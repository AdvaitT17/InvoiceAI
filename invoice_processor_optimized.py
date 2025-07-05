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
import hashlib
from functools import lru_cache, wraps
import gc
from concurrent.futures import ThreadPoolExecutor
import pickle
import redis
from contextlib import contextmanager

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

# Global model cache to avoid repeated initialization
_model_cache = {}
_model_lock = Lock()

def get_model(model_name='gemini-1.5-flash'):
    """Get cached model instance"""
    global _model_cache, _model_lock
    
    with _model_lock:
        if model_name not in _model_cache:
            _model_cache[model_name] = genai.GenerativeModel(model_name)
        return _model_cache[model_name]

# Initialize Redis cache (fallback to in-memory if Redis not available)
try:
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    redis_client.ping()
    logger.info("Redis cache initialized successfully")
except:
    redis_client = None
    logger.warning("Redis not available, using in-memory cache")

# In-memory cache fallback
_memory_cache = {}
_cache_lock = Lock()

def cache_key(func_name: str, *args, **kwargs) -> str:
    """Generate cache key for function with arguments"""
    key_data = f"{func_name}:{str(args)}:{str(sorted(kwargs.items()))}"
    return hashlib.md5(key_data.encode()).hexdigest()

def cached_function(ttl: int = 3600):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = cache_key(func.__name__, *args, **kwargs)
            
            # Try Redis first
            if redis_client:
                try:
                    cached_result = redis_client.get(key)
                    if cached_result:
                        return pickle.loads(cached_result.encode('latin-1'))
                except Exception as e:
                    logger.warning(f"Redis cache error: {e}")
            
            # Fallback to memory cache
            with _cache_lock:
                if key in _memory_cache:
                    result, timestamp = _memory_cache[key]
                    if time.time() - timestamp < ttl:
                        return result
                    else:
                        del _memory_cache[key]
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            try:
                if redis_client:
                    redis_client.setex(key, ttl, pickle.dumps(result).decode('latin-1'))
                else:
                    with _cache_lock:
                        _memory_cache[key] = (result, time.time())
            except Exception as e:
                logger.warning(f"Caching error: {e}")
            
            return result
        return wrapper
    return decorator

# Optimized Rate Limiter
class OptimizedRateLimiter:
    """Optimized rate limiter with better performance and memory usage"""
    
    def __init__(self, max_calls_per_min=15, window_size_sec=60):
        self.max_calls_per_min = max_calls_per_min
        self.window_size_sec = window_size_sec
        self.calls = deque(maxlen=max_calls_per_min * 2)  # Fixed size deque
        self.lock = Lock()
        self.batch_size = 1
        self.failed_files = set()  # Use set for O(1) operations
        
    def set_batch_size(self, batch_size):
        """Set batch size and calculate optimal wait time"""
        with self.lock:
            self.batch_size = max(1, batch_size)
            
    def wait_if_needed(self, force_wait=False):
        """Optimized wait calculation"""
        with self.lock:
            current_time = time.time()
            
            # Remove old calls efficiently
            while self.calls and current_time - self.calls[0] > self.window_size_sec:
                self.calls.popleft()
                
            calls_remaining = self.max_calls_per_min - len(self.calls)
            
            if force_wait or calls_remaining < 3:
                wait_time = max(1, self.window_size_sec / self.max_calls_per_min)
                time.sleep(wait_time)
                return True
                
            return False
            
    def add_call(self):
        """Record API call"""
        with self.lock:
            self.calls.append(time.time())
            
    def add_failed_file(self, file_path):
        """Add failed file to set"""
        with self.lock:
            self.failed_files.add(file_path)
            
    def clear_failed_files(self):
        """Clear failed files"""
        with self.lock:
            self.failed_files.clear()
            
    def get_utilization(self):
        """Get current utilization percentage"""
        with self.lock:
            current_time = time.time()
            # Clean old calls
            while self.calls and current_time - self.calls[0] > self.window_size_sec:
                self.calls.popleft()
            return (len(self.calls) / self.max_calls_per_min) * 100

# Global rate limiter instance
rate_limiter = OptimizedRateLimiter()

# Optimized pattern matching
@lru_cache(maxsize=128)
def compile_pattern(pattern: str) -> re.Pattern:
    """Cache compiled regex patterns"""
    return re.compile(pattern, re.IGNORECASE | re.MULTILINE)

