import os
import re
import json
import numpy as np
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import pdfplumber
import google.generativeai as genai
from dotenv import load_dotenv
import pandas as pd
import logging
from typing import Dict, List, Union, Optional, Any, Tuple
import difflib
import time
from collections import deque
from threading import Lock
import random

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configure Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY not found in environment variables")
    raise ValueError("GEMINI_API_KEY environment variable is required")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Rate limiter for Gemini API
class RateLimiter:
    """Rate limiter for API calls with dynamic adjustment based on batch size.
    
    Tracks API calls within a time window and provides throttling mechanisms to avoid
    exceeding API rate limits. Dynamically adjusts throttling based on batch size.
    """
    def __init__(self, max_calls_per_min=15, window_size_sec=60):
        self.max_calls_per_min = max_calls_per_min  # Default for free tier
        self.window_size_sec = window_size_sec
        self.calls = deque()
        self.lock = Lock()
        self.batch_size = 1  # Default batch size
        self.failed_files = []  # Track failed files for retry
        self.current_wait_time = 0  # Current adaptive wait time
        
    def set_batch_size(self, batch_size):
        """Set the batch size to dynamically adjust rate limiting."""
        with self.lock:
            self.batch_size = max(1, batch_size)  # Ensure at least 1
            # Calculate the wait time based on batch size to stay under limits
            if batch_size > self.max_calls_per_min:
                # If batch size exceeds max calls per minute, spread out calls
                self.current_wait_time = (self.window_size_sec / self.max_calls_per_min) * 1.2  # Add 20% buffer
            else:
                # Otherwise use minimal wait time with a small buffer
                self.current_wait_time = (self.window_size_sec / self.max_calls_per_min) * 0.8
            
            logger.info(f"Rate limiter adjusted: batch_size={batch_size}, wait_time={self.current_wait_time:.2f}s")
            
    def add_failed_file(self, file_path):
        """Add a file that failed due to rate limiting for later retry."""
        with self.lock:
            if file_path not in self.failed_files:
                self.failed_files.append(file_path)
                
    def get_failed_files(self):
        """Get the list of files that failed due to rate limiting."""
        with self.lock:
            return self.failed_files.copy()
            
    def clear_failed_files(self):
        """Clear the list of failed files."""
        with self.lock:
            self.failed_files.clear()
            
    def wait_if_needed(self, force_wait=False):
        """Check if we need to wait before making another API call.
        
        Args:
            force_wait: If True, always wait even if under rate limit
            
        Returns:
            bool: True if waited, False if no wait needed
        """
        with self.lock:
            # Clean up old calls outside the window
            current_time = time.time()
            while self.calls and current_time - self.calls[0] > self.window_size_sec:
                self.calls.popleft()
                
            # Check if we're at the rate limit
            call_count = len(self.calls)
            calls_remaining = self.max_calls_per_min - call_count
            
            # Dynamic wait time based on remaining capacity and batch size
            if force_wait or calls_remaining < 3 or call_count >= (self.max_calls_per_min * 0.8):  # 80% threshold
                # Add jitter to avoid thundering herd problem (all processes calling at once after waiting)
                jitter = random.uniform(0.8, 1.2)  
                wait_time = self.current_wait_time * jitter
                
                if calls_remaining <= 1:
                    # If almost at limit, wait full window to ensure we don't exceed
                    wait_time = max(wait_time, self.window_size_sec * 0.25)  # At least 25% of window
                    
                logger.info(f"Rate limiting: waiting {wait_time:.2f}s ({call_count}/{self.max_calls_per_min} calls used in last minute)")
                time.sleep(wait_time)
                return True
                
            return False
            
    def add_call(self):
        """Record an API call."""
        with self.lock:
            self.calls.append(time.time())
            
    def get_utilization(self):
        """Get current API usage percentage."""
        with self.lock:
            # Clean up old calls
            current_time = time.time()
            while self.calls and current_time - self.calls[0] > self.window_size_sec:
                self.calls.popleft()
                
            return (len(self.calls) / self.max_calls_per_min) * 100

# Create global rate limiter instance
rate_limiter = RateLimiter()

# Define common patterns for invoice fields
PATTERNS = {
    'invoice_number': r'Invoice No\.?\s*:?\s*([A-Za-z0-9\-\/]+)',
    'invoice_date': r'Date of Invoice\s*:?\s*([0-9\-\/\.]+(?:\s*\([^)]*\))?)',
    'fssai_number': r'FSSAI\s*:?\s*([A-Za-z0-9]+)',
}

