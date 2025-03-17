/**
 * Invoice AI - Main Application JavaScript
 * Modern SaaS functionality for the invoice processing application
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize UI components
    initNavigation();
    initMobileMenu();
    initDropzone();
    initAlerts();
    initDashboard();
    
    // Load initial data
    loadPreviousResults();
});

/**
 * Initialize the navigation system
 */
function initNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    const sections = document.querySelectorAll('.content-section');
    
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
            
            // Show corresponding section with animation
            const targetSection = document.getElementById(targetId);
            if (targetSection) {
                targetSection.classList.add('active');
                
                // Reset UI state based on section
                if (targetId === 'upload') {
                    // Reset upload form when navigating to upload section
                    resetUploadArea();
                    
                    // Hide result cards if present
                    const resultSection = document.getElementById('result');
                    if (resultSection) {
                        resultSection.classList.remove('active');
                    }
                } else if (targetId === 'extractions') {
                    // Load previous results if navigating to previous results tab
                    loadPreviousResults();
                } else if (targetId === 'dashboard') {
                    // Refresh dashboard data
                    updateDashboardStats();
                }
            } else {
                console.error('Section not found:', targetId);
                showAlert('Section not found: ' + targetId, 'danger');
            }
        });
    });
    
    // Back to upload button functionality
    const backToUploadButton = document.getElementById('backToUpload');
    if (backToUploadButton) {
        backToUploadButton.addEventListener('click', function() {
            // Check if we're coming from batch processing
            if (this.getAttribute('data-from-batch') === 'true') {
                // Reset the attribute for next time
                this.setAttribute('data-from-batch', 'false');
                // Change text back to original
                this.innerHTML = '<i class="bi bi-arrow-left"></i> Back to Upload';
                // Navigate to extractions section (batch results)
                navigateTo('extractions');
            } else {
                // Navigate to extractions section
                navigateTo('extractions');
                // Refresh the extractions list
                loadPreviousResults();
            }
        });
    }
    
    // Handle direct section links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        if (!anchor.classList.contains('nav-link')) {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                
                const targetId = this.getAttribute('href').substring(1);
                const targetSection = document.getElementById(targetId);
                const targetTab = document.querySelector(`a[href="#${targetId}"]`);
                
                if (targetSection && targetTab) {
                    // Trigger the tab click event
                    targetTab.click();
                }
            });
        }
    });
}

/**
 * Initialize mobile menu
 */
function initMobileMenu() {
    const mobileMenuToggle = document.getElementById('mobileSidebarToggle');
    const sidebar = document.querySelector('.sidebar');
    
    if (mobileMenuToggle && sidebar) {
        mobileMenuToggle.addEventListener('click', function() {
            sidebar.classList.toggle('active');
            document.body.classList.toggle('sidebar-open');
        });
        
        // Close menu when a nav link is clicked on mobile
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', function() {
                if (window.innerWidth < 992) {
                    sidebar.classList.remove('active');
                    document.body.classList.remove('sidebar-open');
                }
            });
        });
    }
}

/**
 * Initialize the file upload and dropzone
 */