# Optimized text extraction
@contextmanager
def memory_management():
    """Context manager for memory cleanup"""
    try:
        yield
    finally:
        gc.collect()

@cached_function(ttl=1800)  # Cache for 30 minutes
def extract_text_from_pdf_cached(pdf_path: str, file_hash: str) -> str:
    """Cached version of PDF text extraction"""
    return extract_text_from_pdf_uncached(pdf_path)

def extract_text_from_pdf_uncached(pdf_path: str) -> str:
    """Optimized PDF text extraction"""
    text = ""
    
    with memory_management():
        try:
            # Try pdfplumber first (faster for text-based PDFs)
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                        
            # Extract tables if available
            table_text = extract_tables_from_pdf_cached(pdf_path)
            if table_text.strip():
                text += "\n\n" + table_text
                
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e}, falling back to OCR")
            
        # Fallback to OCR if no text found
        if not text.strip():
            text = extract_text_from_image_optimized(pdf_path)
            
    return text

@cached_function(ttl=1800)
def extract_tables_from_pdf_cached(pdf_path: str) -> str:
    """Cached table extraction"""
    table_text = ""
    
    with memory_management():
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    if tables:
                        for table_idx, table in enumerate(tables):
                            table_text += f"\n--- TABLE {i+1}.{table_idx+1} ---\n"
                            for row in table:
                                if row:
                                    formatted_row = [str(cell).strip() if cell else "" for cell in row]
                                    table_text += " | ".join(formatted_row) + "\n"
        except Exception as e:
            logger.error(f"Error extracting tables: {e}")
            
    return table_text

def extract_text_from_image_optimized(pdf_path: str) -> str:
    """Optimized OCR extraction with better resource management"""
    text = ""
    
    with memory_management():
        try:
            # Convert with optimized settings
            images = convert_from_path(
                pdf_path, 
                dpi=200,  # Reduced DPI for faster processing
                first_page=1,
                last_page=3,  # Limit pages for performance
                thread_count=2
            )
            
            # Process images in parallel
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = []
                for image in images:
                    future = executor.submit(process_image_ocr, image)
                    futures.append(future)
                
                for future in futures:
                    try:
                        text += future.result() + "\n"
                    except Exception as e:
                        logger.warning(f"OCR processing error: {e}")
                        
        except Exception as e:
            logger.error(f"Error in OCR extraction: {e}")
            
    return text

def process_image_ocr(image: Image.Image) -> str:
    """Process single image with OCR"""
    try:
        # Optimize image for OCR
        img_gray = image.convert('L')
        
        # Use optimized OCR settings
        text = pytesseract.image_to_string(
            img_gray,
            config='--psm 3 --oem 3 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz .,/:()-'
        )
        
        return text
        
    except Exception as e:
        logger.warning(f"OCR processing failed: {e}")
        return ""

@cached_function(ttl=3600)
def identify_invoice_pattern_cached(text: str) -> Tuple[str, float]:
    """Cached pattern identification"""
    # Simplified pattern matching for better performance
    upper_text = text.upper()
    
    # Fast pattern matching using simple string operations
    if 'BAGS' in upper_text and 'NET' in upper_text:
        return 'pattern_d', 0.85
    elif 'HSN' in upper_text and 'QUANTITY' in upper_text:
        return 'pattern_a', 0.8
    elif 'DESCRIPTION' in upper_text and 'RATE' in upper_text:
        return 'pattern_b', 0.7
    else:
        return 'generic', 0.6

def get_file_hash(file_path: str) -> str:
    """Get file hash for caching"""
    try:
        with open(file_path, 'rb') as f:
            # Read only first 8KB for speed
            content = f.read(8192)
            return hashlib.md5(content).hexdigest()
    except Exception:
        return str(int(time.time()))