# Define purely structural invoice patterns without any company/industry-specific identifiers
INVOICE_PATTERNS = {
    'pattern_a': {
        'table_patterns': [
            # Common column structure: Description + HSN + Quantity + Weight + Rate + Amount
            {'headers': ['DESCRIPTION', 'HSN', 'QUANTITY', 'WEIGHT', 'RATE', 'AMOUNT'], 'confidence': 0.9},
            {'headers': ['DESCRIPTION OF GOODS', 'HSN', 'QTY', 'WEIGHT', 'RATE', 'AMOUNT'], 'confidence': 0.9},
            {'headers': ['GOODS DESCRIPTION', 'HSN/SAC', 'QTY', 'WEIGHT', 'RATE', 'AMOUNT'], 'confidence': 0.9},
            {'headers': ['GOODS', 'HSN CODE', 'QUANTITY', 'WEIGHT', 'RATE', 'AMOUNT'], 'confidence': 0.9},
            # Variations with bags instead of quantity
            {'headers': ['DESCRIPTION', 'HSN', 'BAGS', 'WEIGHT', 'RATE', 'AMOUNT'], 'quantity_col': 'BAGS', 'weight_col': 'WEIGHT', 'confidence': 0.9},
            {'headers': ['DESCRIPTION', 'HSN', 'BAGS', 'QUINTAL', 'RATE', 'AMOUNT'], 'quantity_col': 'BAGS', 'weight_col': 'QUINTAL', 'confidence': 0.9}
        ]
    },
    'pattern_b': {
        'table_patterns': [
            # Common structure: Description + Quantity + Rate + Amount (no HSN)
            {'headers': ['DESCRIPTION', 'QUANTITY', 'RATE', 'AMOUNT'], 'confidence': 0.9},
            {'headers': ['ITEM', 'QTY', 'RATE', 'AMOUNT'], 'confidence': 0.9},
            {'headers': ['PARTICULARS', 'QUANTITY', 'RATE', 'VALUE'], 'confidence': 0.9},
            {'headers': ['GOODS', 'QTY', 'PRICE', 'TOTAL'], 'confidence': 0.9},
            {'headers': ['PRODUCT', 'QUANTITY', 'PRICE', 'TOTAL'], 'confidence': 0.9}
        ]
    },
    'pattern_c': {
        'table_patterns': [
            # Complex structure with batch/lot numbers and other details
            {'headers': ['DESCRIPTION', 'HSN', 'BATCH', 'NET', 'QUANTITY', 'WEIGHT', 'RATE'], 'confidence': 0.9},
            {'headers': ['PRODUCT', 'HSN/SAC', 'LOT', 'QTY', 'WEIGHT', 'RATE', 'AMOUNT'], 'confidence': 0.9},
            {'headers': ['DESCRIPTION', 'HSN', 'BATCH', 'NET', 'BAGS', 'WEIGHT', 'RATE'], 'quantity_col': 'BAGS', 'weight_col': 'WEIGHT', 'confidence': 0.9}
        ]
    },
    'pattern_d': {
        'table_patterns': [
            # Special format with Bag, Pkg, and Quantity columns (AM AGRO type invoices)
            {'headers': ['DESCRIPTION', 'HSN/SAC', 'BATCH', 'BAG', 'PKG', 'QUANTITY', 'RATE', 'PER', 'AMOUNT'], 
             'quantity_col': 'QUANTITY', 'bag_col': 'BAG', 'confidence': 0.95},
            {'headers': ['DESCRIPTION OF GOODS', 'HSN/SAC', 'BATCH', 'BAG', 'PKG', 'QUANTITY', 'RATE', 'PER', 'AMOUNT'], 
             'quantity_col': 'QUANTITY', 'bag_col': 'BAG', 'confidence': 0.95},
            {'headers': ['SR', 'DESCRIPTION', 'HSN/SAC', 'BATCH', 'BAG', 'PKG', 'QUANTITY', 'RATE', 'PER', 'AMOUNT'], 
             'quantity_col': 'QUANTITY', 'bag_col': 'BAG', 'confidence': 0.95},
            # Shorter variations that still have the distinctive BAG and PKG columns
            {'headers': ['DESCRIPTION', 'HSN/SAC', 'BAG', 'PKG', 'QUANTITY', 'RATE', 'PER', 'AMOUNT'],
             'quantity_col': 'QUANTITY', 'bag_col': 'BAG', 'confidence': 0.95},
            {'headers': ['DESCRIPTION', 'HSN/SAC', 'BAG', 'PKG', 'QUANTITY', 'RATE', 'PER'],
             'quantity_col': 'QUANTITY', 'bag_col': 'BAG', 'confidence': 0.95}
        ]
    },
    'generic': {
        'table_patterns': [
            # Generic fallback patterns for common invoice structures
            {'headers': ['DESCRIPTION', 'QUANTITY', 'RATE', 'AMOUNT'], 'confidence': 0.7},
            {'headers': ['ITEM', 'QTY', 'PRICE', 'VALUE'], 'confidence': 0.7},
            {'headers': ['GOODS', 'QUANTITY', 'PRICE', 'TOTAL'], 'confidence': 0.7}
        ]
    }
}

def extract_text_from_image(pdf_path):
    """Extract text from PDF using OCR with enhanced preprocessing.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text as string
    """
    text = ""
    try:
        # Convert PDF to images with higher DPI for better quality
        images = convert_from_path(pdf_path, dpi=300)
        
        for image in images:
            # Preprocess image for better OCR results
            img_gray = image.convert('L')
            
            # Increase contrast for better text recognition
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(img_gray)
            img_enhanced = enhancer.enhance(1.5)  # Increase contrast by 50%
            
            # Use page segmentation mode 3 (fully automatic page segmentation, but no OSD)
            # and OCR Engine Mode 3 (default, based on what is available)
            text += pytesseract.image_to_string(
                img_enhanced,
                config='--psm 3 --oem 3'
            ) + "\n"
            
    except Exception as e:
        logger.error(f"Error extracting text from image: {e}")
    return text

