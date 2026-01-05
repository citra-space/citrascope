// Configuration management for CitraScope

import { getConfig, saveConfig, getConfigStatus, getHardwareAdapters, getAdapterSchema } from './api.js';

// API Host constants - must match backend constants in app.py
const PROD_API_HOST = 'api.citra.space';
const DEV_API_HOST = 'dev.api.citra.space';
const DEFAULT_API_PORT = 443;

let currentAdapterSchema = [];
export let currentConfig = {};

/**
 * Initialize configuration management
 */
async function fetchVersion() {
    try {
        const response = await fetch('/api/version');
        const data = await response.json();
        const versionEl = document.getElementById('citraScopeVersion');
        if (versionEl && data.version) {
            versionEl.textContent = data.version;
        }
    } catch (error) {
        console.error('Error fetching version:', error);
        const versionEl = document.getElementById('citraScopeVersion');
        if (versionEl) {
            versionEl.textContent = 'unknown';
        }
    }
}

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
            } else {
                document.getElementById('adapter-settings-container').innerHTML = '';
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
    fetchVersion();
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

        // Load adapter-specific settings if adapter is selected
        if (config.hardware_adapter) {
            await loadAdapterSchema(config.hardware_adapter);
            populateAdapterSettings(config.adapter_settings || {});
        }
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

/**
 * Load adapter schema and render settings form
 */
async function loadAdapterSchema(adapterName) {
    try {
        const data = await getAdapterSchema(adapterName);
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
                html += `<option value="${opt}">${opt}</option>`;
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

        // Type conversion
        if (value !== '' && value !== null) {
            if (fieldType === 'int') {
                value = parseInt(value, 10);
            } else if (fieldType === 'float') {
                value = parseFloat(value);
            } else if (fieldType === 'bool') {
                // Already handled above
            }
        }

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
        // API settings from endpoint selector
        host: host,
        port: port,
        use_ssl: use_ssl,
        // Preserve other settings from loaded config
        max_task_retries: currentConfig.max_task_retries || 3,
        initial_retry_delay_seconds: currentConfig.initial_retry_delay_seconds || 30,
        max_retry_delay_seconds: currentConfig.max_retry_delay_seconds || 300,
        log_retention_days: currentConfig.log_retention_days || 30,
    };

    try {
        const result = await saveConfig(config);

        if (result.ok) {
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
        } else {
            showConfigError(result.data.error || result.data.message || 'Failed to save configuration');
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
 * Show configuration error message
 */
function showConfigError(message) {
    const errorDiv = document.getElementById('configError');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
}

/**
 * Show configuration success message
 */
function showConfigSuccess(message) {
    const successDiv = document.getElementById('configSuccess');
    successDiv.textContent = message;
    successDiv.style.display = 'block';

    // Auto-hide after 5 seconds
    setTimeout(() => {
        successDiv.style.display = 'none';
    }, 5000);
}

/**
 * Hide all configuration messages
 */
function hideConfigMessages() {
    document.getElementById('configError').style.display = 'none';
    document.getElementById('configSuccess').style.display = 'none';
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
                        const row = document.createElement('tr');
                        row.innerHTML = `
                            <td>${filterId}</td>
                            <td>${filter.name}</td>
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
 * Save all filter focus positions (called during main config save)
 * Returns: Object with { success: number, failed: number }
 */
async function saveModifiedFilters() {
    const inputs = document.querySelectorAll('.filter-focus-input');
    if (inputs.length === 0) return { success: 0, failed: 0 }; // No filters to save

    let successCount = 0;
    let failedCount = 0;

    // Save all filter values
    for (const input of inputs) {
        const filterId = input.dataset.filterId;
        const focusPosition = parseInt(input.value);

        if (isNaN(focusPosition) || focusPosition < 0) {
            failedCount++;
            continue;
        }

        try {
            const response = await fetch(`/api/adapter/filters/${filterId}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ focus_position: focusPosition })
            });

            if (response.ok) {
                successCount++;
            } else {
                failedCount++;
                console.error(`Failed to save filter ${filterId}: HTTP ${response.status}`);
            }
        } catch (error) {
            failedCount++;
            console.error(`Error saving filter ${filterId}:`, error);
        }
    }

    return { success: successCount, failed: failedCount };
}

/**
 * Trigger autofocus routine
 */
async function triggerAutofocus() {
    const button = document.getElementById('runAutofocusButton');
    const buttonText = document.getElementById('autofocusButtonText');
    const buttonSpinner = document.getElementById('autofocusButtonSpinner');

    if (!button || !buttonText || !buttonSpinner) return;

    // Disable button and show spinner
    button.disabled = true;
    buttonText.textContent = 'Running Autofocus...';
    buttonSpinner.style.display = 'inline-block';

    try {
        const response = await fetch('/api/adapter/autofocus', {
            method: 'POST'
        });

        const data = await response.json();

        if (response.ok) {
            showConfigSuccess('Autofocus completed successfully');
            // Reload filter config to show updated focus positions
            await loadFilterConfig();
        } else {
            showConfigError(data.error || 'Autofocus failed');
        }
    } catch (error) {
        console.error('Error triggering autofocus:', error);
        showConfigError('Failed to trigger autofocus');
    } finally {
        // Re-enable button
        button.disabled = false;
        buttonText.textContent = 'Run Autofocus';
        buttonSpinner.style.display = 'none';
    }
}

/**
 * Initialize filter configuration on page load
 */
export async function initFilterConfig() {
    // Load filter config when config section is visible
    await loadFilterConfig();
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