function initDropzone() {
    const uploadArea = document.getElementById('uploadArea');
    const dropzone = document.getElementById('dropzone');
    const filePreview = document.getElementById('filePreview');
    const uploadProgress = document.getElementById('uploadProgress');
    const fileInput = document.getElementById('fileInput');
    const browseButton = document.getElementById('browseButton');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const uploadButton = document.getElementById('uploadButton');
    const cancelButton = document.getElementById('cancelButton');
    const processAnother = document.getElementById('processAnother');
    
    if (!uploadArea || !fileInput) return;
    
    // File Upload - Browse Button
    if (browseButton) {
        browseButton.addEventListener('click', function() {
            fileInput.click();
        });
    }
    
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
            dropzone.classList.add('dragging');
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, function() {
            dropzone.classList.remove('dragging');
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
            }
            
            // Show preview, hide prompt
            dropzone.style.display = 'none';
            filePreview.style.display = 'flex';
            
            // Store files reference for upload
            uploadButton.files = files;
        }
    }
    
    // Upload button click handler
    if (uploadButton) {
        uploadButton.addEventListener('click', function() {
            if (!this.files || this.files.length === 0) return;
            
            // Show progress, hide preview
            filePreview.style.display = 'none';
            uploadProgress.style.display = 'block';
            
            // Create form data
            const formData = new FormData();
            for (let i = 0; i < this.files.length; i++) {
                if (this.files[i].type === 'application/pdf') {
                    formData.append('invoice', this.files[i]);
                }
            }
            
            // Set progress bar
            const progressBar = uploadProgress.querySelector('.progress-bar');
            progressBar.style.width = '0%';
            
            // Process the upload
            processUpload(formData, progressBar);
        });
    }
    
    // Cancel button click handler
    if (cancelButton) {
        cancelButton.addEventListener('click', function() {
            resetUploadArea();
        });
    }
    
    // Process Another button click handler
    if (processAnother) {
        processAnother.addEventListener('click', function() {
            // Switch to upload section and reset
            const uploadTab = document.querySelector('a[href="#upload"]');
            if (uploadTab) {
                uploadTab.click();
            }
            resetUploadArea();
        });
    }
    
    // Process the upload and handle response
    function processUpload(formData, progressBar) {
        const xhr = new XMLHttpRequest();
        
        xhr.open('POST', '/upload');
        
        // Upload progress event
        xhr.upload.addEventListener('progress', function(e) {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                progressBar.style.width = percentComplete + '%';
            }
        });
        
        // Handle response
        xhr.onload = function() {
            if (xhr.status === 200) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    console.log("Server response:", response); // Debug log
                    
                    // Update progress bar to 100%
                    progressBar.style.width = '100%';
                    
                    // Show success message
                    const successCount = response.success_count || 0;
                    const totalFiles = response.total_files || 0;
                    showAlert(`Processed ${successCount} of ${totalFiles} invoices successfully!`, 'success');
                    
                    // Check if we have multiple results
                    const hasMultipleResults = response.results && 
                                              Array.isArray(response.results) && 
                                              response.results.length > 1;
                    
                    if (hasMultipleResults) {
                        // Show a batch processing summary modal first
                        const batchSummary = document.createElement('div');
                        batchSummary.className = 'batch-summary section-card mb-4';
                        batchSummary.innerHTML = `
                            <div class="card-header d-flex justify-content-between align-items-center">
                                <h3>Batch Processing Summary</h3>
                            </div>
                            <div class="card-content">
                                <div class="alert alert-success">
                                    <strong>Successfully processed ${successCount} of ${totalFiles} invoices</strong>
                                </div>
                                <div class="table-responsive">
                                    <table class="table">
                                        <thead>
                                            <tr>
                                                <th>Filename</th>
                                                <th>Status</th>
                                                <th>Invoice #</th>
                                                <th>Company</th>
                                                <th>Action</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${response.results.map(item => {
                                                // Extract data depending on structure
                                                const result = item.result || {};
                                                return `
                                                <tr>
                                                    <td>${item.filename || 'Unknown'}</td>
                                                    <td><span class="badge bg-success">Processed</span></td>
                                                    <td>${result.invoice_number || '-'}</td>
                                                    <td>${result.company_name || '-'}</td>
                                                    <td>
                                                        <button class="btn btn-sm btn-primary view-batch-result" 
                                                                data-index="${response.results.indexOf(item)}">
                                                            View Details
                                                        </button>
                                                    </td>
                                                </tr>
                                                `;
                                            }).join('')}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        `;
                        
                        // Store the results in a global variable for easy access
                        window.batchResults = response.results;
                        
                        // Force refresh extractions page first
                        const cacheBuster = new Date().getTime();
                        fetch(`/extraction_history?_=${cacheBuster}`, {
                            headers: {
                                'Cache-Control': 'no-cache',
                                'Pragma': 'no-cache'
                            }
                        });
                        
                        // Navigate to extractions page and display the summary
                        const extractionsSection = document.getElementById('extractions');
                        if (extractionsSection) {
                            // Show the section
                            navigateTo('extractions');
                            
                            // Insert the batch summary at the top of the extractions section
                            const firstChild = extractionsSection.querySelector('.section-header');
                            if (firstChild && firstChild.nextSibling) {
                                extractionsSection.insertBefore(batchSummary, firstChild.nextSibling);
                            } else {
                                extractionsSection.appendChild(batchSummary);
                            }
                            
                            // Add event listeners to view batch results
                            document.querySelectorAll('.view-batch-result').forEach(button => {
                                button.addEventListener('click', function() {
                                    const index = parseInt(this.getAttribute('data-index'), 10);
                                    const result = window.batchResults[index];
                                    if (result) {
                                        // Display this individual result
                                        navigateTo('result');
                                        
                                        // Change the back button to 'Back to Results' instead of 'Back to Upload'
                                        const backButton = document.getElementById('backToUpload');
                                        if (backButton) {
                                            backButton.innerHTML = '<i class="bi bi-arrow-left"></i> Back to Results';
                                            backButton.setAttribute('data-from-batch', 'true');
                                        }
                                        
                                        const resultData = result.result || result;
                                        populateResults(resultData);
                                    }
                                });
                            });
                        }
                        
                        // Load the extraction history data
                        loadPreviousResults();
                    } else {
                        // For single result, show the result directly
                        // Switch to results section
                        const sections = document.querySelectorAll('.content-section');
                        sections.forEach(section => section.classList.remove('active'));
                        
                        // Display the result section
                        const resultSection = document.getElementById('result');
                        if (resultSection) {
                            resultSection.classList.add('active');
                            
                            // Handle the response structure based on our backend API
                            if (response.results && Array.isArray(response.results) && response.results.length > 0) {
                                // If response contains a results array (batch processing)
                                const firstResult = response.results[0];
                                
                                // If result has a nested result object (from extraction_results.json structure)
                                if (firstResult.result) {
                                    // Add filename to the result object for display
                                    firstResult.result.filename = firstResult.filename;
                                    populateResults(firstResult.result);
                                } else {
                                    // Direct result object
                                    populateResults(firstResult);
                                }
                            } else if (response.result) {
                                // If response has a direct result object
                                populateResults(response.result);
                            } else {
                                // If response itself is the result
                                populateResults(response);
                            }
                        }
                    }
                    
                    // Update dashboard stats
                    updateDashboardStats();
                    
                } catch (error) {
                    console.error('Error parsing JSON response:', error);
                    showAlert('Error processing response', 'danger');
                    resetUploadArea();
                }
            } else {
                showAlert('Error processing invoice. Please try again.', 'danger');
                resetUploadArea();
            }
        };
        
        // Handle network errors
        xhr.onerror = function() {
            showAlert('Network error. Please check your connection and try again.', 'danger');
            resetUploadArea();
        };
        
        // Send the form data
        xhr.send(formData);
    }
}