def extract_full_text(pdf_path):
    """Extract text from PDF using pdfplumber.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text as string
    """
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        logger.error(f"Error extracting text with pdfplumber: {e}")
    return text

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using pdfplumber first, then OCR if needed.
    Also extracts tables for better structured data.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text as string
    """
    text = extract_full_text(pdf_path)
    table_text = extract_tables_from_pdf(pdf_path)
    
    # Combine normal text and table text
    if table_text.strip():
        text = text + "\n\n" + table_text
    
    if not text.strip():
        logger.info("No text found with pdfplumber. Switching to OCR...")
        text = extract_text_from_image(pdf_path)
    
    return text


def extract_tables_from_pdf(pdf_path):
    """Extract tables from PDF using pdfplumber and format as text.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted table text as string
    """
    table_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if tables:
                    for table_idx, table in enumerate(tables):
                        # Add table marker
                        table_text += f"\n--- TABLE {i+1}.{table_idx+1} ---\n"
                        
                        # Format table as text with proper column alignment
                        for row in table:
                            formatted_row = [str(cell).strip() if cell else "" for cell in row]
                            table_text += " | ".join(formatted_row) + "\n"
    except Exception as e:
        logger.error(f"Error extracting tables: {e}")
    
    return table_text


def identify_invoice_pattern(text):
    """Identify the invoice pattern based purely on table structure.
    
    Args:
        text: Extracted text from invoice
        
    Returns:
        Pattern name and confidence score as tuple
    """
    best_pattern = 'generic'
    best_confidence = 0.0
    best_table_pattern = None
    detected_columns = {}
    
    # Use uppercase for more reliable matching
    upper_text = text.upper()
    
    # Extract tables from text to identify column headers directly
    tables = extract_tables_from_text(text)
    if tables and len(tables) > 0 and len(tables[0]) > 0:
        headers = [h.upper() for h in tables[0][0] if h]  # First row of first table
        
        # Attempt to classify column types based on semantic understanding
        for header in headers:
            # Identify quantity columns
            if any(q_term in header for q_term in ['QTY', 'QUANTITY', 'BAGS', 'NOS', 'PIECES', 'PCS', 'COUNT']):
                detected_columns['quantity_col'] = header
            
            # Identify weight columns - various ways weight can be represented
            elif any(w_term in header for w_term in ['WEIGHT', 'WT', 'KG', 'NET', 'QUINTAL', 'QTL', 'MT', 'TON']):
                # Special case: "NET (KG) PER BAG" is weight-related, not quantity
                if 'PER BAG' in header or 'PER UNIT' in header:
                    detected_columns['weight_col'] = header
                else:
                    detected_columns['weight_col'] = header
            
            # Identify rate columns
            elif any(r_term in header for r_term in ['RATE', 'PRICE', 'UNIT PRICE', '/KG', '/QTL', '/BAG', 'PER']):
                detected_columns['rate_col'] = header
            
            # Identify amount/total columns
            elif any(a_term in header for a_term in ['AMOUNT', 'TOTAL', 'VALUE', 'AMT']):
                detected_columns['amount_col'] = header
            
            # Identify description columns
            elif any(d_term in header for d_term in ['DESC', 'ITEM', 'PRODUCT', 'COMMODITY', 'PARTICULARS']):
                detected_columns['desc_col'] = header
    
    # For each pattern type
    for pattern_name, pattern_info in INVOICE_PATTERNS.items():
        # For each table pattern in this type
        for table_pattern in pattern_info['table_patterns']:
            # Count how many headers are found in the text
            headers_found = 0
            for header in table_pattern['headers']:
                if header.upper() in upper_text:
                    headers_found += 1
            
            # Calculate match ratio
            if len(table_pattern['headers']) > 0:
                match_ratio = headers_found / len(table_pattern['headers'])
                current_confidence = table_pattern['confidence'] * match_ratio
                
                # Check if this pattern has a higher confidence
                if current_confidence > best_confidence:
                    best_confidence = current_confidence
                    best_pattern = pattern_name
                    best_table_pattern = table_pattern
    
    # Format the pattern string, prioritizing detected columns if available
    pattern_key = "generic"
    
    if detected_columns:
        # Use detected columns as the primary source of information
        quantity_col = detected_columns.get('quantity_col', 'QUANTITY')
        weight_col = detected_columns.get('weight_col', 'WEIGHT')
        rate_col = detected_columns.get('rate_col', 'RATE')
        
        # Include semantic information in the pattern key
        pattern_key = f"{best_pattern}:{quantity_col}:{weight_col}:{rate_col}"
        
        # Boost confidence if we detected specific columns
        best_confidence = max(best_confidence, 0.4)
    elif best_table_pattern and best_confidence > 0.3:
        # Fall back to pattern-based approach if no columns detected
        if 'quantity_col' in best_table_pattern:
            quantity_col = best_table_pattern['quantity_col']
            weight_col = best_table_pattern.get('weight_col', 'WEIGHT')
            pattern_key = f"{best_pattern}:{quantity_col}:{weight_col}"
        else:
            # Use default columns
            headers_str = "-".join([h.replace(' ', '_') for h in best_table_pattern['headers'][:3]])
            pattern_key = f"{best_pattern}:{headers_str}"
    else:
        # Minimum confidence threshold for generic pattern
        best_confidence = max(best_confidence, 0.3)
    
    logger.info(f"Pattern detection: {pattern_key} (confidence: {best_confidence:.2f})")
    if detected_columns:
        logger.info(f"Detected columns: {detected_columns}")
        
    return pattern_key, best_confidence


def get_template_specific_prompt(pattern_key, text):
    """Get structure-based extraction prompt based on the identified table pattern.
    
    Args:
        pattern_key: Key of the identified pattern (includes column information)
        text: Extracted text from invoice
        
    Returns:
        Prompt string with structure-specific instructions
    """
    # Parse the pattern key to extract column information
    pattern_parts = pattern_key.split(":")
    pattern_type = pattern_parts[0]
    
    # Base prompt that works for all patterns
    base_prompt = """
You are an expert in extracting structured data from invoices. Extract these details accurately:

1. **Goods Description**: The exact product name/description as written in the invoice.
2. **HSN/SAC Code**: The HSN or SAC numerical code.
3. **Quantity**: The numerical count of items/bags/pieces. This is often labeled as "BAGS" or "QTY".
4. **Weight**: The total weight with unit (kg, qtl, tons) - NOT the weight per unit.
5. **Rate**: The rate per unit of weight (often per kg/quintal). Look for a monetary value.
6. **Amount**: The total amount for this product. This is not the invoice total.
7. **Company Name**: The name of the SELLER (not buyer) issuing the invoice.
8. **Invoice Number**: Only the number, without "Invoice No." prefix.
9. **FSSAI Number**: The seller's FSSAI license number if available.
10. **Date of Invoice**: The invoice date.

**CRITICALLY IMPORTANT FOR COLUMN INTERPRETATION**:
- "BAGS" or similar columns ALWAYS represent the quantity (number of bags/units)
- "NET (Kg)" or similar columns represent the total weight, not quantity
- "NET (Kg) PER BAG" represents weight per individual bag, not the quantity
- "Rate" is usually price per weight unit (per kg/quintal) not price per bag

If a column is labeled "NET (Kg) PER BAG" or similar, this is NOT the quantity - it's the weight of each individual bag.
If a different column shows the count of bags (often labeled "BAGS"), that is the quantity.
"""
    
    # Check if this is a birla mill invoice or similar format that's causing issues
    is_problematic_format = ("NET (Kg) PER BAG" in text or "BIRLA RICE" in text or 
                            "NET (KG)" in text or "PER BAG" in text or 
                            "BAGS" in text and "NET" in text and "RATE" in text)
    
    # Check if this matches AM AGRO format or similar with BAG and PKG columns
    is_agro_format = ("BAG" in text and "PKG" in text and "QUANTITY" in text and "PER" in text) or \
                     ("A M AGRO" in text or "AGRO INDUSTRIES" in text)
    
    special_instructions = ""
    if is_problematic_format:
        special_instructions = """
**SPECIAL COLUMN HANDLING REQUIRED IN THIS INVOICE**:

This invoice has a specific table structure that MUST be interpreted as follows:

1. "BAGS" column = QUANTITY (count of bags)
   - This is always a whole number like 200, 300, 500 bags
   - Goes into the "quantity" field

2. "NET (Kg) PER BAG" or similar = WEIGHT PER UNIT
   - This is the weight of ONE bag (like 25kg, 50kg)
   - NOT a quantity - DO NOT use this for the quantity field
   - DO NOT use this as the total weight either

3. "NET" column = TOTAL WEIGHT
   - This is the total weight (BAGS × weight per bag)
   - This goes into the "weight" field (with kg unit)

4. "Rate" column = PRICE PER WEIGHT UNIT
   - Usually price per 100kg or per quintal
   - This goes into the "rate" field

MANDATORY FIELD MAPPING:
- "BAGS" → quantity field
- "NET" → weight field (with kg unit)
- "Rate" → rate field

