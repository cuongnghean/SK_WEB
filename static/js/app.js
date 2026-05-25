/**
 * Main JavaScript for Tax Obligation Management System
 * Provides common utilities and AJAX helpers
 */

'use strict';

// ===================================
// CONFIGURATION
// ===================================
const AppConfig = {
    apiTimeout: 30000, // 30 seconds
    maxRetries: 3,
    dateFormat: 'dd/mm/yyyy',
    currencyFormat: 'vi-VN'
};

// ===================================
// UTILITY FUNCTIONS
// ===================================

/**
 * Format currency to Vietnamese Dong
 * @param {number} amount - Amount to format
 * @returns {string} Formatted currency string
 */
function formatCurrency(amount) {
    if (amount === null || amount === undefined || isNaN(amount)) {
        return '0 VND';
    }
    return new Intl.NumberFormat(AppConfig.currencyFormat, {
        style: 'currency',
        currency: 'VND',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(amount).replace('₫', 'VND').trim();
}

/**
 * Format date to Vietnamese format
 * @param {string|Date} dateString - Date to format
 * @param {string} format - Format type ('short', 'long', 'time')
 * @returns {string} Formatted date string
 */
function formatDate(dateString, format = 'short') {
    if (!dateString) return 'N/A';
    
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return 'N/A';
    
    const options = {
        short: { day: '2-digit', month: '2-digit', year: 'numeric' },
        long: { day: '2-digit', month: 'long', year: 'numeric' },
        time: { hour: '2-digit', minute: '2-digit', second: '2-digit' },
        datetime: { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }
    };
    
    return date.toLocaleDateString('vi-VN', options[format] || options.short);
}

/**
 * Debounce function for search inputs
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Validate MST format (10 or 13 digits)
 * @param {string} mst - MST to validate
 * @returns {boolean} Is valid MST
 */
function validateMST(mst) {
    if (!mst) return false;
    const cleaned = mst.replace(/\D/g, '');
    return cleaned.length === 10 || cleaned.length === 13;
}

/**
 * Validate CCCD format (9 or 12 digits)
 * @param {string} cccd - CCCD to validate
 * @returns {boolean} Is valid CCCD
 */
function validateCCCD(cccd) {
    if (!cccd) return false;
    const cleaned = cccd.replace(/\D/g, '');
    return cleaned.length === 9 || cleaned.length === 12;
}

/**
 * Mask CCCD for display
 * @param {string} cccd - CCCD to mask
 * @returns {string} Masked CCCD
 */
function maskCCCD(cccd) {
    if (!cccd) return 'N/A';
    const cleaned = cccd.replace(/\D/g, '');
    if (cleaned.length <= 4) return '*'.repeat(cleaned.length);
    return '*'.repeat(cleaned.length - 4) + cleaned.slice(-4);
}

// ===================================
// AJAX HELPERS
// ===================================

/**
 * Make AJAX request with retry logic
 * @param {string} url - Request URL
 * @param {Object} options - Request options
 * @returns {Promise} Response promise
 */
async function ajaxRequest(url, options = {}) {
    const defaultOptions = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        timeout: AppConfig.apiTimeout
    };
    
    const config = { ...defaultOptions, ...options };
    
    // Add CSRF token if available
    const csrfToken = document.querySelector('meta[name="csrf-token"]');
    if (csrfToken) {
        config.headers['X-CSRF-Token'] = csrfToken.content;
    }
    
    let lastError;
    
    for (let attempt = 1; attempt <= AppConfig.maxRetries; attempt++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), config.timeout);
            
            config.signal = controller.signal;
            
            const response = await fetch(url, config);
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.message || `HTTP ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
            
        } catch (error) {
            lastError = error;
            
            if (error.name === 'AbortError') {
                throw new Error('Yêu cầu bị hủy do quá thời gian');
            }
            
            if (attempt < AppConfig.maxRetries) {
                await sleep(1000 * attempt); // Exponential backoff
            }
        }
    }
    
    throw lastError;
}

/**
 * Sleep utility for async operations
 * @param {number} ms - Milliseconds to sleep
 * @returns {Promise} Sleep promise
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ===================================
// UI HELPERS
// ===================================

/**
 * Show loading overlay
 */
function showLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.classList.add('active');
    }
}

/**
 * Hide loading overlay
 */
function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.classList.remove('active');
    }
}

/**
 * Show toast notification
 * @param {string} message - Message to show
 * @param {string} type - Toast type ('success', 'error', 'warning', 'info')
 */
function showToast(message, type = 'info') {
    const toastrMethod = toastr[type] || toastr.info;
    toastrMethod(message);
}

/**
 * Show confirmation dialog
 * @param {string} title - Dialog title
 * @param {string} message - Dialog message
 * @returns {Promise} User confirmation
 */
function showConfirm(title, message) {
    return new Promise((resolve) => {
        // Create modal if it doesn't exist
        let modal = document.getElementById('confirmModal');
        
        if (!modal) {
            const modalHtml = `
                <div class="modal fade" id="confirmModal" tabindex="-1">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title" id="confirmModalTitle"></h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body" id="confirmModalBody"></div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal" id="confirmCancel">Hủy</button>
                                <button type="button" class="btn btn-primary" id="confirmOk">Xác nhận</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            modal = document.getElementById('confirmModal');
        }
        
        const modalInstance = bootstrap.Modal.getOrCreateInstance(document.getElementById('confirmModal'));
        
        document.getElementById('confirmModalTitle').textContent = title;
        document.getElementById('confirmModalBody').textContent = message;
        
        const confirmBtn = document.getElementById('confirmOk');
        const cancelBtn = document.getElementById('confirmCancel');
        
        const cleanup = () => {
            confirmBtn.removeEventListener('click', handleConfirm);
            cancelBtn.removeEventListener('click', handleCancel);
        };
        
        const handleConfirm = () => {
            cleanup();
            modalInstance.hide();
            resolve(true);
        };
        
        const handleCancel = () => {
            cleanup();
            modalInstance.hide();
            resolve(false);
        };
        
        confirmBtn.addEventListener('click', handleConfirm);
        cancelBtn.addEventListener('click', handleCancel);
        
        modalInstance.show();
    });
}

