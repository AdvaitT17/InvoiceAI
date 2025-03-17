# Invoice AI - Data Extraction System

A Python application that extracts structured data from PDF invoices using OCR and machine learning techniques. The application processes invoices and extracts key information such as company name, invoice number, product details, and more.

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
- Modern web UI for uploading invoices and viewing results
- Export functionality for extracted data (JSON, CSV, Excel)
- Historical results tracking

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

2. Open a web browser and navigate to: `http://127.0.0.1:5000`

3. Use the web interface to:
   - Upload PDF invoices
   - View extraction results
   - Export data in your preferred format
   - Access previous extraction results

## Project Structure

- `app.py`: Main Flask application
- `invoice_processor.py`: Core logic for invoice data extraction
- `templates/`: HTML templates for the web UI
- `static/`: CSS and JavaScript files
- `uploads/`: Temporary storage for uploaded invoices
- `results/`: Storage for extracted data

## How It Works

1. The uploaded PDF is converted to images
2. OCR is performed on the images to extract text
3. Rule-based and machine learning techniques are applied to identify key data points
4. Structured data is extracted and presented to the user

## Limitations

- Currently supports PDF invoices only
- Extraction accuracy depends on the quality and structure of the invoice
- Fields that cannot be accurately extracted are marked as "N/A"

## License

This project is licensed under the MIT License - see the LICENSE file for details.