Example row with CORRECT interpretation:
| Description | HSN | BAGS | NET (Kg) PER BAG | NET | Rate | Amount |
| ----------- | --- | ---- | --------------- | --- | ---- | ------ |
| STEAM RICE  | 123 | 200  | 25              | 5000| 2000 | 100000 |

You MUST extract this as:
```json
{
  "goods_description": "STEAM RICE",
  "hsn_sac_code": "123",
  "quantity": "200",        /* from BAGS column */
  "weight": "5000 kg",     /* from NET column */
  "rate": "2000",          /* from Rate column */
  "amount": "100000"       /* from Amount column */
}
```

DO NOT use "NET (Kg) PER BAG" as the quantity under any circumstances.
"""
    elif is_agro_format:
        special_instructions = """
**SPECIAL COLUMN HANDLING REQUIRED FOR THIS INVOICE FORMAT**:

This invoice has a multi-column structure that MUST be interpreted correctly:

1. "BAG" column = Number of bags (a packaging count)
   - This is NOT the primary quantity for extraction
   - Example: 307 bags

2. "PKG" column = Package information (usually a code)
   - This is NOT used for quantity calculation

3. "QUANTITY" column = The actual TOTAL QUANTITY in metric tons (MT) or similar unit
   - This is the MAIN quantity to extract
   - This is a decimal value (like 0.26, 80.08, etc.)
   - Example: 0.26 MT = 260 kg

4. "RATE" column = Price per unit
   - The "PER" column specifies the unit (usually KGS)
   - Example: 4850.00 per KGS

MANDATORY FIELD MAPPING:
- Description column → goods_description
- HSN/SAC column → hsn_sac_code
- QUANTITY column → quantity/weight field (include the unit like MT)
- RATE column → rate field

Example row with CORRECT interpretation:
| Description | HSN/SAC | Batch | Bag | Pkg | Quantity | Rate | Per | Amount |
| ----------- | ------- | ----- | --- | --- | -------- | ---- | --- | ------ |
| Loose Rice  | 1006309 | 511   | 307 | 0.26| 79.82    | 4850 | KGS | 387127 |

You MUST extract this as:
```json
{
  "goods_description": "Loose Rice",
  "hsn_sac_code": "1006309",
  "quantity": "79.82 MT",    /* from QUANTITY column */
  "rate": "4850",           /* from Rate column */
  "amount": "387127"        /* from Amount column */
}
```

If the QUANTITY column has a small decimal value (like 0.26), it's likely in Metric Tons (MT) and should be interpreted as such.
"""
    
    # Extract table data for analysis
    table_data = extract_structured_tables(text)
    column_hints = """