/**
 * Create and show alert
 * @param {string} message - Alert message
 * @param {string} type - Alert type ('success', 'danger', 'warning', 'info')
 * @param {number} duration - Auto dismiss duration in ms (0 to not dismiss)
 * @returns {HTMLElement} Alert element
 */
function showAlert(message, type = 'info', duration = 5000) {
    const alertContainer = document.getElementById('alertContainer') || createAlertContainer();
    
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show animate-slideIn" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    alertContainer.insertAdjacentHTML('beforeend', alertHtml);
    
    const alertEl = alertContainer.lastElementChild;
    
    if (duration > 0) {
        setTimeout(() => {
            alertEl.remove();
        }, duration);
    }
    
    return alertEl;
}

/**
 * Create alert container if not exists
 * @returns {HTMLElement} Alert container
 */
function createAlertContainer() {
    const container = document.createElement('div');
    container.id = 'alertContainer';
    container.className = 'alert-container';
    container.style.cssText = 'position: fixed; top: 70px; right: 20px; z-index: 9999; width: 350px;';
    document.body.appendChild(container);
    return container;
}

// ===================================
// DATA TABLES HELPERS
// ===================================

/**
 * Initialize DataTable with default options
 * @param {string} tableId - Table element ID
 * @param {Object} options - DataTable options
 * @returns {DataTable} DataTable instance
 */
function initDataTable(tableId, options = {}) {
    const defaultOptions = {
        language: {
            url: '//cdn.datatables.net/plug-ins/1.13.8/i18n/vi.json',
            search: "Tìm kiếm:",
            lengthMenu: "Hiển thị _MENU_ dòng",
            info: "Hiển thị _START_ đến _END_ của _TOTAL_ dòng",
            paginate: {
                first: "Đầu",
                last: "Cuối",
                next: "Sau",
                previous: "Trước"
            },
            emptyTable: "Không có dữ liệu",
            zeroRecords: "Không tìm thấy kết quả"
        },
        pageLength: 25,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, "Tất cả"]],
        dom: 'Bfrtip',
        buttons: [
            'copy', 'csv', 'excel', 'pdf', 'print'
        ],
        responsive: true,
        order: [[0, 'asc']],
        drawCallback: function() {
            // Re-initialize tooltips after table redraw
            initTooltips();
        }
    };
    
    return $(`#${tableId}`).DataTable({ ...defaultOptions, ...options });
}

