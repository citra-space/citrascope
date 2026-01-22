// Configuration management for CitraScope

import { getConfig, saveConfig, getConfigStatus, getHardwareAdapters, getAdapterSchema } from './api.js';
import { getFilterColor } from './filters.js';

// API Host constants - must match backend constants in app.py
const PROD_API_HOST = 'api.citra.space';
const DEV_API_HOST = 'dev.api.citra.space';
const DEFAULT_API_PORT = 443;

let currentAdapterSchema = [];
export let currentConfig = {};
let savedAdapter = null; // Track the currently saved adapter

export async function initConfig() {
    // Populate hardware adapter dropdown
    await loadAdapterOptions();

    // Hardware adapter selection change
    const adapterSelect = document.getElementById('hardwareAdapterSelect');
    if (adapterSelect) {
        adapterSelect.addEventListener('change', async function(e) {
            const adapter = e.target.value;
            if (adapter) {
                await loadAdapterSchema(adapter);
                await loadFilterConfig();
            } else {
                document.getElementById('adapter-settings-container').innerHTML = '';
                const filterSection = document.getElementById('filterConfigSection');
                if (filterSection) filterSection.style.display = 'none';
            }
        });
    }

    // API endpoint selection change
    const apiEndpointSelect = document.getElementById('apiEndpoint');
    if (apiEndpointSelect) {
        apiEndpointSelect.addEventListener('change', function(e) {
            const customContainer = document.getElementById('customHostContainer');
            if (e.target.value === 'custom') {
                customContainer.style.display = 'block';
            } else {
                customContainer.style.display = 'none';
            }
        });
    }

    // Config form submission
    const configForm = document.getElementById('configForm');
    if (configForm) {
        configForm.addEventListener('submit', saveConfiguration);
    }

    // Load initial config
    await loadConfiguration();
    checkConfigStatus();
}

/**
 * Check if configuration is needed and show setup wizard if not configured
 */
async function checkConfigStatus() {
    try {
        const status = await getConfigStatus();

        if (!status.configured) {
            // Show setup wizard if not configured
            const wizardModal = new bootstrap.Modal(document.getElementById('setupWizard'));
            wizardModal.show();
        }

        if (status.error) {
            showConfigError(status.error);
        }
    } catch (error) {
        console.error('Failed to check config status:', error);
    }
}

/**
 * Load available hardware adapters and populate dropdown
 */
