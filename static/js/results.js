/**
 * Invoice AI - Results JavaScript
 * Handles displaying and managing invoice processing results
 */

/**
 * Display single invoice processing results
 */
function displayResults(result) {
    const resultCard = document.getElementById('resultCard');
    if (!resultCard) return;
    
    // Show result card
    resultCard.style.display = 'block';
    
    // Hide batch result card
    const batchResultCard = document.getElementById('batchResultCard');
    if (batchResultCard) {
        batchResultCard.style.display = 'none';
    }
    
    // Hide back to batch button
    const backToBatchBtn = document.getElementById('backToBatchBtn');
    if (backToBatchBtn) {
        backToBatchBtn.style.display = 'none';
    }
    
    // Update result header
    const resultTitle = document.getElementById('resultTitle');
    if (resultTitle) {
        resultTitle.textContent = result.filename || 'Invoice Processing Results';
    }
    
    // Calculate and display confidence score
    displayConfidenceScore(result.confidence_scores);
    
    // Display extracted data
    displayExtractedData(result.extracted_data);
    
    // Update raw JSON data
    const jsonData = document.getElementById('jsonData');
    if (jsonData) {
        jsonData.textContent = JSON.stringify(result, null, 2);
    }
    
    // Store result in session storage
    storeResult(result);
}

/**
 * Display batch processing results
 */
function displayBatchResults(data) {
    const batchResultCard = document.getElementById('batchResultCard');
    if (!batchResultCard) return;
    
    // Show batch result card
    batchResultCard.style.display = 'block';
    
    // Hide single result card
    const resultCard = document.getElementById('resultCard');
    if (resultCard) {
        resultCard.style.display = 'none';
    }
    
    // Update batch results table
    const tableBody = document.getElementById('batchResultsTable');
    if (tableBody) {
        // Clear previous results
        tableBody.innerHTML = '';
        
        // Add each result to table
        data.results.forEach((result, index) => {
            const row = document.createElement('tr');
            row.className = 'invoice-row';
            row.dataset.index = index;
            
            // Calculate confidence score
            const confidenceScore = calculateAverageConfidence(result.confidence_scores);
            
            // Format data
            const invoiceNumber = result.extracted_data?.invoice_number || 'N/A';
            const vendor = result.extracted_data?.vendor_name || 'Unknown';
            const date = result.extracted_data?.date || 'N/A';
            const amount = result.extracted_data?.total_amount ? `$${result.extracted_data.total_amount}` : 'N/A';
            
            // Set row content
            row.innerHTML = `
                <td>${result.filename || `Invoice ${index + 1}`}</td>
                <td>${vendor}</td>
                <td>${invoiceNumber}</td>
                <td>${date}</td>
                <td>${amount}</td>
                <td>
                    <div class="progress">
                        <div class="progress-bar ${getConfidenceClass(confidenceScore)}" 
                             role="progressbar" 
                             style="width: ${confidenceScore}%" 
                             aria-valuenow="${confidenceScore}" 
                             aria-valuemin="0" 
                             aria-valuemax="100">
                            ${confidenceScore}%
                        </div>
                    </div>
                </td>
                <td>
                    <button class="btn btn-sm btn-primary view-invoice-btn">
                        <i class="bi bi-eye"></i> View
                    </button>
                </td>
            `;
            
            tableBody.appendChild(row);
            
            // Add click event to view button
            const viewButton = row.querySelector('.view-invoice-btn');
            if (viewButton) {
                viewButton.addEventListener('click', function() {
                    displayResults(data.results[index]);
                    
                    // Show back to batch button
                    const backToBatchBtn = document.getElementById('backToBatchBtn');
                    if (backToBatchBtn) {
                        backToBatchBtn.style.display = 'block';
                    }
                });
            }
        });
    }
    
    // Update summary info
    const totalInvoices = document.getElementById('totalInvoices');
    if (totalInvoices) {
        totalInvoices.textContent = data.results.length;
    }
    
    const avgConfidence = document.getElementById('avgConfidence');
    if (avgConfidence) {
        // Calculate average confidence across all results
        let total = 0;
        data.results.forEach(result => {
            total += calculateAverageConfidence(result.confidence_scores);
        });
        const average = Math.round(total / data.results.length);
        avgConfidence.textContent = `${average}%`;
    }
    
    const totalAmount = document.getElementById('totalAmount');
    if (totalAmount) {
        // Calculate total amount across all invoices
        let total = 0;
        data.results.forEach(result => {
            if (result.extracted_data?.total_amount) {
                const amount = parseFloat(result.extracted_data.total_amount);
                if (!isNaN(amount)) {
                    total += amount;
                }
            }
        });
        totalAmount.textContent = `$${total.toFixed(2)}`;
    }
    
    // Store batch results
    storeBatchResults(data.results);
}