/**
 * Populate the result fields with extraction data
 */
function populateResults(data) {
    console.log('Populating results with data:', JSON.stringify(data, null, 2));
    
    // For debug purposes, let's log all the elements we're trying to populate
    console.log('Element existence check:',
        'companyName:', !!document.getElementById('companyName'),
        'invoiceNumber:', !!document.getElementById('invoiceNumber'),
        'invoiceDate:', !!document.getElementById('invoiceDate'),
        'fssaiNumber:', !!document.getElementById('fssaiNumber'),
        'productTableBody:', !!document.getElementById('productTableBody')
    );
    
    // Set the file name if available
    const resultFileName = document.getElementById('resultFileName');
    if (resultFileName) {
        resultFileName.textContent = data.filename || 'Invoice Results';
    }
    
    // Set confidence badge
    const confidenceBadge = document.getElementById('confidenceBadge');
    if (confidenceBadge && data.confidence_scores && data.confidence_scores.overall) {
        const confidence = Math.round(data.confidence_scores.overall * 100);
        confidenceBadge.textContent = `${confidence}% Confidence`;
        
        // Update badge color based on confidence level
        if (confidence >= 85) {
            confidenceBadge.style.backgroundColor = 'var(--success)';
        } else if (confidence >= 70) {
            confidenceBadge.style.backgroundColor = 'var(--warning)';
        } else {
            confidenceBadge.style.backgroundColor = 'var(--danger)';
        }
    } else {
        console.warn('Could not set confidence badge:', {
            'badgeExists': !!confidenceBadge,
            'confidence_scores': data.confidence_scores,
            'overall': data.confidence_scores ? data.confidence_scores.overall : undefined
        });
    }
    
    // Populate invoice information fields
    const companyNameEl = document.getElementById('companyName');
    const invoiceNumberEl = document.getElementById('invoiceNumber');
    const invoiceDateEl = document.getElementById('invoiceDate');
    const fssaiNumberEl = document.getElementById('fssaiNumber');
    
    if (companyNameEl) companyNameEl.textContent = data.company_name || '-';
    if (invoiceNumberEl) invoiceNumberEl.textContent = data.invoice_number || '-';
    if (invoiceDateEl) invoiceDateEl.textContent = data.invoice_date || '-';
    if (fssaiNumberEl) fssaiNumberEl.textContent = data.fssai_number || '-';
    
    // Log values for debugging
    console.log('Field population:', {
        'company_name': data.company_name,
        'invoice_number': data.invoice_number,
        'invoice_date': data.invoice_date,
        'fssai_number': data.fssai_number
    });
    
    // Populate product table
    const productTableBody = document.getElementById('productTableBody');
    if (productTableBody) {
        // Clear existing content
        productTableBody.innerHTML = '';
        
        // Check if we have product data
        if (data.products && data.products.length > 0) {
            console.log(`Populating ${data.products.length} products`);
            
            // Add each product as a row
            data.products.forEach((product, index) => {
                console.log(`Product ${index}:`, product);
                const row = document.createElement('tr');
                
                // Create cells for each column
                row.innerHTML = `
                    <td>${product.goods_description || '-'}</td>
                    <td>${product.hsn_sac_code || '-'}</td>
                    <td>${product.quantity || '-'}</td>
                    <td>${product.weight || '-'}</td>
                    <td>${product.rate || '-'}</td>
                    <td>${product.amount || '-'}</td>
                `;
                
                productTableBody.appendChild(row);
            });
        } else {
            console.warn('No products found in data:', data.products);
            // No products found, show message
            productTableBody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center">No product data available</td>
                </tr>
            `;
        }
    } else {
        console.error('Product table body element not found!');
    }
    
    // Setup the download Excel button
    const downloadExcelButton = document.getElementById('downloadExcel');
    if (downloadExcelButton) {
        // Remove any existing event listeners
        const newButton = downloadExcelButton.cloneNode(true);
        downloadExcelButton.parentNode.replaceChild(newButton, downloadExcelButton);
        
        newButton.addEventListener('click', function() {
            // Create a filtered data object with only the required fields
            const extractedData = {
                company_name: data.company_name || null,
                invoice_number: data.invoice_number || null,
                invoice_date: data.invoice_date || null,
                fssai_number: data.fssai_number || null,
                products: data.products || []
            };
            
            // Send request to server to generate Excel file
            fetch('/download/excel', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(extractedData)
            })
            .then(response => {
                if (response.ok) {
                    return response.blob();
                }
                throw new Error('Failed to generate Excel file');
            })
            .then(blob => {
                // Create a download link for the Excel file
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `invoice_data_${Date.now()}.xlsx`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                
                showAlert('Excel file downloaded successfully', 'success');
            })
            .catch(error => {
                console.error('Error generating Excel file:', error);
                showAlert('Failed to generate Excel file', 'danger');
            });
        });
    }
}

/**
 * Reset the upload area to its initial state
 */
function resetUploadArea() {
    const uploadArea = document.getElementById('uploadArea');
    const dropzone = document.getElementById('dropzone');
    const filePreview = document.getElementById('filePreview');
    const uploadProgress = document.getElementById('uploadProgress');
    const fileInput = document.getElementById('fileInput');
    
    if (!uploadArea || !dropzone || !filePreview || !uploadProgress || !fileInput) return;
    
    // Reset file input
    fileInput.value = '';
    
    // Reset upload button files reference
    const uploadButton = document.getElementById('uploadButton');
    if (uploadButton) {
        uploadButton.files = null;
    }
    
    // Show dropzone, hide preview and progress
    dropzone.style.display = 'flex';
    filePreview.style.display = 'none';
    uploadProgress.style.display = 'none';
    
    // Reset progress bar
    const progressBar = uploadProgress.querySelector('.progress-bar');
    if (progressBar) {
        progressBar.style.width = '0%';
    }
    
    // Clear file info
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    
    if (fileName) fileName.textContent = '';
    if (fileSize) fileSize.textContent = '';
    
    // Reset drag state
    dropzone.classList.remove('dragging');
    
    // Show upload card if it was hidden
    const uploadCard = document.getElementById('uploadCard');
    if (uploadCard) {
        uploadCard.style.display = 'block';
    }
}

/**
 * Format file size to human-readable format
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Initialize the alert system
 */
function initAlerts() {
    // We'll use this container for all alert messages
    const alertContainer = document.getElementById('alertContainer');
    
    if (!alertContainer) {
        // Create alert container if it doesn't exist
        const container = document.createElement('div');
        container.id = 'alertContainer';
        container.className = 'alert-container';
        document.body.appendChild(container);
    }
}

/**
 * Show an alert message
 * @param {string} message - The message to display
 * @param {string} type - The alert type (info, success, warning, danger)
 * @param {string|null} updateId - Optional ID of an existing alert to update instead of creating a new one
 * @returns {string} - The ID of the created/updated alert
 */
function showAlert(message, type = 'info', updateId = null) {
    const alertContainer = document.getElementById('alertContainer');
    
    if (!alertContainer) return null;
    
    // Get icon based on type
    let icon = 'info-circle';
    if (type === 'success') icon = 'check-circle';
    if (type === 'warning') icon = 'exclamation-triangle';
    if (type === 'danger') icon = 'exclamation-circle';
    
    let alert;
    let isNew = true;
    
    // If updateId provided, try to find and update existing alert
    if (updateId) {
        alert = document.getElementById(updateId);
        if (alert) {
            isNew = false;
            
            // Apply transition effect
            alert.style.transition = 'opacity 0.3s';
            alert.style.opacity = '0.5';
            
            // Update alert class for new type
            alert.className = `alert alert-${type}`;
            
            // Update content with animation
            setTimeout(() => {
                // Update the inner HTML
                alert.innerHTML = `
                    <div class="d-flex align-items-center">
                        <i class="bi bi-${icon} me-2"></i>
                        <div>${message}</div>
                        <button type="button" class="btn-close ms-auto" aria-label="Close"></button>
                    </div>
                `;
                
                // Fade back in
                alert.style.opacity = '1';
                
                // Re-add closing functionality
                const closeButton = alert.querySelector('.btn-close');
                if (closeButton) {
                    closeButton.addEventListener('click', function() {
                        alert.remove();
                    });
                }
            }, 300);
        }
    }
    
    // If no existing alert found or no updateId provided, create a new one
    if (isNew) {
        // Generate a unique ID for this alert
        const alertId = 'alert-' + Date.now();
        
        // Create new alert element
        alert = document.createElement('div');
        alert.id = alertId;
        alert.className = `alert alert-${type}`;
        alert.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="bi bi-${icon} me-2"></i>
                <div>${message}</div>
                <button type="button" class="btn-close ms-auto" aria-label="Close"></button>
            </div>
        `;
        
        // Add alert to container
        alertContainer.appendChild(alert);
        
        // Add closing functionality
        const closeButton = alert.querySelector('.btn-close');
        if (closeButton) {
            closeButton.addEventListener('click', function() {
                alert.remove();
            });
        }
    }
    
    // Auto-remove alert after 5 seconds
    setTimeout(() => {
        alert.classList.add('fade-out');
        setTimeout(() => {
            if (alert.parentNode === alertContainer) {
                alertContainer.removeChild(alert);
            }
        }, 300);
    }, 5000);
    
    // Return the alert ID so it can be referenced for updates
    return alert.id;
}

/**
 * Load previous extraction results for the history section
 */
function loadPreviousResults() {
    console.log('Loading previous extractions from app.js');
    const extractionsTable = document.getElementById('extractionsTable');
    const noExtractionsMessage = document.getElementById('noExtractionsMessage');
    const extractionsTableBody = document.getElementById('extractionsTableBody');
    
    if (!extractionsTable || !noExtractionsMessage || !extractionsTableBody) {
        console.warn('Missing required DOM elements for extraction history');
        return;
    }
    
    // Show loading state
    noExtractionsMessage.textContent = 'Loading extractions...';
    noExtractionsMessage.style.display = 'block';
    extractionsTable.style.display = 'none';
    
    // Fetch previous results
    fetch('/extraction_history')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Extraction history data:', data);
            
            // Check if data has extractions property and it's not empty
            if (data && data.extractions && data.extractions.length > 0) {
                // Use the extractions array from the response
                const extractions = data.extractions;
                
                // We have data, show the table
                extractionsTable.style.display = 'block';
                noExtractionsMessage.style.display = 'none';
                
                // Clear existing rows
                extractionsTableBody.innerHTML = '';
                
                // Add each extraction to the table
                extractions.forEach(extraction => {
                    const row = document.createElement('tr');
                    
                    // Format the row
                    row.innerHTML = `
                        <td>${extraction.filename || 'Unknown File'}</td>
                        <td>${extraction.company_name || '-'}</td>
                        <td>${extraction.invoice_number || '-'}</td>
                        <td>${extraction.invoice_date || '-'}</td>
                        <td>
                            <span class="confidence-badge" style="background-color: ${getConfidenceColor(extraction.confidence_overall)}">
                                ${Math.round((extraction.confidence_overall || 0) * 100)}%
                            </span>
                        </td>
                        <td>
                            <button class="btn btn-sm btn-outline-primary view-extraction" data-id="${extraction.id}">
                                <i class="bi bi-eye"></i> View
                            </button>
                        </td>
                    `;
                    
                    extractionsTableBody.appendChild(row);
                });
                
                // Add event listeners to view buttons
                document.querySelectorAll('.view-extraction').forEach(button => {
                    button.addEventListener('click', function() {
                        const extractionId = this.getAttribute('data-id');
                        viewExtraction(extractionId);
                    });
                });
                
                console.log('Loaded and displayed extraction history');
            } else {
                // No data, show the empty message
                console.log('No extraction data found');
                extractionsTable.style.display = 'none';
                noExtractionsMessage.textContent = 'No previous extractions found. Upload an invoice to get started.';
                noExtractionsMessage.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('Error loading extraction history:', error);
            extractionsTable.style.display = 'none';
            noExtractionsMessage.textContent = 'Error loading extractions. Please try again.';
            noExtractionsMessage.style.display = 'block';
            showAlert('Failed to load extraction history: ' + error.message, 'danger');
        });
}