async function loadAdapterOptions() {
    try {
        const data = await getHardwareAdapters();
        const adapterSelect = document.getElementById('hardwareAdapterSelect');

        if (adapterSelect && data.adapters) {
            // Clear existing options except the first placeholder
            while (adapterSelect.options.length > 1) {
                adapterSelect.remove(1);
            }

            // Add options from API
            data.adapters.forEach(adapterName => {
                const option = document.createElement('option');
                option.value = adapterName;
                option.textContent = data.descriptions[adapterName] || adapterName;
                adapterSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Failed to load hardware adapters:', error);
    }
}

/**
 * Load configuration from API and populate form
 */
async function loadConfiguration() {
    try {
        const config = await getConfig();
        currentConfig = config; // Save for reuse when saving
        savedAdapter = config.hardware_adapter; // Track saved adapter

        // Display config file path
        const configPathElement = document.getElementById('configFilePath');
        if (configPathElement && config.config_file_path) {
            configPathElement.textContent = config.config_file_path;
        }

        // Display log file path
        const logPathElement = document.getElementById('logFilePath');
        if (logPathElement) {
            if (config.log_file_path) {
                logPathElement.textContent = config.log_file_path;
            } else {
                logPathElement.textContent = 'Disabled';
            }
        }

        // Display images directory path
        const imagesDirElement = document.getElementById('imagesDirPath');
        if (imagesDirElement && config.images_dir_path) {
            imagesDirElement.textContent = config.images_dir_path;
        }

        // API endpoint selector
        const apiEndpointSelect = document.getElementById('apiEndpoint');
        const customHostContainer = document.getElementById('customHostContainer');
        const customHost = document.getElementById('customHost');
        const customPort = document.getElementById('customPort');
        const customUseSsl = document.getElementById('customUseSsl');

        if (config.host === PROD_API_HOST) {
            apiEndpointSelect.value = 'production';
            customHostContainer.style.display = 'none';
        } else if (config.host === DEV_API_HOST) {
            apiEndpointSelect.value = 'development';
            customHostContainer.style.display = 'none';
        } else {
            apiEndpointSelect.value = 'custom';
            customHostContainer.style.display = 'block';
            customHost.value = config.host || '';
            customPort.value = config.port || DEFAULT_API_PORT;
            customUseSsl.checked = config.use_ssl !== undefined ? config.use_ssl : true;
        }

        // Core fields
        document.getElementById('personal_access_token').value = config.personal_access_token || '';
        document.getElementById('telescopeId').value = config.telescope_id || '';
        document.getElementById('hardwareAdapterSelect').value = config.hardware_adapter || '';
        document.getElementById('logLevel').value = config.log_level || 'INFO';
        document.getElementById('keep_images').checked = config.keep_images || false;
        document.getElementById('file_logging_enabled').checked = config.file_logging_enabled !== undefined ? config.file_logging_enabled : true;

        // Load autofocus settings (top-level)
        const scheduledAutofocusEnabled = document.getElementById('scheduled_autofocus_enabled');
        const autofocusInterval = document.getElementById('autofocus_interval_minutes');
        if (scheduledAutofocusEnabled) {
            scheduledAutofocusEnabled.checked = config.scheduled_autofocus_enabled || false;
        }
        if (autofocusInterval) {
            autofocusInterval.value = config.autofocus_interval_minutes || 60;
        }

        // Load adapter-specific settings if adapter is selected
        if (config.hardware_adapter) {
            await loadAdapterSchema(config.hardware_adapter, config.adapter_settings || {});
            populateAdapterSettings(config.adapter_settings || {});
        }
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

/**
 * Load adapter schema and render settings form
 */
async function loadAdapterSchema(adapterName, currentSettings = {}) {
    try {
        // Pass current adapter settings for dynamic schema generation
        const settingsParam = Object.keys(currentSettings).length > 0
            ? `?current_settings=${encodeURIComponent(JSON.stringify(currentSettings))}`
            : '';

        const response = await fetch(`/api/hardware-adapters/${adapterName}/schema${settingsParam}`);
        const data = await response.json();

        currentAdapterSchema = data.schema || [];
        renderAdapterSettings(currentAdapterSchema);
    } catch (error) {
        console.error('Failed to load adapter schema:', error);
        showConfigError(`Failed to load settings for ${adapterName}`);
    }
}

/**
 * Render adapter-specific settings form
 */
function renderAdapterSettings(schema) {
    const container = document.getElementById('adapter-settings-container');

    if (!schema || schema.length === 0) {
        container.innerHTML = '';
        return;
    }

    let html = '<h5 class="mb-3">Adapter Settings</h5><div class="row g-3 mb-4">';

    schema.forEach(field => {
        // Skip readonly fields (handled elsewhere in UI)
        if (field.readonly) {
            return;
        }

        const isRequired = field.required ? '<span class="text-danger">*</span>' : '';
        const placeholder = field.placeholder || '';
        const description = field.description || '';
        const displayName = field.friendly_name || field.name;

        html += '<div class="col-12 col-md-6">';
        html += `<label for="adapter_${field.name}" class="form-label">${displayName} ${isRequired}</label>`;

        if (field.type === 'bool') {
            html += `<div class="form-check mt-2">`;
            html += `<input class="form-check-input adapter-setting" type="checkbox" id="adapter_${field.name}" data-field="${field.name}" data-type="${field.type}">`;
            html += `<label class="form-check-label" for="adapter_${field.name}">${description}</label>`;
            html += `</div>`;
        } else if (field.options && field.options.length > 0) {
            const displayName = field.friendly_name || field.name;
            html += `<select id="adapter_${field.name}" class="form-select adapter-setting" data-field="${field.name}" data-type="${field.type}" ${field.required ? 'required' : ''}>`;
            html += `<option value="">-- Select ${displayName} --</option>`;
            field.options.forEach(opt => {
                // Handle both object format {value, label} and plain string options
                const optValue = typeof opt === 'object' ? opt.value : opt;
                const optLabel = typeof opt === 'object' ? opt.label : opt;
                html += `<option value="${optValue}">${optLabel}</option>`;
            });
            html += `</select>`;
        } else if (field.type === 'int' || field.type === 'float') {
            const min = field.min !== undefined ? `min="${field.min}"` : '';
            const max = field.max !== undefined ? `max="${field.max}"` : '';
            html += `<input type="number" id="adapter_${field.name}" class="form-control adapter-setting" `;
            html += `data-field="${field.name}" data-type="${field.type}" `;
            html += `placeholder="${placeholder}" ${min} ${max} ${field.required ? 'required' : ''}>`;
        } else {
            // Default to text input
            const pattern = field.pattern ? `pattern="${field.pattern}"` : '';
            html += `<input type="text" id="adapter_${field.name}" class="form-control adapter-setting" `;
            html += `data-field="${field.name}" data-type="${field.type}" `;
            html += `placeholder="${placeholder}" ${pattern} ${field.required ? 'required' : ''}>`;
        }

        if (description && field.type !== 'bool') {
            html += `<small class="text-muted">${description}</small>`;
        }
        html += '</div>';
    });

    html += '</div>';
    container.innerHTML = html;

    // Add change listeners to device type fields to reload schema dynamically
    const deviceTypeFields = ['camera_type', 'mount_type', 'filter_wheel_type', 'focuser_type'];
    deviceTypeFields.forEach(fieldName => {
        const select = document.getElementById(`adapter_${fieldName}`);
        if (select) {
            select.addEventListener('change', async () => {
                // Get current adapter name
                const adapterSelect = document.getElementById('hardwareAdapterSelect');
                if (!adapterSelect || !adapterSelect.value) return;

                // Collect current settings
                const currentSettings = collectAdapterSettings();

                // Reload schema with new device type selection
                await loadAdapterSchema(adapterSelect.value, currentSettings);

                // Repopulate settings (preserves user's selections)
                populateAdapterSettings(currentSettings);
            });
        }
    });
}

/**
 * Populate adapter settings with values
 */
function populateAdapterSettings(adapterSettings) {
    Object.entries(adapterSettings).forEach(([key, value]) => {
        const input = document.getElementById(`adapter_${key}`);
        if (input) {
            if (input.type === 'checkbox') {
                input.checked = value;
            } else {
                input.value = value;
            }
        }
    });
}

/**
 * Collect adapter settings from form
 */
function collectAdapterSettings() {
    const settings = {};
    const inputs = document.querySelectorAll('.adapter-setting');

    inputs.forEach(input => {
        const fieldName = input.dataset.field;
        const fieldType = input.dataset.type;
        let value;

        if (input.type === 'checkbox') {
            value = input.checked;
        } else {
            value = input.value;
        }

        // Skip empty values for non-checkbox fields (will use backend defaults)
        if (input.type !== 'checkbox' && (value === '' || value === null || value === undefined)) {
            return;
        }

        // Type conversion
        if (fieldType === 'int') {
            value = parseInt(value, 10);
        } else if (fieldType === 'float') {
            value = parseFloat(value);
        }
        // bool type already handled above

        settings[fieldName] = value;
    });

    return settings;
}

/**
 * Save configuration form handler
 */
async function saveConfiguration(event) {
    event.preventDefault();

    const saveButton = document.getElementById('saveConfigButton');
    const buttonText = document.getElementById('saveButtonText');
    const spinner = document.getElementById('saveButtonSpinner');

    // Show loading state
    saveButton.disabled = true;
    spinner.style.display = 'inline-block';
    buttonText.textContent = 'Saving...';

    // Hide previous messages
    hideConfigMessages();

    // Determine API host settings based on endpoint selection
    const apiEndpoint = document.getElementById('apiEndpoint').value;
    let host, port, use_ssl;

    if (apiEndpoint === 'production') {
        host = PROD_API_HOST;
        port = DEFAULT_API_PORT;
        use_ssl = true;
    } else if (apiEndpoint === 'development') {
        host = DEV_API_HOST;
        port = DEFAULT_API_PORT;
        use_ssl = true;
    } else { // custom
        host = document.getElementById('customHost').value;
        port = parseInt(document.getElementById('customPort').value, 10);
        use_ssl = document.getElementById('customUseSsl').checked;
    }

    const config = {
        personal_access_token: document.getElementById('personal_access_token').value,
        telescope_id: document.getElementById('telescopeId').value,
        hardware_adapter: document.getElementById('hardwareAdapterSelect').value,
        adapter_settings: collectAdapterSettings(),
        log_level: document.getElementById('logLevel').value,
        keep_images: document.getElementById('keep_images').checked,
        file_logging_enabled: document.getElementById('file_logging_enabled').checked,
        // Autofocus settings (top-level)
        scheduled_autofocus_enabled: document.getElementById('scheduled_autofocus_enabled')?.checked || false,
        autofocus_interval_minutes: parseInt(document.getElementById('autofocus_interval_minutes')?.value || 60, 10),
        // API settings from endpoint selector
        host: host,
        port: port,
        use_ssl: use_ssl,
        // Preserve other settings from loaded config
        max_task_retries: currentConfig.max_task_retries || 3,
        initial_retry_delay_seconds: currentConfig.initial_retry_delay_seconds || 30,
        max_retry_delay_seconds: currentConfig.max_retry_delay_seconds || 300,
        log_retention_days: currentConfig.log_retention_days || 30,
        last_autofocus_timestamp: currentConfig.last_autofocus_timestamp, // Preserve timestamp
    };

    try {
        // Validate filters BEFORE saving main config (belt and suspenders)
        const inputs = document.querySelectorAll('.filter-focus-input');
        if (inputs.length > 0) {
            const checkboxes = document.querySelectorAll('.filter-enabled-checkbox');
            const enabledCount = Array.from(checkboxes).filter(cb => cb.checked).length;
            if (enabledCount === 0) {
                showConfigMessage('At least one filter must be enabled', 'danger');
                return; // Exit early without saving anything
            }
        }

        const result = await saveConfig(config);

        if (result.ok) {
            // Update saved adapter to match newly saved config
            savedAdapter = config.hardware_adapter;

            // After config saved successfully, save any modified filter focus positions
            const filterResults = await saveModifiedFilters();

            // Build success message based on results
            let message = result.data.message || 'Configuration saved and applied successfully!';
            if (filterResults.success > 0) {
                message += ` Updated ${filterResults.success} filter focus position${filterResults.success > 1 ? 's' : ''}.`;
            }
            if (filterResults.failed > 0) {
                message += ` Warning: ${filterResults.failed} filter update${filterResults.failed > 1 ? 's' : ''} failed.`;
            }

            showConfigSuccess(message);

            // Reload filters to re-enable editing for the new adapter
            await loadFilterConfig();
        } else {
            // Check for specific error codes
            const errorMsg = result.data.error || result.data.message || 'Failed to save configuration';
            showConfigError(errorMsg);
        }
    } catch (error) {
        showConfigError('Failed to save configuration: ' + error.message);
    } finally {
        // Reset button state
        saveButton.disabled = false;
        spinner.style.display = 'none';
        buttonText.textContent = 'Save Configuration';
    }
}

/**
 * Create and show a Bootstrap toast notification
 * @param {string} message - The message to display
 * @param {string} type - 'danger' for errors, 'success' for success messages
 * @param {boolean} autohide - Whether to auto-hide the toast
 */
function createToast(message, type = 'danger', autohide = false) {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        console.error('Toast container not found');
        return;
    }

    // Create toast element
    const toastId = `toast-${Date.now()}`;
    const toastHTML = `
        <div id="${toastId}" class="toast text-bg-${type}" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header text-bg-${type}">
                <strong class="me-auto">CitraScope</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;

    // Insert toast into container
    toastContainer.insertAdjacentHTML('beforeend', toastHTML);

    // Get the toast element and initialize Bootstrap toast
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, {
        autohide: autohide,
        delay: 5000
    });

    // Remove toast element from DOM after it's hidden
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });

    // Show the toast
    toast.show();
}

/**
 * Show configuration error message
 */
function showConfigError(message) {
    createToast(message, 'danger', false);
}

/**
 * Show configuration message (can be error or success)
 */
function showConfigMessage(message, type = 'danger') {
    if (type === 'danger') {
        showConfigError(message);
    } else {
        showConfigSuccess(message);
    }
}

/**
 * Show configuration success message
 */
function showConfigSuccess(message) {
    createToast(message, 'success', true);
}

/**
 * Hide all configuration messages (no-op for toast compatibility)
 */
function hideConfigMessages() {
    // No-op - toasts handle their own hiding
}

/**
 * Show configuration section (called from setup wizard)
 */
export function showConfigSection() {
    // Close setup wizard modal
    const wizardModal = bootstrap.Modal.getInstance(document.getElementById('setupWizard'));
    if (wizardModal) {
        wizardModal.hide();
    }

    // Show config section
    const configLink = document.querySelector('a[data-section="config"]');
    if (configLink) {
        configLink.click();
    }
}

/**
 * Load and display filter configuration
 */
async function loadFilterConfig() {
    const filterSection = document.getElementById('filterConfigSection');
    const changeMessage = document.getElementById('filterAdapterChangeMessage');
    const tableContainer = document.getElementById('filterTableContainer');

    // Check if selected adapter matches saved adapter
    const adapterSelect = document.getElementById('hardwareAdapterSelect');
    const selectedAdapter = adapterSelect ? adapterSelect.value : null;

    if (selectedAdapter && savedAdapter && selectedAdapter !== savedAdapter) {
        // Adapter has changed but not saved yet - show message and hide table
        if (filterSection) filterSection.style.display = 'block';
        if (changeMessage) changeMessage.style.display = 'block';
        if (tableContainer) tableContainer.style.display = 'none';
        return;
    }

    // Hide message and show table when adapters match
    if (changeMessage) changeMessage.style.display = 'none';
    if (tableContainer) tableContainer.style.display = 'block';

    try {
        const response = await fetch('/api/adapter/filters');

        if (response.status === 404 || response.status === 503) {
            // Adapter doesn't support filters or isn't available
            if (filterSection) filterSection.style.display = 'none';
            return;
        }

        const data = await response.json();

        if (response.ok && data.filters) {
            // Show the filter section
            if (filterSection) filterSection.style.display = 'block';

            // Update enabled filters display on dashboard
            updateEnabledFiltersDisplay(data.filters);

            // Populate filter table
            const tbody = document.getElementById('filterTableBody');
            const noFiltersMsg = document.getElementById('noFiltersMessage');

            if (tbody) {
                tbody.innerHTML = '';
                const filters = data.filters;
                const filterIds = Object.keys(filters).sort();

                if (filterIds.length === 0) {
                    if (noFiltersMsg) noFiltersMsg.style.display = 'block';
                } else {
                    if (noFiltersMsg) noFiltersMsg.style.display = 'none';

                    filterIds.forEach(filterId => {
                        const filter = filters[filterId];
                        const isEnabled = filter.enabled !== undefined ? filter.enabled : true;
                        const filterColor = getFilterColor(filter.name);
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>
                                <input type="checkbox"
                                       class="form-check-input filter-enabled-checkbox"
                                       data-filter-id="${filterId}"
                                       ${isEnabled ? 'checked' : ''}>
                            </td>
                            <td>
                                <span class="badge" style="background-color: ${filterColor}; color: white;">${filter.name}</span>
                            </td>
                            <td>
                                <input type="number"
                                       class="form-control form-control-sm filter-focus-input"
                                       data-filter-id="${filterId}"
                                       value="${filter.focus_position}"
                                       min="0"
                                       step="1">
                            </td>
                        `;
                        tbody.appendChild(row);
                    });
                }
            }
        } else {
            if (filterSection) filterSection.style.display = 'none';
        }
    } catch (error) {
        console.error('Error loading filter config:', error);
        if (filterSection) filterSection.style.display = 'none';
    }
}