/**
 * Display confidence score in the UI
 */
function displayConfidenceScore(confidenceScores) {
    const confidenceEl = document.getElementById('confidenceScore');
    if (!confidenceEl) return;
    
    // Calculate average confidence
    const averageConfidence = calculateAverageConfidence(confidenceScores);
    
    // Update confidence score display
    confidenceEl.textContent = `${averageConfidence}%`;
    confidenceEl.className = `confidence-score ${getConfidenceClass(averageConfidence)}`;
    
    // Update confidence gauge if it exists
    const gaugeEl = document.getElementById('confidenceGauge');
    if (gaugeEl) {
        gaugeEl.style.setProperty('--percentage', `${averageConfidence}%`);
        gaugeEl.className = `confidence-gauge ${getConfidenceClass(averageConfidence)}`;
    }
    
    // Update confidence breakdown
    displayConfidenceBreakdown(confidenceScores);
}

/**
 * Calculate average confidence from confidence scores object
 */
function calculateAverageConfidence(confidenceScores) {
    if (!confidenceScores || typeof confidenceScores !== 'object') {
        return 85; // Default value if no confidence scores
    }
    
    const scores = Object.values(confidenceScores).filter(score => typeof score === 'number');
    if (scores.length === 0) return 85;
    
    // Calculate average and convert to percentage
    const average = scores.reduce((sum, score) => sum + score, 0) / scores.length;
    return Math.round(average * 100);
}

/**
 * Get CSS class based on confidence level
 */
function getConfidenceClass(confidence) {
    if (confidence >= 90) return 'confidence-high';
    if (confidence >= 75) return 'confidence-medium';
    if (confidence >= 60) return 'confidence-low';
    return 'confidence-very-low';
}

/**
 * Display confidence breakdown by field
 */
function displayConfidenceBreakdown(confidenceScores) {
    const breakdownEl = document.getElementById('confidenceBreakdown');
    if (!breakdownEl || !confidenceScores) return;
    
    // Clear previous breakdown
    breakdownEl.innerHTML = '';
    
    // Create breakdown for each field
    Object.entries(confidenceScores).forEach(([field, score]) => {
        if (typeof score !== 'number') return;
        
        // Format field name
        const fieldName = field.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        
        // Calculate percentage
        const percentage = Math.round(score * 100);
        
        // Create progress bar
        const item = document.createElement('div');
        item.className = 'confidence-breakdown-item mb-2';
        item.innerHTML = `
            <div class="d-flex justify-content-between mb-1">
                <span>${fieldName}</span>
                <span>${percentage}%</span>
            </div>
            <div class="progress">
                <div class="progress-bar ${getConfidenceClass(percentage)}" 
                     role="progressbar" 
                     style="width: ${percentage}%" 
                     aria-valuenow="${percentage}" 
                     aria-valuemin="0" 
                     aria-valuemax="100"></div>
            </div>
        `;
        
        breakdownEl.appendChild(item);
    });
}

/**
 * Display extracted data in the UI
 */
function displayExtractedData(data) {
    if (!data) return;
    
    // Update each field in the UI
    updateExtractedField('invoiceNumber', data.invoice_number);
    updateExtractedField('invoiceDate', data.date);
    updateExtractedField('dueDate', data.due_date);
    updateExtractedField('poNumber', data.po_number);
    updateExtractedField('vendorName', data.vendor_name);
    updateExtractedField('vendorAddress', data.vendor_address);
    updateExtractedField('billToName', data.bill_to_name);
    updateExtractedField('billToAddress', data.bill_to_address);
    updateExtractedField('subtotal', data.subtotal, true);
    updateExtractedField('tax', data.tax, true);
    updateExtractedField('totalAmount', data.total_amount, true);
    
    // Display line items if available
    displayLineItems(data.line_items);
    
    // Make fields editable
    makeFieldsEditable();
}

/**
 * Update an extracted field in the UI
 */
function updateExtractedField(id, value, isCurrency = false) {
    const element = document.getElementById(id);
    if (!element) return;
    
    // Format value if necessary
    let displayValue = value;
    
    if (isCurrency && value) {
        // Format as currency
        displayValue = typeof value === 'number' ? 
            `$${value.toFixed(2)}` : 
            `$${value}`;
    }
    
    // Update element
    element.textContent = displayValue || 'N/A';
    
    // Add not-available class if no value
    if (!value) {
        element.classList.add('not-available');
    } else {
        element.classList.remove('not-available');
    }
}