**DETECTED COLUMN STRUCTURE**:
""" + table_data
    
    # Example structure to help the model understand the format
    example_json = """
{
  "company_name": "SHRI EXAMPLE RICE MILL",
  "invoice_number": "780",
  "fssai_number": "12345678901234",
  "invoice_date": "26/06/2023",
  "products": [
    {
      "goods_description": "STEAM KOLAM RICE",
      "hsn_sac_code": "10063090",
      "quantity": "500",
      "weight": "25000 kg",
      "rate": "4300",
      "amount": "1075000"
    }
  ]
}
"""
    
    # Combine all guidance
    full_prompt = (
        base_prompt + 
        special_instructions +
        column_hints +
        "\n\nHere's an example of the expected JSON output:\n" + example_json +
        "\n\nNow extract from this invoice text:\n" + text
    )
    
    return full_prompt


def extract_structured_tables(text):
    """Extract tables with structure analysis to help identify columns.
    
    Args:
        text: Text to extract tables from
        
    Returns:
        Structured string representation of tables with column analysis
    """
    # Try to find table patterns within the text
    table_rows = []
    lines = text.split('\n')
    in_table = False
    numeric_columns = {}
    headers = []
    
    for line in lines:
        if '|' in line and len(line.split('|')) > 3:
            # Potential table row
            if not in_table:
                in_table = True
                headers = [cell.strip() for cell in line.split('|')]
                table_rows.append(headers)
            else:
                row_cells = [cell.strip() for cell in line.split('|')]
                table_rows.append(row_cells)
                
                # Analyze numeric columns
                for i, cell in enumerate(row_cells):
                    if i < len(headers) and i not in numeric_columns:
                        numeric_columns[i] = {}
                    
                    # Try to extract numeric values
                    if i in numeric_columns:
                        matches = re.findall(r'\d+(\.\d+)?', cell)
                        if matches and matches[0]:
                            try:
                                numeric_value = float(matches[0])
                                if 'min' not in numeric_columns[i] or numeric_value < numeric_columns[i]['min']:
                                    numeric_columns[i]['min'] = numeric_value
                                if 'max' not in numeric_columns[i] or numeric_value > numeric_columns[i]['max']:
                                    numeric_columns[i]['max'] = numeric_value
                            except ValueError:
                                # Skip if conversion fails
                                pass
    
    # Generate column analysis
    result = ""
    if table_rows and len(table_rows) > 1:
        result += "Found columns: " + ", ".join(f'"{h}"' for h in table_rows[0] if h) + "\n\n"
        
        # Add column type suggestions
        result += "Column type suggestions based on patterns:\n"
        
        for i, header in enumerate(table_rows[0]):
            if i in numeric_columns and 'min' in numeric_columns[i] and 'max' in numeric_columns[i]:
                col_type = ""
                
                # Quantity columns are often whole numbers with low values
                if 'BAG' in header or 'QTY' in header or 'QUANTITY' in header or 'PCS' in header:
                    col_type = "QUANTITY (count of items/bags)"
                # Weight per unit columns often have medium values with decimals
                elif 'PER' in header and ('KG' in header or 'WEIGHT' in header or 'NET' in header):
                    col_type = "WEIGHT PER UNIT"
                # Total weight columns often have larger values
                elif 'WEIGHT' in header or 'NET' in header or 'KG' in header:
                    col_type = "TOTAL WEIGHT"
                # Rate columns have currency values
                elif 'RATE' in header or 'PRICE' in header:
                    col_type = "RATE (price per unit)"
                # Amount columns have the largest values
                elif 'AMOUNT' in header or 'TOTAL' in header or 'VALUE' in header:
                    col_type = "AMOUNT (total price)"
                
                result += f"Column '{header}': {col_type} - Value range: {numeric_columns[i]['min']} to {numeric_columns[i]['max']}\n"
    
    return result


def extract_tables_from_text(text):
    """Extract table structures from text.
    
    Args:
        text: Text to extract tables from
        
    Returns:
        List of tables with rows and columns
    """
    tables = []
    table_sections = re.split(r'\n-+\s*TABLE\s+\d+\.\d+\s*-+\n', text)
    
    # Skip the first section which is usually before any table
    for section in table_sections[1:] if len(table_sections) > 1 else table_sections:
        lines = section.strip().split('\n')
        if not lines:
            continue
            
        # Process table rows
        rows = []
        for line in lines:
            if ' | ' in line:
                # Split by delimiter and clean each cell
                row = [cell.strip() for cell in line.split(' | ')]
                rows.append(row)
        
        if rows:
            tables.append(rows)
    
    return tables


def process_with_gemini(text, pattern_name=None, focus=None, max_attempts=3, file_path=None):
    """Process extracted text with Gemini AI to extract structured data.
    Uses pattern recognition and focuses on specific sections if needed.
    
    Args:
        text: Extracted text from the PDF
        pattern_name: Optional predefined pattern name to use
        focus: Optional section to focus on ('header', 'products', or None for entire invoice)
        max_attempts: Maximum number of extraction attempts
        file_path: Path to the invoice file for tracking retries
        
    Returns:
        Structured data as JSON or None if processing failed
    """
    # Identify invoice pattern if not provided
    if not pattern_name:
        pattern_name, _ = identify_invoice_pattern(text)
    
    # Get pattern-specific prompt
    prompt = get_template_specific_prompt(pattern_name, text)
    
    # Attempt extraction
    attempts = 0
    result = None
    exponential_backoff = 1  # Initial backoff in seconds
    max_backoff = 32  # Maximum backoff in seconds
    
    while attempts < max_attempts and not result:
        attempts += 1
        logger.info(f"Attempt {attempts} to extract data using pattern '{pattern_name}'")
        
        # Check rate limits before making API call
        rate_limiter.wait_if_needed(force_wait=(attempts > 1))  # Force wait on retry attempts
        
        try:
            # Record this API call
            rate_limiter.add_call()
            
            # Make the API call
            response = model.generate_content(prompt)
            raw_result = response.text
            
            # Reset backoff on success
            exponential_backoff = 1
            
            # Clean up the response to extract only the JSON part
            if "```json" in raw_result:
                raw_result = raw_result.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_result:
                raw_result = raw_result.split("```")[1].split("```")[0].strip()
            
            # Parse the JSON to validate it
            result = json.loads(raw_result)
            
            # Validate extracted data
            validation_results = validate_extraction(result, text, pattern_name)
            if not validation_results['is_valid']:
                logger.warning(f"Validation failed: {validation_results['errors']}")
                
                # If attempt failed validation, refine the prompt
                if attempts < max_attempts:
                    prompt = refine_prompt_based_on_validation(prompt, validation_results['errors'])
                    result = None  # Reset result to trigger another attempt
                    continue
            
            # If we reached here, extraction succeeded or we ran out of attempts
            if "products" not in result:
                # Reconstruct to correct format if needed
                if isinstance(result, list):
                    # Extract common fields from first product if available
                    common_fields = {}
                    if result:
                        for field in ["company_name", "invoice_number", "fssai_number", "invoice_date"]:
                            if field in result[0]:
                                common_fields[field] = result[0].get(field, "N/A")
                    
                    # Reconstruct in expected format
                    result = {
                        "company_name": common_fields.get("company_name", "N/A"),
                        "invoice_number": common_fields.get("invoice_number", "N/A"),
                        "fssai_number": common_fields.get("fssai_number", "N/A"),
                        "invoice_date": common_fields.get("invoice_date", "N/A"),
                        "products": result if isinstance(result, list) else []
                    }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error in Gemini processing: {error_msg}")
            
            # Check for rate limit errors
            if "429" in error_msg or "Resource has been exhausted" in error_msg:
                # Add to failed files list for retry
                if file_path:
                    rate_limiter.add_failed_file(file_path)
                
                # If we're rate limited, use exponential backoff
                wait_time = exponential_backoff + random.uniform(0, 1)  # Add jitter
                logger.warning(f"Rate limit exceeded. Backing off for {wait_time:.2f} seconds")
                time.sleep(wait_time)
                
                # Increase backoff for next attempt (exponential)
                exponential_backoff = min(exponential_backoff * 2, max_backoff)
            
            # If we've reached max attempts, give up
            if attempts >= max_attempts:
                logger.error(f"Failed after {max_attempts} attempts")
                return None
            
            # For non-rate limit errors, add a small delay before retrying
            if "429" not in error_msg and "Resource has been exhausted" not in error_msg:
                time.sleep(1)
    
    # Post-process the extraction result
    if result:
        result = post_process_extraction(result, text, pattern_name)
    
    return result


def validate_extraction(result, text, pattern_name):
    """Validate the extraction result against expected patterns.
    
    Args:
        result: Extracted JSON data
        text: Original invoice text
        pattern_name: Invoice pattern name
        
    Returns:
        Dictionary with validation results and errors
    """
    errors = []
    
    # Check required fields
    required_fields = ["company_name", "invoice_number", "invoice_date", "products"]
    for field in required_fields:
        if field not in result or not result[field]:
            errors.append(f"Missing required field: {field}")
    
    # Company name validation
    if "company_name" in result:
        # Remove any common prefixes or suffixes
        result["company_name"] = re.sub(r'^M/s\s+', '', result["company_name"])
        
        # Try to match with known company names if close enough
        for pattern, pattern_info in INVOICE_PATTERNS.items():
            if 'identifiers' in pattern_info:
                for identifier in pattern_info['identifiers']:
                    if difflib.SequenceMatcher(None, result["company_name"], identifier).ratio() > 0.8:
                        result["company_name"] = identifier
                        break
    
    # Invoice number validation - should be mostly numeric
    if "invoice_number" in result and result["invoice_number"] != "N/A":
        if not re.search(r'\d', result["invoice_number"]):
            errors.append(f"Invoice number '{result['invoice_number']}' doesn't contain any digits")
            
        # Remove any non-numeric or non-alphanumeric characters, preserving alphanumeric invoice numbers
        invoice_num = result["invoice_number"]
        # Keep the alphanumeric pattern but remove extra symbols like "#", "/", etc.
        invoice_num = re.sub(r'[^a-zA-Z0-9]', '', invoice_num)
        result['invoice_number'] = invoice_num
    
    # Product validation
    if "products" in result and isinstance(result["products"], list):
        if not result["products"]:
            errors.append("No products extracted")
        else:
            for i, product in enumerate(result["products"]):
                # Check required product fields
                for field in ["goods_description", "quantity", "rate", "amount"]:
                    if field not in product or not product[field] or product[field] == "N/A":
                        if field in ["quantity", "rate", "amount"] and field in product and product[field] == "N/A":
                            # For numerical fields, N/A is suspicious if the field is typically required
                            errors.append(f"Product {i+1} has suspicious '{field}' value: {product.get(field, 'missing')}")
    
    return {
        "is_valid": len(errors) == 0,
        "errors": errors
    }


def refine_prompt_based_on_validation(original_prompt, errors):
    """Refine the prompt based on validation errors.
    
    Args:
        original_prompt: Original prompt string
        errors: List of validation errors
        
    Returns:
        Refined prompt string
    """
    refinements = ["\n\n**IMPORTANT CORRECTIONS NEEDED:**"]
    
    for error in errors:
        if "Company name" in error:
            refinements.append("- The company name should be the SELLER (the entity issuing the invoice), not the buyer.")
        elif "Invoice number" in error and "prefix" in error:
            refinements.append("- Extract ONLY the number part after 'Invoice No.' - do not include the prefix.")
        elif "No products extracted" in error:
            refinements.append("- Look carefully for the product table. It usually contains columns for description, quantity, rate, and amount.")
        elif "suspicious" in error and "quantity" in error:
            refinements.append("- Look for numerical quantity values, often in a column labeled 'BAGS' or 'QTY'.")
        elif "suspicious" in error and "rate" in error:
            refinements.append("- The rate should be a monetary value, often in a column labeled 'RATE' or 'Price'.")
        elif "suspicious" in error and "amount" in error:
            refinements.append("- The amount should be the total cost for each product, often in a column labeled 'AMOUNT' or 'Total'.")
    
    # Add general improvement instructions
    refinements.append("- Ensure all extracted values match exactly what's in the invoice.")
    refinements.append("- Pay special attention to the table structure for product details.")
    
    # Combine original prompt with refinements
    refined_prompt = original_prompt + "\n" + "\n".join(refinements)
    
    return refined_prompt


def post_process_extraction(result, text, pattern_name):
    """Post-process the extraction result to fix common issues.
    
    Args:
        result: Extracted JSON data
        text: Original invoice text
        pattern_name: Invoice pattern name
        
    Returns:
        Processed result
    """
    if not result:
        return result
    
    # Fix incomplete company name extraction
    if result.get('company_name', '').strip() in ['N/A', '', 'NULL'] or result.get('company_name') == "RICE MILL":
        # Look for company name patterns in the first 20 lines of the text
        lines = text.split('\n')[:20]  # Check only first 20 lines where company name usually appears
        
        # Common patterns for company names
        company_patterns = [
            # Look for M/s followed by capitalized words
            r'M/s\s+((?:[A-Z][A-Za-z]*\s*)+(?:RICE MILL|AGRO|INDUSTRIES|PVT\.? LTD\.?|LIMITED))',
            # Look for capitalized words followed by entity types
            r'\b((?:[A-Z][A-Za-z]*\s*)+(?:RICE MILL|AGRO|INDUSTRIES|PVT\.? LTD\.?|LIMITED))\b',
            # Company name section header followed by name
            r'(?:Company|Seller|From):\s*((?:[A-Z][A-Za-z]*\s*)+)'
        ]
        
        potential_companies = []
        for pattern in company_patterns:
            for line in lines:
                # Convert line to uppercase for consistent matching
                upper_line = line.upper()
                
                if 'M/S' in upper_line and 'RICE MILL' in upper_line:
                    # Special handling for M/s prefix to ensure it's captured correctly
                    m_s_match = re.search(r'(M/S\s+(?:[A-Z][A-Za-z]*\s*)+(?:RICE MILL|AGRO|INDUSTRIES))', upper_line)
                    if m_s_match:
                        # Keep original case from the original text
                        start_idx = line.upper().find(m_s_match.group(1))
                        end_idx = start_idx + len(m_s_match.group(1))
                        company_name = line[start_idx:end_idx]
                        potential_companies.append((company_name, len(company_name) + 5))  # Bonus points for M/s prefix
                
                # Regular pattern matching
                matches = re.finditer(pattern, upper_line)
                for match in matches:
                    # Keep original case by extracting from the original line
                    start_idx = line.upper().find(match.group(1).upper())
                    if start_idx >= 0:
                        end_idx = start_idx + len(match.group(1))
                        company_name = line[start_idx:end_idx]
                        
                        # Check if we should prepend M/s if it appears before the company name
                        m_s_prefix = ""
                        if start_idx > 4 and "M/S" in line[start_idx-4:start_idx].upper():
                            m_s_start = line.upper().find("M/S", max(0, start_idx-10), start_idx)
                            if m_s_start >= 0:
                                m_s_prefix = line[m_s_start:start_idx].strip() + " "
                        
                        full_company = m_s_prefix + company_name
                        potential_companies.append((full_company, len(full_company)))
        
        # Sort by length of company name (longer names are typically more complete)
        potential_companies.sort(key=lambda x: x[1], reverse=True)
        
        if potential_companies:
            # Use the longest matching company name
            result['company_name'] = potential_companies[0][0]
    
    # Correcting invoice number formatting
    if result.get('invoice_number'):
        # Remove any non-numeric or non-alphanumeric characters, preserving alphanumeric invoice numbers
        invoice_num = result['invoice_number']
        # Keep the alphanumeric pattern but remove extra symbols like "#", "/", etc.
        invoice_num = re.sub(r'[^a-zA-Z0-9]', '', invoice_num)
        result['invoice_number'] = invoice_num
    
    # Extract FSSAI number if missing
    if not result.get('fssai_number') or result.get('fssai_number') == 'N/A':
        # Common patterns for FSSAI numbers
        fssai_patterns = [
            r'FSSAI\s*(?:No\.?|Number\.?|#)?\s*:?\s*(\d{10,14})',
            r'(?:FSSAI|Food License)\s*:?\s*(\d{10,14})'
        ]
        
        for pattern in fssai_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['fssai_number'] = match.group(1)
                break
    
    # Correcting date formatting
    if result.get('invoice_date'):
        date_str = result['invoice_date']
        
        # Try to parse and standardize various date formats
        try:
            # Remove any extra text around the date
            date_str = re.sub(r'[^0-9\-/.\\]', ' ', date_str).strip()
            date_patterns = [
                r'(\d{1,2})[-/\\.](\d{1,2})[-/\\.](\d{2,4})',  # DD-MM-YYYY or similar
                r'(\d{2,4})[-/\\.](\d{1,2})[-/\\.](\d{1,2})',  # YYYY-MM-DD or similar
                r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)[,\s]+(\d{2,4})'  # 21st June, 2023 or similar
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, date_str)
                if match:
                    date_parts = match.groups()
                    if len(date_parts[2]) == 2:  # Year is in YY format
                        year = int(date_parts[2])
                        if year < 30:  # Assuming 20XX for years less than 30
                            year += 2000
                        else:  # Assuming 19XX for years 30 and above
                            year += 1900
                        date_parts = list(date_parts)
                        date_parts[2] = str(year)
                    
                    # Determine the date format
                    if re.match(r'[A-Za-z]+', date_parts[1]):  # Month is in text
                        month_names = {
                            "january": "01", "february": "02", "march": "03", "april": "04",
                            "may": "05", "june": "06", "july": "07", "august": "08",
                            "september": "09", "october": "10", "november": "11", "december": "12",
                            "jan": "01", "feb": "02", "mar": "03", "apr": "04", "jun": "06",
                            "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"
                        }
                        month = month_names.get(date_parts[1].lower(), "01")
                        date_str = f"{date_parts[0]}/{month}/{date_parts[2]}"
                    else:
                        # Check if first component is year (YYYY-MM-DD)
                        if len(date_parts[0]) == 4:
                            date_str = f"{date_parts[2]}/{date_parts[1]}/{date_parts[0]}"  # Convert to DD/MM/YYYY
                        else:
                            date_str = f"{date_parts[0]}/{date_parts[1]}/{date_parts[2]}"  # DD/MM/YYYY
                    
                    # Format consistently as DD/MM/YYYY
                    result['invoice_date'] = date_str
                    break
        except Exception as e:
            logger.warning(f"Error processing date format: {e}")
    
    # Clean up product data
    if 'products' in result and result['products']:
        for product in result['products']:
            # Standardize HSN/SAC code
            if 'hsn_sac_code' in product:
                hsn = product['hsn_sac_code']
                # Keep only numbers for HSN code
                hsn = re.sub(r'[^0-9]', '', hsn)
                product['hsn_sac_code'] = hsn if hsn else "N/A"
            
            # Standardize quantity
            if 'quantity' in product:
                qty = product['quantity']
                # Remove any non-numeric characters except decimal point
                qty = re.sub(r'[^0-9.]', '', qty)
                product['quantity'] = qty if qty else "N/A"
    
    return result


def extract_table_structure(text):
    """Extract and normalize the table structure from invoice text.
    
    Args:
        text: Extracted text from invoice
        
    Returns:
        Table text as string
    """
    table_text = ""
    
    # Try to locate the table structure
    # Look for common table headers
    common_headers = [
        'DESCRIPTION', 'QUANTITY', 'QTY', 'RATE', 'AMOUNT', 'PRICE',
        'ITEM', 'PRODUCT', 'GOODS', 'HSN', 'SAC', 'BAGS', 'WEIGHT', 'QUINTAL'
    ]
    
    # Find table start locations
    start_indices = []
    for header in common_headers:
        pattern = r'\b' + re.escape(header) + r'\b'
        matches = [m.start() for m in re.finditer(pattern, text, re.IGNORECASE)]
        start_indices.extend(matches)
    
    if not start_indices:
        logger.warning("Could not identify product table in invoice")
        return table_text
    
    # Analyze highest concentration of headers to find the table section
    start_indices.sort()
    
    # Special handling for Birla Rice Mill and similar formats
    if "SHRI BIRLA RICE MILL" in text or "BIRLA RICE" in text:
        # Look for specific patterns in Birla Rice Mill invoices
        birla_pattern = r'(DESCRIPTION|PARTICULARS|GOODS).{0,50}(HSN|HSN/SAC).{0,50}(BATCH|BAGS).{0,50}(WEIGHT|QTY)'
        birla_match = re.search(birla_pattern, text, re.IGNORECASE)
        
        if birla_match:
            # Extract the table section - looking for a section with these headers
            # and including several lines after it that likely contain the product data
            table_start = max(0, birla_match.start() - 50)
            # Get a large chunk after the headers to capture the table content
            table_section = text[table_start:table_start + 1000]
            
            # Extract only the table-like structure
            lines = table_section.split('\n')
            table_lines = []
            
            # Flag to track if we're in the table section
            in_table = False
            empty_line_count = 0
            
            for line in lines:
                # Start of table - headers line
                if not in_table and any(header in line.upper() for header in ['DESCRIPTION', 'HSN', 'BATCH', 'WEIGHT']):
                    in_table = True
                    table_lines.append(line)
                # Continue capturing table rows
                elif in_table:
                    # If we hit too many consecutive empty lines, we've probably exited the table
                    if not line.strip():
                        empty_line_count += 1
                        if empty_line_count > 2:
                            in_table = False
                    else:
                        empty_line_count = 0
                        table_lines.append(line)
                        
                        # Look for potential end of table markers
                        if any(marker in line.upper() for marker in ['TOTAL', 'GRAND TOTAL', 'SUBTOTAL', 'AMOUNT IN WORDS']):
                            # Add this line (it's the total) then exit table mode
                            in_table = False
            
            table_text = "\n".join(table_lines)
            return table_text
    
    # General approach for other invoice types
    # Find clusters of header terms
    cluster_size = 150  # Characters to analyze in each cluster
    clusters = []
    
    for i in range(len(start_indices)):
        cluster_start = start_indices[i]
        cluster_end = cluster_start + cluster_size
        
        # Count how many headers are in this cluster
        headers_in_cluster = sum(1 for idx in start_indices if cluster_start <= idx < cluster_end)
        clusters.append((cluster_start, headers_in_cluster))
    
    # Sort clusters by number of headers (descending)
    clusters.sort(key=lambda x: x[1], reverse=True)
    
    if clusters:
        # Use the cluster with the most headers as the table start
        table_start = max(0, clusters[0][0] - 20)  # Start a bit before the first header
        
        # Extract a large portion after the table start
        table_end = min(len(text), table_start + 1000)  # Grab a large chunk to ensure we get the full table
        table_section = text[table_start:table_end]
        
        # Extract only the table-like structure
        lines = table_section.split('\n')
        table_lines = []
        
        # Flag to track if we're in the table section
        in_table = False
        header_line_idx = -1
        
        for i, line in enumerate(lines):
            # Look for a line with multiple headers
            header_count = sum(1 for header in common_headers if header in line.upper())
            
            # Potential table header line if it has multiple headers
            if header_count >= 2:
                in_table = True
                header_line_idx = i
                table_lines.append(line)
            # Continue capturing table rows
            elif in_table and i > header_line_idx:
                # Add lines until we hit a likely end of table
                table_lines.append(line)
                
                # Check for potential end of table indicators
                if any(marker in line.upper() for marker in ['TOTAL', 'GRAND TOTAL', 'SUBTOTAL', 'AMOUNT IN WORDS']):
                    # Include the totals line, then break
                    break
                
                # Stop if we've gone too far from the header line
                if i - header_line_idx > 20:  # Assume table doesn't have more than 20 rows
                    break
        
        table_text = "\n".join(table_lines)
    
    return table_text


def convert_weight_to_kg(weight_str):
    """
    Convert weight from qtl or tons to kg.
    
    Args:
        weight_str: Weight string with unit
        
    Returns:
        Weight in kg or original string if conversion is not possible
    """
    if weight_str == "N/A" or not isinstance(weight_str, str):
        return weight_str
        
    weight_str = weight_str.replace(",", "")  # Remove commas
    
    # Extract number and unit using regex
    match = re.match(r'(\d+(?:\.\d+)?)\s*([a-zA-Z]+)', weight_str)
    if not match:
        return weight_str
        
    try:
        weight_value = float(match.group(1))
        weight_unit = match.group(2).lower()
        
        if "qtl" in weight_unit:
            return weight_value * 100  # Convert qtl to kg
        elif "ton" in weight_unit:
            return weight_value * 1000  # Convert tons to kg
        elif "kg" in weight_unit:
            return weight_value  # No conversion needed
        else:
            return weight_str  # Return original if unit is unknown
    except ValueError:
        return weight_str  # Return original if conversion fails


def process_invoice(invoice_path: str, debug_mode=False) -> Dict[str, Any]:
    """Process an invoice and extract structured data with enhanced accuracy.
    
    Args:
        invoice_path: Path to the invoice PDF file
        debug_mode: If True, returns additional debug information
        
    Returns:
        Dictionary containing all extracted data and confidence scores
    """
    logger.info(f"Processing invoice: {invoice_path}")
    
    start_time = time.time()
    
    try:
        # Extract text from PDF with improved method
        text = extract_text_from_pdf(invoice_path)
        
        if not text.strip():
            logger.error("Failed to extract any text from the PDF")
            return {
                "success": False,
                "error": "Could not extract text from PDF",
                "company_name": "N/A",
                "invoice_number": "N/A",
                "fssai_number": "N/A",
                "invoice_date": "N/A",
                "products": []
            }
        
        # Identify invoice pattern
        pattern_name, _ = identify_invoice_pattern(text)
        logger.info(f"Identified pattern '{pattern_name}' for {invoice_path}")
        
        # First attempt - process with pattern-specific prompt
        result = process_with_gemini(text, pattern_name=pattern_name, file_path=invoice_path)
        
        # If first attempt failed, try generic pattern as fallback
        if not result and pattern_name != "generic_invoice":
            logger.info(f"Retrying with generic pattern for {invoice_path}")
            result = process_with_gemini(text, pattern_name="generic_invoice", file_path=invoice_path)
        
        if not result:
            # Check if this was due to rate limiting
            if invoice_path in rate_limiter.get_failed_files():
                logger.error(f"Rate limit exceeded for {invoice_path}")
                return {
                    "success": False,
                    "error": "API rate limit exceeded. Please try again later or process fewer files at once.",
                    "rate_limited": True,
                    "company_name": "N/A",
                    "invoice_number": "N/A",
                    "fssai_number": "N/A",
                    "invoice_date": "N/A",
                    "products": []
                }
            else:
                logger.error(f"Gemini processing failed for {invoice_path}")
                return {
                    "success": False,
                    "error": "Gemini API returned no result",
                    "company_name": "N/A",
                    "invoice_number": "N/A",
                    "fssai_number": "N/A",
                    "invoice_date": "N/A",
                    "products": []
                }
        
        # Process the extracted data
        # No need to parse JSON as process_with_gemini now returns Python dict
        extracted_data = result
        
        # Calculate confidence scores for the extraction
        confidence_scores = {
            "company_name": 0.9 if extracted_data.get("company_name", "N/A") != "N/A" else 0.0,
            "invoice_number": 0.9 if extracted_data.get("invoice_number", "N/A") != "N/A" else 0.0,
            "fssai_number": 0.9 if extracted_data.get("fssai_number", "N/A") != "N/A" else 0.0,
            "invoice_date": 0.9 if extracted_data.get("invoice_date", "N/A") != "N/A" else 0.0,
            "products": min(0.9, 0.2 * len(extracted_data.get("products", []))) # Higher confidence with more products
        }
        
        # Overall confidence
        confidence_scores["overall"] = sum(confidence_scores.values()) / len(confidence_scores)
        
        # Convert weights if needed and clean up product data
        if "products" in extracted_data and extracted_data["products"]:
            for product in extracted_data["products"]:
                if "weight" in product:
                    # Store original weight for display
                    product["original_weight"] = product["weight"]
                    # Convert weight to kg for calculations if needed
                    product["weight_in_kg"] = convert_weight_to_kg(product["weight"])
                    
                # Clean numerical values
                for field in ["quantity", "rate", "amount"]:
                    if field in product and product[field] != "N/A":
                        # Remove unwanted characters but keep decimals and currency symbols
                        clean_value = re.sub(r'[^0-9.,₹$]', '', product[field])
                        product[field] = clean_value
        
        # Add metadata to the result
        processing_time = time.time() - start_time
        final_result = {
            "success": True,
            "pattern_used": pattern_name,
            "confidence_scores": confidence_scores,
            "processing_time": processing_time,
            **extracted_data  # Include all extracted data
        }
        
        # Add debug info if requested
        if debug_mode:
            final_result["debug"] = {
                "text_length": len(text),
                "pattern": pattern_name,
                "filename": os.path.basename(invoice_path)
            }
        
        return final_result
    
    except Exception as e:
        logger.error(f"Error processing invoice: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "company_name": "N/A",
            "invoice_number": "N/A",
            "fssai_number": "N/A",
            "invoice_date": "N/A",
            "products": []
        }

if __name__ == "__main__":
    # For testing
    import sys
    
    if len(sys.argv) > 1:
        invoice_path = sys.argv[1]
        result = process_invoice(invoice_path)
        print(json.dumps(result, indent=4))
    else:
        print("Please provide the path to an invoice PDF file.")