/**
 * Save all filter focus positions and enabled states (called during main config save)
 * Returns: Object with { success: number, failed: number }
 */
async function saveModifiedFilters() {
    const inputs = document.querySelectorAll('.filter-focus-input');
    if (inputs.length === 0) return { success: 0, failed: 0 }; // No filters to save

    // Belt and suspenders: Validate at least one filter is enabled before saving
    const checkboxes = document.querySelectorAll('.filter-enabled-checkbox');
    const enabledCount = Array.from(checkboxes).filter(cb => cb.checked).length;
    if (enabledCount === 0) {
        showConfigMessage('At least one filter must be enabled', 'danger');
        return { success: 0, failed: inputs.length };
    }

    // Collect all filter updates into array
    const filterUpdates = [];
    for (const input of inputs) {
        const filterId = input.dataset.filterId;
        const focusPosition = parseInt(input.value);

        if (isNaN(focusPosition) || focusPosition < 0) {
            continue; // Skip invalid entries
        }

        // Get enabled state from corresponding checkbox
        const checkbox = document.querySelector(`.filter-enabled-checkbox[data-filter-id="${filterId}"]`);
        const enabled = checkbox ? checkbox.checked : true;

        filterUpdates.push({
            filter_id: filterId,
            focus_position: focusPosition,
            enabled: enabled
        });
    }

    if (filterUpdates.length === 0) {
        return { success: 0, failed: 0 };
    }

    // Send single batch update
    try {
        const response = await fetch('/api/adapter/filters/batch', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(filterUpdates)
        });

        if (response.ok) {
            const data = await response.json();
            const successCount = data.updated_count || 0;

            // After batch update, sync to backend
            try {
                const syncResponse = await fetch('/api/adapter/filters/sync', {
                    method: 'POST'
                });
                if (!syncResponse.ok) {
                    console.error('Failed to sync filters to backend');
                }
            } catch (error) {
                console.error('Error syncing filters to backend:', error);
            }

            return { success: successCount, failed: 0 };
        } else {
            const data = await response.json();
            const errorMsg = data.error || 'Unknown error';
            console.error(`Failed to save filters: ${errorMsg}`);

            // Show error to user
            if (response.status === 400 && errorMsg.includes('last enabled filter')) {
                showConfigMessage(errorMsg, 'danger');
            }

            return { success: 0, failed: filterUpdates.length };
        }
    } catch (error) {
        console.error('Error saving filters:', error);
        return { success: 0, failed: filterUpdates.length };
    }
}