/**
 * Get the appropriate color for a confidence value
 */
function getConfidenceColor(confidence) {
    const percent = Math.round((confidence || 0) * 100);
    if (percent >= 85) {
        return 'var(--success)';
    } else if (percent >= 70) {
        return 'var(--warning)';
    } else {
        return 'var(--danger)';
    }
}

/**
 * View a specific extraction
 */
function viewExtraction(id) {
    console.log(`Fetching extraction data for ID: ${id}`);
    // Create a loading alert and store its ID for later updating
    const alertId = showAlert('Loading extraction...', 'info');
    
    fetch(`/extraction/${id}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Extraction data received:', data); // Debug log
            
            // Switch to the result section
            const sections = document.querySelectorAll('.content-section');
            sections.forEach(section => section.classList.remove('active'));
            
            const resultSection = document.getElementById('result');
            if (resultSection) {
                resultSection.classList.add('active');
                
                // Data structure handling with better debugging
                if (data.results && Array.isArray(data.results) && data.results.length > 0) {
                    console.log('Data has results array, using first item');
                    const firstResult = data.results[0];
                    
                    if (firstResult.result) {
                        console.log('First result has nested result object');
                        firstResult.result.filename = firstResult.filename;
                        populateResults(firstResult.result);
                    } else {
                        console.log('Using first result directly');
                        populateResults(firstResult);
                    }
                } else if (data.result) {
                    console.log('Data has direct result property');
                    // Add filename from the parent object if needed
                    if (data.filename && !data.result.filename) {
                        data.result.filename = data.filename;
                    }
                    populateResults(data.result);
                } else {
                    console.log('Using data object directly');
                    populateResults(data);
                }
                
                // Update the existing alert to show success, using the same alertId
                showAlert('Extraction data loaded successfully', 'success', alertId);
            } else {
                console.error('Result section not found in DOM');
                showAlert('Error: Result section not found', 'danger');
            }
        })
        .catch(error => {
            console.error('Error loading extraction:', error);
            // Update the existing alert to show the error, using the same alertId
            showAlert('Failed to load extraction details: ' + error.message, 'danger', alertId);
        });
}

/**
 * Initialize the dashboard stats and charts
 */
function initDashboard() {
    updateDashboardStats();
}

/**
 * Update the dashboard statistics
 */
function updateDashboardStats() {
    fetch('/dashboard_stats')
        .then(response => response.json())
        .then(data => {
            // Update the stat counters
            document.getElementById('totalInvoices').textContent = data.total_invoices || 0;
            document.getElementById('successRate').textContent = `${Math.round((data.success_rate || 0) * 100)}%`;
            document.getElementById('avgProcessingTime').textContent = `${data.avg_processing_time || 0}s`;
            document.getElementById('activeToday').textContent = data.active_today || 0;
            
            // Populate recent uploads
            updateRecentUploads(data.recent_uploads || []);
        })
        .catch(error => {
            console.error('Error updating dashboard stats:', error);
        });
}

/**
 * Update the recent uploads table on the dashboard
 */
function updateRecentUploads(recentUploads) {
    const recentUploadsEmpty = document.getElementById('recentUploadsEmpty');
    const recentUploadsTable = document.getElementById('recentUploadsTable');
    const recentUploadsTableBody = document.getElementById('recentUploadsTableBody');
    
    if (!recentUploadsEmpty || !recentUploadsTable || !recentUploadsTableBody) return;
    
    if (recentUploads.length > 0) {
        // Show the table, hide the empty message
        recentUploadsTable.style.display = 'block';
        recentUploadsEmpty.style.display = 'none';
        
        // Clear existing rows
        recentUploadsTableBody.innerHTML = '';
        
        // Add each upload as a row (limited to 5)
        recentUploads.slice(0, 5).forEach(upload => {
            const row = document.createElement('tr');
            
            row.innerHTML = `
                <td>${upload.filename || 'Unknown File'}</td>
                <td>${upload.vendor_name || '-'}</td>
                <td>${upload.invoice_number || '-'}</td>
                <td>${upload.invoice_date || '-'}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary view-extraction" data-id="${upload.id}">
                        <i class="bi bi-eye"></i> View
                    </button>
                </td>
            `;
            
            recentUploadsTableBody.appendChild(row);
        });
        
        // Add event listeners to view buttons
        document.querySelectorAll('.view-extraction').forEach(button => {
            button.addEventListener('click', function() {
                const extractionId = this.getAttribute('data-id');
                viewExtraction(extractionId);
            });
        });
    } else {
        // No data, show the empty message
        recentUploadsTable.style.display = 'none';
        recentUploadsEmpty.style.display = 'block';
    }
}

/**
 * Show a summary of batch processing results
 */
function showBatchProcessingSummary(results) {
    if (!results || !Array.isArray(results) || results.length === 0) return;
    
    // Create a modal to show batch processing results
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.id = 'batchSummaryModal';
    modal.setAttribute('tabindex', '-1');
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-labelledby', 'batchSummaryModalLabel');
    modal.setAttribute('aria-hidden', 'true');
    
    // Count successful extractions
    const successCount = results.filter(r => r.success || (r.result && Object.keys(r.result).length > 0)).length;
    
    // Create modal content
    modal.innerHTML = `
        <div class="modal-dialog modal-lg" role="document">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="batchSummaryModalLabel">Batch Processing Summary</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <div class="alert alert-info">
                        <strong>Successfully processed ${successCount} of ${results.length} invoices.</strong>
                        <p>Full results are available in the Previous Extractions section.</p>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-striped">
                            <thead>
                                <tr>
                                    <th>Filename</th>
                                    <th>Status</th>
                                    <th>Company</th>
                                    <th>Invoice #</th>
                                    <th>Date</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${results.map(item => {
                                    // Get data based on the structure
                                    const success = item.success || (item.result && Object.keys(item.result).length > 0);
                                    const result = item.result || item;
                                    return `
                                    <tr>
                                        <td>${item.filename || 'Unknown'}</td>
                                        <td>${success ? '<span class="badge bg-success">Success</span>' : '<span class="badge bg-danger">Failed</span>'}</td>
                                        <td>${result.company_name || '-'}</td>
                                        <td>${result.invoice_number || '-'}</td>
                                        <td>${result.invoice_date || '-'}</td>
                                    </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    <button type="button" class="btn btn-primary" id="viewExtractionsBtn">View in Extractions</button>
                </div>
            </div>
        </div>
    `;
    
    // Add modal to body
    document.body.appendChild(modal);
    
    // Initialize Bootstrap modal
    const modalInstance = new bootstrap.Modal(modal);
    modalInstance.show();
    
    // Add event listener to the View Extractions button
    const viewExtractionsBtn = document.getElementById('viewExtractionsBtn');
    if (viewExtractionsBtn) {
        viewExtractionsBtn.addEventListener('click', function() {
            modalInstance.hide();
            navigateTo('extractions');
            loadPreviousResults();
        });
    }
    
    // Remove modal from DOM when hidden
    modal.addEventListener('hidden.bs.modal', function() {
        document.body.removeChild(modal);
    });
}

/**
 * Navigate to a specific section
 */
function navigateTo(sectionId) {
    const sections = document.querySelectorAll('.content-section');
    sections.forEach(section => section.classList.remove('active'));
    
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.classList.add('active');
    }
}