# Optimized main processing function
def process_invoice_optimized(invoice_path: str, debug_mode=False) -> Dict[str, Any]:
    """
    Optimized invoice processing with caching and better performance
    """
    start_time = time.time()
    
    try:
        # Get file hash for caching
        file_hash = get_file_hash(invoice_path)
        
        # Check rate limit
        if rate_limiter.wait_if_needed():
            logger.info("Rate limit applied")
            
        # Extract text with caching
        text = extract_text_from_pdf_cached(invoice_path, file_hash)
        
        if not text.strip():
            return {
                'success': False,
                'error': 'No text could be extracted from the PDF',
                'processing_time': time.time() - start_time
            }
        
        # Identify pattern with caching
        pattern_key, confidence = identify_invoice_pattern_cached(text)
        
        # Process with AI (this is the expensive operation)
        rate_limiter.add_call()
        
        with memory_management():
            extraction_result = process_with_gemini_optimized(
                text, 
                pattern_key, 
                file_path=invoice_path
            )
        
        # Add metadata
        extraction_result['processing_time'] = time.time() - start_time
        extraction_result['pattern_confidence'] = confidence
        extraction_result['file_hash'] = file_hash
        
        return extraction_result
        
    except Exception as e:
        logger.error(f"Error processing invoice: {e}")
        return {
            'success': False,
            'error': str(e),
            'processing_time': time.time() - start_time
        }

def process_with_gemini_optimized(text: str, pattern_name: str = None, file_path: str = None) -> Dict[str, Any]:
    """
    Optimized Gemini processing with better error handling and caching
    """
    try:
        # Get cached model
        model = get_model()
        
        # Generate simplified prompt for better performance
        prompt = get_optimized_prompt(pattern_name, text)
        
        # Make API call
        response = model.generate_content(prompt)
        
        if not response.text:
            return {
                'success': False,
                'error': 'No response from AI model'
            }
            
        # Parse JSON response
        try:
            result = json.loads(response.text.strip())
            result['success'] = True
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing error: {e}")
            return {
                'success': False,
                'error': f'Invalid JSON response: {e}'
            }
            
    except Exception as e:
        logger.error(f"Gemini processing error: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def get_optimized_prompt(pattern_name: str, text: str) -> str:
    """Generate optimized prompt for better performance"""
    
    # Truncate text to reduce token usage
    max_text_length = 4000
    if len(text) > max_text_length:
        text = text[:max_text_length] + "..."
    
    prompt = f"""
Extract invoice data and return ONLY valid JSON:

{{
  "company_name": "seller company name",
  "invoice_number": "invoice number only",
  "invoice_date": "date",
  "fssai_number": "fssai number if available",
  "products": [
    {{
      "goods_description": "product name",
      "hsn_sac_code": "hsn code",
      "quantity": "quantity with unit",
      "weight": "weight with unit",
      "rate": "rate per unit",
      "amount": "total amount"
    }}
  ],
  "confidence_scores": {{
    "overall": 0.85,
    "company_name": 0.9,
    "invoice_number": 0.8,
    "fssai_number": 0.7,
    "invoice_date": 0.9,
    "products": 0.8
  }}
}}

Invoice text:
{text}
"""
    
    return prompt

# Batch processing for multiple invoices
def process_invoices_batch(invoice_paths: List[str], max_workers: int = 3) -> List[Dict[str, Any]]:
    """
    Process multiple invoices in parallel with optimized resource management
    """
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {
            executor.submit(process_invoice_optimized, path): path 
            for path in invoice_paths
        }
        
        for future in future_to_path:
            path = future_to_path[future]
            try:
                result = future.result()
                result['original_path'] = path
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing {path}: {e}")
                results.append({
                    'success': False,
                    'error': str(e),
                    'original_path': path
                })
    
    return results

# Backwards compatibility
def process_invoice(invoice_path: str, debug_mode=False) -> Dict[str, Any]:
    """Backwards compatible function"""
    return process_invoice_optimized(invoice_path, debug_mode)

# Cleanup function
def cleanup_cache():
    """Clean up memory cache"""
    global _memory_cache, _model_cache
    
    with _cache_lock:
        _memory_cache.clear()
        
    with _model_lock:
        _model_cache.clear()
        
    gc.collect()
    logger.info("Cache cleaned up")

# Health check function
def health_check() -> Dict[str, Any]:
    """System health check"""
    return {
        'status': 'healthy',
        'cache_size': len(_memory_cache),
        'model_cache_size': len(_model_cache),
        'rate_limiter_utilization': rate_limiter.get_utilization(),
        'redis_available': redis_client is not None
    }