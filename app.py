from flask import Flask, render_template, request, jsonify, send_file, make_response
import pandas as pd
from io import BytesIO
import os
import json
import pandas as pd
from datetime import datetime
import time
from werkzeug.utils import secure_filename
from invoice_processor import process_invoice, rate_limiter

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'invoice' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    # Get list of files (for single file upload, this is still a list with one item)
    files = request.files.getlist('invoice')
    
    if not files or files[0].filename == '':
        return jsonify({'error': 'No selected files'}), 400
    
    # Clear any previously failed files
    rate_limiter.clear_failed_files()
    
    # Set the batch size for rate limiting based on number of files
    batch_size = len(files)
    rate_limiter.set_batch_size(batch_size)
    
    # Process each file and collect results
    all_results = []
    success_count = 0
    rate_limited_files = []
    
    for i, file in enumerate(files):
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Log progress
            print(f"Processing file {i+1}/{len(files)}: {filename}")
            
            try:
                # Process the invoice
                extraction_result = process_invoice(filepath)
                
                # Check if processing failed due to rate limiting
                if not extraction_result['success'] and extraction_result.get('rate_limited', False):
                    rate_limited_files.append({
                        'filepath': filepath,
                        'filename': filename
                    })
                    all_results.append({
                        'success': False,
                        'filename': filename,
                        'error': extraction_result['error'],
                        'rate_limited': True
                    })
                    continue
                
                # Add timestamp and original filename
                extraction_result['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                extraction_result['original_filename'] = filename
                
                # Save results to a unique JSON file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                results_filename = f"result_{timestamp}_{filename.split('.')[0]}.json"
                results_path = os.path.join('results', results_filename)
                
                # Ensure results directory exists
                os.makedirs('results', exist_ok=True)
                
                with open(results_path, 'w') as f:
                    json.dump(extraction_result, f, indent=4)
                
                # Structure the result for frontend consumption
                result_entry = {
                    'filename': filename,
                    'result': {
                        'company_name': extraction_result.get('company_name', '-'),
                        'invoice_number': extraction_result.get('invoice_number', '-'),
                        'invoice_date': extraction_result.get('invoice_date', '-'),
                        'fssai_number': extraction_result.get('fssai_number', '-'),
                        'products': extraction_result.get('products', []),
                        'confidence_scores': extraction_result.get('confidence_scores', {
                            'overall': 0,
                            'company_name': 0,
                            'invoice_number': 0,
                            'fssai_number': 0,
                            'invoice_date': 0,
                            'products': 0
                        }),
                        'template_used': extraction_result.get('template_used', 'unknown')
                    }
                }
                
                # Add to results collection
                all_results.append(result_entry)
                success_count += 1
            
            except Exception as e:
                all_results.append({
                    'success': False,
                    'filename': filename,
                    'error': str(e)
                })
        else:
            all_results.append({
                'success': False,
                'filename': file.filename,
                'error': 'File type not allowed'
            })
    
    # Handle retry for rate-limited files if any
    if rate_limited_files:
        retry_results = retry_rate_limited_files(rate_limited_files)
        
        # Update all_results with retry results
        for retry_result in retry_results:
            # Find and replace the original failed result
            for i, result in enumerate(all_results):
                if result.get('filename') == retry_result.get('filename') and result.get('rate_limited', False):
                    all_results[i] = retry_result
                    if retry_result.get('success', False):
                        success_count += 1
                    break
    
    # Return summary of all processing results
    return jsonify({
        'success': success_count > 0,
        'total_files': len(files),
        'success_count': success_count,
        'rate_limited_count': len(rate_limited_files),
        'api_utilization': rate_limiter.get_utilization(),
        'results': all_results
    })


def retry_rate_limited_files(failed_files, max_retries=3):
    """
    Retry processing for files that failed due to rate limiting.
    
    Args:
        failed_files: List of dictionaries with filepath and filename
        max_retries: Maximum number of retry attempts
        
    Returns:
        List of results from retry attempts
    """
    if not failed_files:
        return []
    
    retry_results = []
    retry_batch_size = len(failed_files)
    
    # Adjust rate limiter for retry batch
    rate_limiter.set_batch_size(retry_batch_size)
    
    # Wait for a cooldown period before retrying (60 seconds = 1 minute window reset)
    cooldown = 60
    print(f"Rate limit exceeded. Waiting {cooldown} seconds before retrying {retry_batch_size} files...")
    time.sleep(cooldown)
    
    for retry_file in failed_files:
        filepath = retry_file['filepath']
        filename = retry_file['filename']
        
        print(f"Retrying rate-limited file: {filename}")
        
        # Process with increased wait times
        try:
            # Force wait between retries to avoid hitting limits again
            rate_limiter.wait_if_needed(force_wait=True)
            
            # Retry processing
            extraction_result = process_invoice(filepath)
            
            if extraction_result['success']:
                # Add timestamp and original filename
                extraction_result['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                extraction_result['original_filename'] = filename
                extraction_result['retry_success'] = True
                
                # Save results to a unique JSON file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                results_filename = f"result_{timestamp}_{filename.split('.')[0]}_retry.json"
                results_path = os.path.join('results', results_filename)
                
                with open(results_path, 'w') as f:
                    json.dump(extraction_result, f, indent=4)
                
                # Structure the result for frontend consumption
                result_entry = {
                    'filename': filename,
                    'success': True,
                    'retry_success': True,
                    'result': {
                        'company_name': extraction_result.get('company_name', '-'),
                        'invoice_number': extraction_result.get('invoice_number', '-'),
                        'invoice_date': extraction_result.get('invoice_date', '-'),
                        'fssai_number': extraction_result.get('fssai_number', '-'),
                        'products': extraction_result.get('products', []),
                        'confidence_scores': extraction_result.get('confidence_scores', {
                            'overall': 0,
                            'company_name': 0,
                            'invoice_number': 0,
                            'fssai_number': 0,
                            'invoice_date': 0,
                            'products': 0
                        }),
                        'template_used': extraction_result.get('template_used', 'unknown')
                    }
                }
                
                retry_results.append(result_entry)
            else:
                # Still failed after retry
                retry_results.append({
                    'success': False,
                    'filename': filename,
                    'error': extraction_result.get('error', 'Retry failed'),
                    'retry_failed': True
                })
        
        except Exception as e:
            retry_results.append({
                'success': False,
                'filename': filename,
                'error': f"Retry error: {str(e)}",
                'retry_failed': True
            })
    
    return retry_results

@app.route('/download/<filename>')
def download_results(filename):
    filepath = os.path.join('results', filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    # Convert to CSV or Excel based on query parameter
    format_type = request.args.get('format', 'csv')  # Default to CSV instead of JSON
    
    # Load the JSON data
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Create a properly formatted DataFrame with the specified columns
    rows = []
    
    # Get invoice metadata
    company_name = data.get('company_name', 'N/A')
    invoice_number = data.get('invoice_number', 'N/A')
    fssai_number = data.get('fssai_number', 'N/A')
    invoice_date = data.get('invoice_date', 'N/A')
    
    # Process each product as a separate row
    if 'products' in data and data['products']:
        for product in data['products']:
            row = {
                'Goods Description': product.get('goods_description', 'N/A'),
                'HSN/SAC Code': product.get('hsn_sac_code', 'N/A'),
                'Quantity': product.get('quantity', 'N/A'),
                'Weight': product.get('weight', 'N/A'),
                'Rate': product.get('rate', 'N/A'),
                'Amount': product.get('amount', 'N/A'),
                'Company Name': company_name,
                'Invoice Number': invoice_number,
                'FSSAI Number': fssai_number,
                'Date of Invoice': invoice_date
            }
            rows.append(row)
    else:
        # If no products, create at least one row with invoice metadata
        rows.append({
            'Goods Description': 'N/A',
            'HSN/SAC Code': 'N/A',
            'Quantity': 'N/A',
            'Weight': 'N/A',
            'Rate': 'N/A',
            'Amount': 'N/A',
            'Company Name': company_name,
            'Invoice Number': invoice_number,
            'FSSAI Number': fssai_number,
            'Date of Invoice': invoice_date
        })
    
    # Create DataFrame with columns in the specified order
    columns = [
        'Goods Description', 'HSN/SAC Code', 'Quantity', 'Weight', 'Rate', 'Amount',
        'Company Name', 'Invoice Number', 'FSSAI Number', 'Date of Invoice'
    ]
    df = pd.DataFrame(rows, columns=columns)
    
    # Generate appropriate filename with proper extension
    base_filename = filename.split('.')[0]
    
    if format_type == 'csv':
        output_filename = f"{base_filename}.csv"
        output_path = os.path.join('results', output_filename)
        df.to_csv(output_path, index=False)
    elif format_type == 'excel':
        output_filename = f"{base_filename}.xlsx"
        output_path = os.path.join('results', output_filename)
        
        # Use openpyxl with additional formatting
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Invoice Data')
            
            # Get the workbook and the worksheet
            workbook = writer.book
            worksheet = writer.sheets['Invoice Data']
            
            # Auto-adjust column widths
            for idx, col in enumerate(df.columns):
                # Find the maximum length of the data in each column
                max_len = max(
                    df[col].astype(str).map(len).max(),  # Max length of data
                    len(str(col))  # Length of column name
                ) + 2  # Add some padding
                
                # Convert to Excel column letter
                col_letter = chr(65 + idx) if idx < 26 else chr(64 + idx // 26) + chr(65 + idx % 26)
                worksheet.column_dimensions[col_letter].width = max_len
    else:
        return jsonify({'error': 'Unsupported format'}), 400
    
    return send_file(output_path, as_attachment=True)

@app.route('/results')
def list_results():
    if not os.path.exists('results'):
        return jsonify([])
    
    files = [f for f in os.listdir('results') if f.endswith('.json')]
    return jsonify(files)

@app.route('/results/<filename>')
def get_result_file(filename):
    """Serve an individual result file by filename"""
    file_path = os.path.join('results', filename)
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/extraction_history')
def extraction_history():
    """Get a list of all previously processed invoices"""
    print("Extraction history endpoint called")
    # Set headers to prevent caching
    response = make_response()
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    if not os.path.exists('results'):
        print("Results directory does not exist")
        os.makedirs('results', exist_ok=True)
        return jsonify({'extractions': []})
    
    extractions = []
    
    # Get list of all result files
    result_files = os.listdir('results')
    print(f"Found {len(result_files)} files in results directory")
    result_files.sort(reverse=True)  # Sort newest first based on filename
    
    for filename in result_files:
        if not filename.endswith('.json'):
            continue
        
        file_path = os.path.join('results', filename)
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Add timestamp if missing
            if 'timestamp' not in data:
                # Try to extract timestamp from filename or use file modification time
                try:
                    file_mtime = os.path.getmtime(file_path)
                    timestamp = datetime.datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')
                except:
                    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                data['timestamp'] = timestamp
            
            # Create a summary entry for this extraction
            entry = {
                'id': filename.replace('.json', ''),  # Use filename as ID without extension
                'filename': data.get('original_filename', filename.replace('.json', '')),
                'timestamp': data.get('timestamp', '-'),
                'company_name': data.get('company_name', 'Unknown'),
                'invoice_number': data.get('invoice_number', '-'),
                'invoice_date': data.get('invoice_date', '-'),
                'template_used': data.get('template_used', 'Default'),
                'confidence_overall': data.get('confidence_scores', {}).get('overall', 0)
            }
            
            extractions.append(entry)
        except Exception as e:
            # Skip files that can't be processed
            app.logger.error(f"Error loading {filename}: {str(e)}")
    
    print(f"Returning {len(extractions)} extractions")
    # Return in the format expected by the frontend
    result = {'extractions': extractions}
    return jsonify(result)

@app.route('/extraction/<extraction_id>')
def get_extraction(extraction_id):
    """Get details for a specific extraction by ID"""
    print(f"Getting extraction details for ID: {extraction_id}")
    
    # Try different file paths with and without .json extension
    file_path = os.path.join('results', extraction_id)
    if not os.path.exists(file_path):
        # Try with .json extension
        file_path_with_ext = os.path.join('results', f"{extraction_id}.json")
        if os.path.exists(file_path_with_ext):
            file_path = file_path_with_ext
        else:
            # List files in results directory for debugging
            print(f"File not found: {file_path}")
            print(f"File with extension not found: {file_path_with_ext}")
            print(f"Files in results directory: {os.listdir('results') if os.path.exists('results') else 'results dir not found'}")
            
            # Try to find a file that starts with the given ID
            if os.path.exists('results'):
                for filename in os.listdir('results'):
                    if filename.startswith(extraction_id):
                        file_path = os.path.join('results', filename)
                        print(f"Found matching file: {filename}")
                        break
                else:
                    return jsonify({'error': 'Extraction not found'}), 404
            else:
                return jsonify({'error': 'Extraction not found'}), 404
    
    try:
        print(f"Opening file: {file_path}")
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        print(f"Loaded data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dictionary'}")
        
        # Ensure we have the correct structure
        result = {
            'filename': data.get('original_filename', extraction_id),
            'result': {
                'company_name': data.get('company_name', '-'),
                'invoice_number': data.get('invoice_number', '-'),
                'invoice_date': data.get('invoice_date', '-'),
                'fssai_number': data.get('fssai_number', '-'),
                'products': data.get('products', []),
                'confidence_scores': data.get('confidence_scores', {
                    'overall': 0,
                    'company_name': 0,
                    'invoice_number': 0,
                    'fssai_number': 0,
                    'invoice_date': 0,
                    'products': 0
                }),
                'template_used': data.get('template_used', 'unknown')
            }
        }
        
        print(f"Returning result with keys: {list(result.keys())}")
        return jsonify(result)
        
    except Exception as e:
        print(f"Error getting extraction: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/download/excel', methods=['POST'])
def download_excel():
    try:
        # Get the JSON data from the request
        data = request.json
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Create a pandas DataFrame for the products
        products_df = None
        if 'products' in data and data['products']:
            products_df = pd.DataFrame(data['products'])
        else:
            products_df = pd.DataFrame(columns=['goods_description', 'hsn_sac_code', 'quantity', 'weight', 'rate', 'amount'])
        
        # Create a DataFrame for the invoice metadata
        metadata = {
            'Field': ['Company Name', 'Invoice Number', 'Invoice Date', 'FSSAI Number'],
            'Value': [
                data.get('company_name', ''),
                data.get('invoice_number', ''),
                data.get('invoice_date', ''),
                data.get('fssai_number', '')
            ]
        }
        metadata_df = pd.DataFrame(metadata)
        
        # Create an Excel file with both DataFrames using pandas ExcelWriter
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            metadata_df.to_excel(writer, sheet_name='Invoice Details', index=False)
            products_df.to_excel(writer, sheet_name='Products', index=False)
            
            # Get workbook and worksheet objects for formatting
            workbook = writer.book
            
            # Format Invoice Details sheet
            invoice_worksheet = writer.sheets['Invoice Details']
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#D7E4BC',
                'border': 1
            })
            
            # Apply header format
            for col_num, value in enumerate(metadata_df.columns.values):
                invoice_worksheet.write(0, col_num, value, header_format)
            
            # Format Products sheet
            products_worksheet = writer.sheets['Products']
            for col_num, value in enumerate(products_df.columns.values):
                products_worksheet.write(0, col_num, value, header_format)
                
            # Set column widths
            invoice_worksheet.set_column('A:A', 20)
            invoice_worksheet.set_column('B:B', 25)
            products_worksheet.set_column('A:A', 40)  # goods description
            products_worksheet.set_column('B:F', 15)  # other columns
        
        # Reset the pointer of the buffer to the beginning
        output.seek(0)
        
        # Create a response with the Excel file
        filename = f"invoice_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f"Error generating Excel file: {str(e)}")
        return jsonify({'error': f'Failed to generate Excel file: {str(e)}'}), 500

@app.route('/recent_uploads')
def recent_uploads():
    """Get a list of recent uploads with detailed information"""
    print("Recent uploads endpoint called")
    # Set headers to prevent caching
    response = make_response()
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    if not os.path.exists('results'):
        print("Results directory does not exist")
        os.makedirs('results', exist_ok=True)
        return jsonify({'uploads': []})
    
    uploads = []
    
    # Get list of all result files
    result_files = os.listdir('results')
    print(f"Found {len(result_files)} files in results directory")
    result_files.sort(reverse=True)  # Sort newest first based on filename
    
    for filename in result_files:
        if not filename.endswith('.json'):
            continue
        
        file_path = os.path.join('results', filename)
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Create a summary entry for this upload
            entry = {
                'id': filename.replace('.json', ''),
                'filename': data.get('original_filename', filename.replace('.json', '')),
                'vendor_name': data.get('company_name', 'Unknown'),
                'invoice_number': data.get('invoice_number', '-'),
                'invoice_date': data.get('invoice_date', '-'),
            }
            uploads.append(entry)
        except Exception as e:
            # Skip files that can't be processed
            app.logger.error(f"Error loading {filename}: {str(e)}")
    
    print(f"Returning {len(uploads)} uploads")
    # Return in the format expected by the frontend
    result = {'uploads': uploads}
    return jsonify(result)

@app.route('/dashboard_stats')
def dashboard_stats():
    """Provide real-time statistics for the dashboard cards"""
    # Calculate total invoices
    total_invoices = sum(1 for filename in os.listdir('results') if filename.endswith('.json'))
    
    # Calculate success rate
    successful_extractions = 0
    total_extractions = 0
    for filename in os.listdir('results'):
        if filename.endswith('.json'):
            with open(os.path.join('results', filename), 'r') as f:
                data = json.load(f)
                total_extractions += 1
                if data.get('success', False):
                    successful_extractions += 1
    success_rate = (successful_extractions / total_extractions * 100) if total_extractions > 0 else 0

    # Calculate average processing time
    total_processing_time = sum(data.get('processing_time', 0) for filename in os.listdir('results') if filename.endswith('.json') for data in [json.load(open(os.path.join('results', filename), 'r'))])
    avg_processing_time = (total_processing_time / total_extractions) if total_extractions > 0 else 0

    # Load previous month's stats
    try:
        with open('monthly_stats.json', 'r') as f:
            previous_stats = json.load(f)
    except FileNotFoundError:
        previous_stats = {'totalInvoices': 0, 'successRate': 0, 'avgProcessingTime': 0}

    # Calculate percentage changes
    change_total_invoices = ((total_invoices - previous_stats['totalInvoices']) / previous_stats['totalInvoices'] * 100) if previous_stats['totalInvoices'] > 0 else 0
    change_success_rate = ((success_rate - previous_stats['successRate']) / previous_stats['successRate'] * 100) if previous_stats['successRate'] > 0 else 0
    change_avg_processing_time = ((avg_processing_time - previous_stats['avgProcessingTime']) / previous_stats['avgProcessingTime'] * 100) if previous_stats['avgProcessingTime'] > 0 else 0

    # Save current stats for next month
    with open('monthly_stats.json', 'w') as f:
        json.dump({'totalInvoices': total_invoices, 'successRate': success_rate, 'avgProcessingTime': avg_processing_time}, f)

    stats = {
        'totalInvoices': total_invoices,
        'successRate': success_rate,
        'avgProcessingTime': avg_processing_time,
        'changeTotalInvoices': change_total_invoices,
        'changeSuccessRate': change_success_rate,
        'changeAvgProcessingTime': change_avg_processing_time
    }
    return jsonify(stats)

if __name__ == '__main__':
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Invoice AI Processing System')
    parser.add_argument('--port', type=int, default=3000, help='Port to run the server on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to run the server on')
    args = parser.parse_args()
    
    app.run(host=args.host, port=args.port, debug=True)