/**
 * Trigger or cancel autofocus routine
 */
async function triggerAutofocus() {
    const button = document.getElementById('runAutofocusButton');
    const buttonText = document.getElementById('autofocusButtonText');
    const buttonSpinner = document.getElementById('autofocusButtonSpinner');

    if (!button || !buttonText || !buttonSpinner) return;

    // Check if this is a cancel action
    const isCancel = button.dataset.action === 'cancel';

    if (isCancel) {
        // Cancel autofocus
        try {
            const response = await fetch('/api/adapter/autofocus/cancel', {
                method: 'POST'
            });
            const data = await response.json();

            if (response.ok && data.success) {
                showToast('Autofocus cancelled', 'info');
                updateAutofocusButton(false);
            } else {
                showToast('Nothing to cancel', 'warning');
            }
        } catch (error) {
            console.error('Error cancelling autofocus:', error);
            showToast('Failed to cancel autofocus', 'error');
        }
        return;
    }

    // Request autofocus
    button.disabled = true;
    buttonSpinner.style.display = 'inline-block';

    try {
        const response = await fetch('/api/adapter/autofocus', {
            method: 'POST'
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Autofocus queued', 'success');
            updateAutofocusButton(true);
        } else {
            showToast(data.error || 'Autofocus request failed', 'error');
        }
    } catch (error) {
        console.error('Error triggering autofocus:', error);
        showToast('Failed to trigger autofocus', 'error');
    } finally {
        button.disabled = false;
        buttonSpinner.style.display = 'none';
    }
}

/**
 * Update autofocus button state based on whether autofocus is queued
 */
function updateAutofocusButton(isQueued) {
    const button = document.getElementById('runAutofocusButton');
    const buttonText = document.getElementById('autofocusButtonText');

    if (!button || !buttonText) return;

    if (isQueued) {
        buttonText.textContent = 'Cancel Autofocus';
        button.dataset.action = 'cancel';
        button.classList.remove('btn-outline-primary');
        button.classList.add('btn-outline-warning');
    } else {
        buttonText.textContent = 'Run Autofocus';
        button.dataset.action = 'request';
        button.classList.remove('btn-outline-warning');
        button.classList.add('btn-outline-primary');
    }
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Use Bootstrap toast if available, otherwise fallback to alert
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        console.log(`Toast (${type}): ${message}`);
        return;
    }

    const toastId = `toast-${Date.now()}`;
    const bgClass = type === 'success' ? 'bg-success' :
                    type === 'error' ? 'bg-danger' :
                    type === 'warning' ? 'bg-warning' : 'bg-info';

    const toastHtml = `
        <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;

    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: 3000 });
    toast.show();

    // Remove from DOM after hidden
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

/**
 * Initialize filter configuration on page load
 */
export async function initFilterConfig() {
    // Load filter config when config section is visible
    await loadFilterConfig();
}

/**
 * Update the enabled filters display on the dashboard.
 * @param {Object} filters - Filter configuration object
 */
function updateEnabledFiltersDisplay(filters) {
    const filtersEl = document.getElementById('enabledFilters');
    if (!filtersEl) return;

    const enabledFilters = Object.values(filters)
        .filter(filter => filter.enabled !== false)
        .map(filter => filter.name);

    if (enabledFilters.length > 0) {
        filtersEl.innerHTML = enabledFilters.map(filterName => {
            const color = getFilterColor(filterName);
            return `<span class="badge me-1" style="background-color: ${color}; color: white;">${filterName}</span>`;
        }).join('');
    } else {
        filtersEl.textContent = '-';
    }
}

/**
 * Setup autofocus button event listener (call once during init)
 */
export function setupAutofocusButton() {
    const autofocusBtn = document.getElementById('runAutofocusButton');
    if (autofocusBtn) {
        autofocusBtn.addEventListener('click', triggerAutofocus);
    }
}

// Make showConfigSection available globally for onclick handlers in HTML
window.showConfigSection = showConfigSection;
