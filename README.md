# Invoice AI - Intelligent Invoice Data Extraction System

A modern Python application that extracts structured data from PDF invoices using OCR and advanced machine learning techniques. The system processes invoices and extracts key information such as company name, invoice number, product details, and more with high accuracy and confidence scores.

## Features

- PDF invoice processing with OCR (Optical Character Recognition)
- Extraction of structured data from invoices:
  - Goods Description: Exact wording used for product description
  - HSN/SAC Code: Numerical HSN or SAC code for each product
  - Quantity: Numerical value representing the quantity
  - Weight: Weight with unit (e.g., kg, qtl, tons)
  - Rate: Cost per single unit
  - Amount: Total cost for all units
  - Company Name: Name of the company issuing the invoice
  - Invoice Number: Alphanumeric invoice number
  - FSSAI Number: Food Safety and Standards Authority of India license number
  - Date of Invoice: Invoice date in DD/MM/YYYY format
- Modern, responsive web UI with intuitive navigation
- Batch processing capabilities for multiple invoices
- Export functionality for extracted data (JSON, CSV, Excel)
- Comprehensive extraction history with search and filter options
- Confidence score indicators for extraction accuracy
- Real-time feedback with alert notifications

## Requirements

- Python 3.8 or higher
- Tesseract OCR engine (installed separately)
- Dependencies listed in requirements.txt

## Installation

1. Clone this repository or download the code
2. Set up a virtual environment:

```
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```
pip install -r requirements.txt
```

4. Download the spaCy language model:

```
python -m spacy download en_core_web_sm
```

5. Ensure Tesseract OCR is installed:
   - On macOS: `brew install tesseract`
   - On Ubuntu/Debian: `sudo apt-get install tesseract-ocr`
   - On Windows: Download installer from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)

## Usage

1. Start the application:

```
python app.py
```

2. Open a web browser and navigate to: `http://127.0.0.1:3000`

3. Use the web interface to:
   - Upload PDF invoices
   - View extraction results
   - Export data in your preferred format
   - Access previous extraction results

## Project Structure

- `app.py`: Main Flask application with API endpoints
- `invoice_processor.py`: Core logic for invoice data extraction
- `templates/`: HTML templates for the web UI
- `static/`: 
  - `css/`: Stylesheets for the application
  - `js/`: JavaScript modules for frontend functionality:
    - `app.js`: Main application logic
    - `main.js`: Core UI functionality
    - `results.js`: Results handling and display
  - `img/`: Images and icons
- `uploads/`: Temporary storage for uploaded invoices
- `results/`: Storage for extracted data in JSON format

## How It Works

1. The uploaded PDF is converted to high-resolution images
2. OCR is performed on the images to extract text with spatial information
3. Advanced rule-based algorithms and machine learning techniques analyze the text
4. Template matching identifies known invoice formats for improved accuracy
5. Structured data is extracted with confidence scores for each field
6. Results are presented in an intuitive UI with options to export or further process

## Capabilities and Limitations

### Capabilities
- Processes PDF invoices with high accuracy
- Detects and extracts tabular data for product listings
- Provides confidence scores to indicate extraction reliability
- Supports batch processing for multiple invoices
- Maintains extraction history for future reference

### Limitations
- Currently supports PDF invoices only (image support coming soon)
- Extraction accuracy depends on the quality and structure of the invoice
- Fields that cannot be accurately extracted are marked with low confidence scores
- Processing very large batch uploads may require additional system resources

## Recent Updates

- Enhanced UI with improved navigation and alerts system
- Added confidence score visualization for extraction quality
- Improved extraction history display and management
- Fixed issues with file handling and extraction display
- Optimized backend for better performance and reliability
- Added transition effects for better user experience

## License

This project is licensed under the MIT License - see the LICENSE file for details.
