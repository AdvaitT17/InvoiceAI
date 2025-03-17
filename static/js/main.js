document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const uploadSection = document.getElementById('upload-section');
    const resultsSection = document.getElementById('results-section');
    const previousResultsSection = document.getElementById('previous-results-section');
    const uploadCard = document.getElementById('uploadCard');
    const uploadArea = document.getElementById('uploadArea');
    const uploadPrompt = document.getElementById('uploadPrompt');
    const uploadPreview = document.getElementById('uploadPreview');
    const uploadProgress = document.getElementById('uploadProgress');
    const fileInput = document.getElementById('fileInput');
    const browseButton = document.getElementById('browseButton');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const uploadButton = document.getElementById('uploadButton');
    const cancelButton = document.getElementById('cancelButton');
    const resultCard = document.getElementById('resultCard');
    const batchResultCard = document.getElementById('batchResultCard');
    const processAnotherBtn = document.getElementById('processAnotherBtn');
    const processBatchAnotherBtn = document.getElementById('processBatchAnotherBtn');
    const backToBatchBtn = document.getElementById('backToBatchBtn');
    const navLinks = document.querySelectorAll('.nav-link');
    const sections = document.querySelectorAll('.section');
    const previousResultsTableBody = document.getElementById('previousResultsTableBody');
    const noResultsMessage = document.getElementById('noResultsMessage');
    const exportButtons = document.querySelectorAll('.export-btn');
    
    // Current result file name (for export functionality)
    let currentResultFileName = '';
    
    // Navigation Tabs
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Remove active class from all tabs and sections
            navLinks.forEach(tab => tab.classList.remove('active'));
            sections.forEach(section => section.classList.remove('active'));
            
            // Add active class to clicked tab
            this.classList.add('active');
            
            // Get target section ID
            const targetId = this.getAttribute('href').substring(1);
            
            // Show corresponding section
            document.getElementById(targetId).classList.add('active');
            
            // Reset UI state based on section
            if (targetId === 'upload-section') {
                // Hide result cards when navigating to upload section
                resultCard.style.display = 'none';
                batchResultCard.style.display = 'none';
                uploadCard.style.display = 'block';
                resetUploadArea();
            } else if (targetId === 'previous-results-section') {
                // Load previous results if navigating to previous results tab
                loadPreviousResults();
            }
        });
    });
    
    // File Upload - Browse Button
    browseButton.addEventListener('click', function() {
        fileInput.click();
    });
    
    // File Upload - File Selected
    fileInput.addEventListener('change', function() {
        handleFileSelection(this.files);
    });
    
    // File Upload - Drag and Drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        uploadArea.addEventListener(eventName, function() {
            uploadArea.classList.add('dragging');
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, function() {
            uploadArea.classList.remove('dragging');
        }, false);
    });
    
    uploadArea.addEventListener('drop', function(e) {
        const files = e.dataTransfer.files;
        handleFileSelection(files);
    }, false);
    
    // Handle file selection
    function handleFileSelection(files) {
        if (files.length > 0) {
            // Display file info
            if (files.length === 1) {
                const file = files[0];
                // Check if file is PDF
                if (file.type !== 'application/pdf') {
                    showAlert('Please select PDF files only', 'danger');
                    return;
                }
                
                fileName.textContent = file.name;
                fileSize.textContent = formatFileSize(file.size);
                document.getElementById('fileCount').textContent = '';
            } else {
                // Multiple files selected
                let validFiles = 0;
                let totalSize = 0;
                
                // Count valid PDF files
                for (let i = 0; i < files.length; i++) {
                    if (files[i].type === 'application/pdf') {
                        validFiles++;
                        totalSize += files[i].size;
                    }
                }
                
                if (validFiles === 0) {
                    showAlert('Please select PDF files only', 'danger');
                    return;
                }
                
                fileName.textContent = `${validFiles} files selected`;
                fileSize.textContent = formatFileSize(totalSize);
                document.getElementById('fileCount').textContent = `${validFiles} of ${files.length} valid PDF files will be processed`;
                
                // Alert if some files were invalid
                if (validFiles < files.length) {
                    showAlert(`${files.length - validFiles} files were ignored because they are not PDFs`, 'warning');
                }
            }
            
            // Show preview, hide prompt
            uploadPrompt.style.display = 'none';
            uploadPreview.style.display = 'block';
            
            // Store files reference for upload
            uploadButton.files = files;
        }
    }
    
    // Cancel button
    cancelButton.addEventListener('click', function() {
        resetUploadArea();
    });
    
    // Reset upload area
    function resetUploadArea() {
        uploadPrompt.style.display = 'block';
        uploadPreview.style.display = 'none';
        uploadProgress.style.display = 'none';
        fileInput.value = '';
    }
    
    // Upload button
    uploadButton.addEventListener('click', function() {
        if (!this.files || this.files.length === 0) return;
        
        // Show progress, hide preview
        uploadPreview.style.display = 'none';
        uploadProgress.style.display = 'block';
        
        // Create form data
        const formData = new FormData();
        
        // Add all PDF files to form data
        let validFilesAdded = 0;
        for (let i = 0; i < this.files.length; i++) {
            if (this.files[i].type === 'application/pdf') {
                formData.append('invoice', this.files[i]);
                validFilesAdded++;
            }
        }
        
        if (validFilesAdded === 0) {
            showAlert('No valid PDF files to upload', 'danger');
            uploadProgress.style.display = 'none';
            resetUploadArea();
            return;
        }
        
        // Send files to server
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || 'Error processing invoices');
                });
            }
            return response.json();
        })
        .then(data => {
            // Hide progress
            uploadProgress.style.display = 'none';
            
            // Check if any invoices were processed successfully
            if (data.success_count > 0) {
                // If only one file was processed, show its results
                if (data.success_count === 1 && data.results.length === 1 && data.results[0].success) {
                    // Store result filename for the single invoice
                    currentResultFileName = data.results[0].filename;
                    
                    // Display results for the single invoice
                    displayResults(data.results[0]);
                } else {
                    // Multiple invoices processed, show batch summary
                    displayBatchResults(data);
                }
            } else {
                // No invoices were processed successfully
                showAlert('Failed to process any invoices. Please check file formats.', 'danger');
                resetUploadArea();
            }
        })
        .catch(error => {
            uploadProgress.style.display = 'none';
            showAlert(error.message, 'danger');
            resetUploadArea();
        });
    });
    
    // Display results
    function displayResults(results) {
        // Hide upload section and show results section
        uploadSection.classList.remove('active');
        resultsSection.classList.add('active');
        
        // Update navigation tab visibility
        document.querySelectorAll('.nav-link').forEach(tab => tab.classList.remove('active'));
        document.getElementById('upload-tab').classList.add('active');
        
        // Show result card
        resultCard.style.display = 'block';
        
        // Set basic info
        document.getElementById('resultCompanyName').textContent = results.company_name;
        document.getElementById('resultInvoiceNumber').textContent = results.invoice_number;
        document.getElementById('resultInvoiceDate').textContent = results.invoice_date;
        document.getElementById('resultFssaiNumber').textContent = results.fssai_number;
        
        // Clear products table
        const productsTableBody = document.getElementById('productsTableBody');
        productsTableBody.innerHTML = '';
        
        // Add products
        if (results.products && results.products.length > 0) {
            results.products.forEach(product => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${product.goods_description}</td>
                    <td>${product.hsn_sac_code}</td>
                    <td>${product.quantity}</td>
                    <td>${product.weight}</td>
                    <td>${product.rate}</td>
                    <td>${product.amount}</td>
                `;
                productsTableBody.appendChild(row);
            });
        } else {
            // No products found
            const row = document.createElement('tr');
            row.innerHTML = `
                <td colspan="6" class="text-center">No product details found in invoice</td>
            `;
            productsTableBody.appendChild(row);
        }
    }
    
    // Display batch processing results
    function displayBatchResults(data) {
        // Hide upload section and show results section
        uploadSection.classList.remove('active');
        resultsSection.classList.add('active');
        
        // Update navigation tab visibility
        document.querySelectorAll('.nav-link').forEach(tab => tab.classList.remove('active'));
        document.getElementById('upload-tab').classList.add('active');
        
        // Set basic info in the batch result card
        document.getElementById('batchSuccessCount').textContent = `${data.success_count} invoice(s)`;
        document.getElementById('batchTotalCount').textContent = `${data.total_files} invoice(s)`;
        
        // Clear batch results table
        const batchResultsTableBody = document.getElementById('batchResultsTableBody');
        batchResultsTableBody.innerHTML = '';
        
        // Add each result to the table
        data.results.forEach(result => {
            const row = document.createElement('tr');
            
            // Set row class based on success status
            if (!result.success) {
                row.classList.add('table-danger');
            }
            
            const originalFilename = result.original_filename || 'Unknown';
            const company = result.success ? (result.company_name || 'N/A') : 'N/A';
            const invoiceNum = result.success ? (result.invoice_number || 'N/A') : 'N/A';
            const invoiceDate = result.success ? (result.invoice_date || 'N/A') : 'N/A';
            const status = result.success ? 
                '<span class="badge bg-success">Success</span>' : 
                `<span class="badge bg-danger">Failed</span>`;
            
            // Add action buttons based on success status
            let actions = '';
            if (result.success) {
                actions = `
                    <button class="btn btn-sm btn-primary view-result-btn" data-filename="${result.filename}">
                        <i class="bi bi-eye"></i> View
                    </button>
                    <div class="dropdown d-inline-block ms-1">
                        <button class="btn btn-sm btn-success dropdown-toggle" type="button" data-bs-toggle="dropdown">
                            <i class="bi bi-download"></i>
                        </button>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item download-btn" data-format="csv" data-filename="${result.filename}" href="#">CSV</a></li>
                            <li><a class="dropdown-item download-btn" data-format="excel" data-filename="${result.filename}" href="#">Excel</a></li>
                        </ul>
                    </div>
                `;
            } else {
                actions = `<span class="text-danger">${result.error || 'Processing error'}</span>`;
            }
            
            row.innerHTML = `
                <td>${originalFilename}</td>
                <td>${company}</td>
                <td>${invoiceNum}</td>
                <td>${invoiceDate}</td>
                <td>${status}</td>
                <td>${actions}</td>
            `;
            
            batchResultsTableBody.appendChild(row);
        });
        
        // Show the batch result card
        batchResultCard.style.display = 'block';
        
        // Add event listeners for view buttons
        document.querySelectorAll('.view-result-btn').forEach(button => {
            button.addEventListener('click', function() {
                const filename = this.getAttribute('data-filename');
                viewInvoiceResult(filename);
            });
        });
        
        // Add event listeners for download buttons
        document.querySelectorAll('.download-btn').forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                const format = this.getAttribute('data-format');
                const filename = this.getAttribute('data-filename');
                window.location.href = `/download/${filename}?format=${format}`;
            });
        });
        
        // Reload the previous results list to show new results (in background)
        loadPreviousResults();
    }
    
    // View a specific invoice result
    function viewInvoiceResult(filename) {
        fetch(`/results/${filename}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to load invoice data');
                }
                return response.json();
            })
            .then(data => {
                // Hide batch result card but remember we came from it
                batchResultCard.style.display = 'none';
                
                // Show back button
                backToBatchBtn.style.display = 'block';
                
                // Store current filename for export buttons
                currentResultFileName = filename;
                
                // Display the results
                displayResults(data);
            })
            .catch(error => {
                showAlert(error.message, 'danger');
            });
    }
    
    // Back to batch results button
    backToBatchBtn.addEventListener('click', function() {
        // Hide individual result view
        resultCard.style.display = 'none';
        backToBatchBtn.style.display = 'none';
        
        // Show batch results again
        batchResultCard.style.display = 'block';
    });
    
    // Process another invoice button
    processAnotherBtn.addEventListener('click', function() {
        resultCard.style.display = 'none';
        backToBatchBtn.style.display = 'none';
        
        // Switch back to upload section
        sections.forEach(section => section.classList.remove('active'));
        uploadSection.classList.add('active');
        uploadCard.style.display = 'block';
        
        // Update tab selection
        navLinks.forEach(tab => tab.classList.remove('active'));
        document.getElementById('upload-tab').classList.add('active');
        
        resetUploadArea();
    });
    
    // Process another batch button
    processBatchAnotherBtn.addEventListener('click', function() {
        batchResultCard.style.display = 'none';
        
        // Switch back to upload section
        sections.forEach(section => section.classList.remove('active'));
        uploadSection.classList.add('active');
        uploadCard.style.display = 'block';
        
        // Update tab selection
        navLinks.forEach(tab => tab.classList.remove('active'));
        document.getElementById('upload-tab').classList.add('active');
        
        resetUploadArea();
    });
    
    // Export buttons
    exportButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            
            if (!currentResultFileName) {
                showAlert('No data available to export', 'warning');
                return;
            }
            
            const format = this.getAttribute('data-format');
            window.location.href = `/download/${currentResultFileName}?format=${format}`;
        });
    });
    
    // Load previous results
    function loadPreviousResultsOld() {
        console.log('Note: Using deprecated loadPreviousResultsOld in main.js');
        fetch('/results')
            .then(response => response.json())
            .then(files => {
                // Clear table
                previousResultsTableBody.innerHTML = '';
                
                if (files.length > 0) {
                    // Sort files by timestamp (descending)
                    files.sort().reverse();
                    
                    // Add files to table
                    files.forEach(file => {
                        // Extract date from filename (format: result_YYYYMMDD_HHMMSS_filename.json)
                        let dateStr = 'Unknown date';
                        const match = file.match(/result_(\d{8})_(\d{6})_/);
                        
                        if (match) {
                            const date = match[1];
                            const time = match[2];
                            dateStr = `${date.slice(6, 8)}/${date.slice(4, 6)}/${date.slice(0, 4)} ${time.slice(0, 2)}:${time.slice(2, 4)}:${time.slice(4, 6)}`;
                        }
                        
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${file.replace(/^result_\d{8}_\d{6}_/, '').replace('.json', '')}</td>
                            <td>${dateStr}</td>
                            <td>
                                <div class="dropdown">
                                    <button class="btn btn-sm btn-outline-primary dropdown-toggle" type="button" data-bs-toggle="dropdown">
                                        Actions
                                    </button>
                                    <ul class="dropdown-menu">
                                        <li><a class="dropdown-item" href="/download/${file}">Download JSON</a></li>
                                        <li><a class="dropdown-item" href="/download/${file}?format=csv">Download CSV</a></li>
                                        <li><a class="dropdown-item" href="/download/${file}?format=excel">Download Excel</a></li>
                                    </ul>
                                </div>
                            </td>
                        `;
                        previousResultsTableBody.appendChild(row);
                    });
                    
                    noResultsMessage.style.display = 'none';
                } else {
                    // No results found
                    noResultsMessage.style.display = 'block';
                }
            })
            .catch(error => {
                console.error('Error loading previous results:', error);
                noResultsMessage.style.display = 'block';
            });
    }
    
    // Helper function: Format file size
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // Helper function: Show alert
    function showAlert(message, type) {
        // Create alert element
        const alertElement = document.createElement('div');
        alertElement.className = `alert alert-${type} alert-dismissible fade show`;
        alertElement.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        // Add to page
        document.querySelector('main').prepend(alertElement);
        
        // Auto hide after 5 seconds
        setTimeout(() => {
            alertElement.classList.remove('show');
            setTimeout(() => alertElement.remove(), 300);
        }, 5000);
    }
});