/**
 * Initialize tooltips
 */
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(el => new bootstrap.Tooltip(el));
}

// ===================================
// FILE UPLOAD HELPERS
// ===================================

/**
 * Upload file with progress tracking
 * @param {string} url - Upload URL
 * @param {File} file - File to upload
 * @param {Function} onProgress - Progress callback
 * @param {Object} additionalData - Additional form data
 * @returns {Promise} Upload result
 */
async function uploadFile(url, file, onProgress = () => {}, additionalData = {}) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const formData = new FormData();
        
        formData.append('file', file);
        
        for (const [key, value] of Object.entries(additionalData)) {
            formData.append(key, value);
        }
        
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                onProgress(percent, e.loaded, e.total);
            }
        });
        
        xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    resolve(JSON.parse(xhr.responseText));
                } catch {
                    resolve(xhr.responseText);
                }
            } else {
                try {
                    const error = JSON.parse(xhr.responseText);
                    reject(new Error(error.message || `Upload failed: ${xhr.status}`));
                } catch {
                    reject(new Error(`Upload failed: ${xhr.status}`));
                }
            }
        });
        
        xhr.addEventListener('error', () => {
            reject(new Error('Network error occurred'));
        });
        
        xhr.addEventListener('abort', () => {
            reject(new Error('Upload cancelled'));
        });
        
        xhr.open('POST', url);
        xhr.send(formData);
    });
}

/**
 * Validate file before upload
 * @param {File} file - File to validate
 * @param {Object} options - Validation options
 * @returns {Object} Validation result
 */
function validateFile(file, options = {}) {
    const defaults = {
        maxSize: 16 * 1024 * 1024, // 16MB
        allowedTypes: ['.xlsx', '.xls', '.csv'],
        allowedMimeTypes: [
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel',
            'text/csv'
        ]
    };
    
    const config = { ...defaults, ...options };
    
    const errors = [];
    
    // Check file size
    if (file.size > config.maxSize) {
        errors.push(`Kích thước file vượt quá ${config.maxSize / (1024 * 1024)}MB`);
    }
    
    // Check file extension
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!config.allowedTypes.includes(ext)) {
        errors.push(`Định dạng file không được hỗ trợ. Chỉ chấp nhận: ${config.allowedTypes.join(', ')}`);
    }
    
    return {
        valid: errors.length === 0,
        errors: errors
    };
}

// ===================================
// INITIALIZATION
// ===================================

/**
 * Initialize application on DOM ready
 */
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    initTooltips();
    
    // Auto-dismiss alerts after 5 seconds
    setTimeout(() => {
        const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(alert => {
            if (bootstrap && bootstrap.Alert) {
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                bsAlert.close();
            } else {
                alert.remove();
            }
        });
    }, 5000);
    
    // Add CSRF meta tag if not exists
    if (!document.querySelector('meta[name="csrf-token"]') && window.CSRF_TOKEN) {
        const meta = document.createElement('meta');
        meta.name = 'csrf-token';
        meta.content = window.CSRF_TOKEN;
        document.head.appendChild(meta);
    }
    
    // Initialize DataTables if present
    if (typeof $.fn.DataTable !== 'undefined') {
        // DataTables will be initialized per page
    }
    
    console.log('Tax Obligation System initialized');
});

// ===================================
// EXPORT
// ===================================

window.App = {
    config: AppConfig,
    formatCurrency,
    formatDate,
    debounce,
    validateMST,
    validateCCCD,
    maskCCCD,
    ajaxRequest,
    showLoading,
    hideLoading,
    showToast,
    showConfirm,
    showAlert,
    initDataTable,
    uploadFile,
    validateFile,
    sleep
};