/**
 * Display line items in a table
 */
function displayLineItems(lineItems) {
    const tableBody = document.getElementById('lineItemsTable');
    if (!tableBody) return;
    
    // Clear previous items
    tableBody.innerHTML = '';
    
    // Check if line items exist
    if (!lineItems || lineItems.length === 0) {
        // Show empty state
        const emptyRow = document.createElement('tr');
        emptyRow.innerHTML = `
            <td colspan="5" class="text-center">No line items found</td>
        `;
        tableBody.appendChild(emptyRow);
        return;
    }
    
    // Add each line item to table
    lineItems.forEach((item, index) => {
        const row = document.createElement('tr');
        
        // Set row content
        row.innerHTML = `
            <td class="editable" data-field="description" data-index="${index}">${item.description || 'N/A'}</td>
            <td class="editable text-center" data-field="quantity" data-index="${index}">${item.quantity || 'N/A'}</td>
            <td class="editable text-end" data-field="unit_price" data-index="${index}">${item.unit_price ? `$${item.unit_price}` : 'N/A'}</td>
            <td class="editable text-end" data-field="amount" data-index="${index}">${item.amount ? `$${item.amount}` : 'N/A'}</td>
        `;
        
        tableBody.appendChild(row);
    });
}

/**
 * Make fields editable
 */
function makeFieldsEditable() {
    // Find all editable fields
    const editableFields = document.querySelectorAll('.editable');
    
    editableFields.forEach(field => {
        // Add edit on click
        field.addEventListener('click', function() {
            // Check if already in edit mode
            if (this.classList.contains('editing')) return;
            
            // Get current value
            const currentValue = this.textContent;
            const fieldName = this.dataset.field;
            const fieldIndex = this.dataset.index;
            
            // Create input element
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'form-control form-control-sm';
            input.value = currentValue.replace('$', '').replace('N/A', '');
            
            // Save original content
            this.dataset.originalContent = this.innerHTML;
            
            // Add editing class
            this.classList.add('editing');
            
            // Replace content with input
            this.innerHTML = '';
            this.appendChild(input);
            
            // Focus input
            input.focus();
            
            // Handle input blur (save changes)
            input.addEventListener('blur', function() {
                // Get new value
                let newValue = this.value.trim();
                
                // Restore original content if empty
                if (newValue === '') {
                    field.innerHTML = field.dataset.originalContent;
                    field.classList.remove('editing');
                    return;
                }
                
                // Format value if needed (e.g., currency)
                if (field.classList.contains('text-end') && !isNaN(parseFloat(newValue))) {
                    newValue = `$${parseFloat(newValue).toFixed(2)}`;
                }
                
                // Update content
                field.textContent = newValue;
                field.classList.remove('editing');
                
                // Update result data
                updateResultData(fieldName, newValue, fieldIndex);
            });
            
            // Handle enter key
            input.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    this.blur();
                } else if (e.key === 'Escape') {
                    field.innerHTML = field.dataset.originalContent;
                    field.classList.remove('editing');
                }
            });
        });
    });
}

/**
 * Update result data when edits are made
 */
function updateResultData(fieldName, newValue, fieldIndex) {
    // Get current result from session storage
    const currentResult = JSON.parse(sessionStorage.getItem('currentResult'));
    if (!currentResult) return;
    
    // Remove currency symbol if present
    if (typeof newValue === 'string' && newValue.startsWith('$')) {
        newValue = newValue.substring(1);
    }
    
    // Convert to number if applicable
    if (!isNaN(parseFloat(newValue)) && fieldName !== 'description' && fieldName !== 'invoice_number') {
        newValue = parseFloat(newValue);
    }
    
    // Update the field in the result
    if (fieldIndex !== undefined) {
        // Update line item field
        if (!currentResult.extracted_data.line_items) {
            currentResult.extracted_data.line_items = [];
        }
        
        if (!currentResult.extracted_data.line_items[fieldIndex]) {
            currentResult.extracted_data.line_items[fieldIndex] = {};
        }
        
        currentResult.extracted_data.line_items[fieldIndex][fieldName] = newValue;
    } else {
        // Update regular field
        const snakeCase = fieldName.replace(/([A-Z])/g, '_$1').toLowerCase();
        currentResult.extracted_data[snakeCase] = newValue;
    }
    
    // Update confidence score for this field
    if (!currentResult.confidence_scores) {
        currentResult.confidence_scores = {};
    }
    
    // User edited value, so confidence is high
    currentResult.confidence_scores[fieldName] = 1.0;
    
    // Save updated result
    sessionStorage.setItem('currentResult', JSON.stringify(currentResult));
    storeResult(currentResult);
    
    // If this is a total_amount or important field, update the display
    if (fieldName === 'total_amount' || fieldName === 'subtotal' || fieldName === 'tax') {
        displayConfidenceScore(currentResult.confidence_scores);
    }
}

/**
 * Store a single result in session storage
 */
function storeResult(result) {
    // Store as current result
    sessionStorage.setItem('currentResult', JSON.stringify(result));
    
    // Add to previous results
    let previousResults = JSON.parse(sessionStorage.getItem('previousResults')) || [];
    
    // Check if this result already exists
    const existingIndex = previousResults.findIndex(item => 
        item.filename === result.filename && 
        item.extracted_data?.invoice_number === result.extracted_data?.invoice_number
    );
    
    if (existingIndex >= 0) {
        // Update existing result
        previousResults[existingIndex] = result;
    } else {
        // Add new result
        previousResults.unshift(result);
        
        // Limit to 20 previous results
        if (previousResults.length > 20) {
            previousResults = previousResults.slice(0, 20);
        }
    }
    
    // Save previous results
    sessionStorage.setItem('previousResults', JSON.stringify(previousResults));
}

/**
 * Store batch results
 */
function storeBatchResults(results) {
    // Store as current batch
    sessionStorage.setItem('currentBatch', JSON.stringify(results));
    
    // Add each result to previous results
    results.forEach(result => {
        storeResult(result);
    });
}

/**
 * Load previous results
 */
function loadPreviousResults() {
    const previousResults = JSON.parse(sessionStorage.getItem('previousResults')) || [];
    const tableBody = document.getElementById('previousResultsTable');
    
    if (!tableBody) return;
    
    // Clear previous data
    tableBody.innerHTML = '';
    
    if (previousResults.length === 0) {
        // Show empty state
        const emptyRow = document.createElement('tr');
        emptyRow.innerHTML = `
            <td colspan="6" class="text-center">No previous results found</td>
        `;
        tableBody.appendChild(emptyRow);
        return;
    }
    
    // Add each result to table
    previousResults.forEach((result, index) => {
        const row = document.createElement('tr');
        
        // Calculate confidence score
        const confidenceScore = calculateAverageConfidence(result.confidence_scores);
        
        // Format data
        const invoiceNumber = result.extracted_data?.invoice_number || 'N/A';
        const vendor = result.extracted_data?.vendor_name || 'Unknown';
        const date = result.extracted_data?.date || 'N/A';
        const amount = result.extracted_data?.total_amount ? `$${result.extracted_data.total_amount}` : 'N/A';
        
        // Format timestamp
        const timestamp = result.timestamp ? 
            new Date(result.timestamp).toLocaleString() : 
            new Date().toLocaleString();
        
        // Set row content
        row.innerHTML = `
            <td>${result.filename || `Invoice ${index + 1}`}</td>
            <td>${vendor}</td>
            <td>${invoiceNumber}</td>
            <td>${date}</td>
            <td>${amount}</td>
            <td>
                <div class="progress">
                    <div class="progress-bar ${getConfidenceClass(confidenceScore)}" 
                         role="progressbar" 
                         style="width: ${confidenceScore}%" 
                         aria-valuenow="${confidenceScore}" 
                         aria-valuemin="0" 
                         aria-valuemax="100">
                        ${confidenceScore}%
                    </div>
                </div>
            </td>
            <td>${timestamp}</td>
            <td>
                <button class="btn btn-sm btn-primary view-previous-btn">
                    <i class="bi bi-eye"></i> View
                </button>
                <button class="btn btn-sm btn-outline-danger delete-previous-btn">
                    <i class="bi bi-trash"></i>
                </button>
            </td>
        `;
        
        tableBody.appendChild(row);
        
        // Add click event to view button
        const viewButton = row.querySelector('.view-previous-btn');
        if (viewButton) {
            viewButton.addEventListener('click', function() {
                // Show result in results section
                const resultsTab = document.querySelector('a[href="#results-section"]');
                if (resultsTab) {
                    resultsTab.click();
                }
                
                // Display the result
                displayResults(result);
            });
        }
        
        // Add click event to delete button
        const deleteButton = row.querySelector('.delete-previous-btn');
        if (deleteButton) {
            deleteButton.addEventListener('click', function() {
                // Remove from previous results
                previousResults.splice(index, 1);
                sessionStorage.setItem('previousResults', JSON.stringify(previousResults));
                
                // Reload table
                loadPreviousResults();
                
                // Show alert
                showAlert('Result deleted successfully', 'success');
            });
        }
    });
}
