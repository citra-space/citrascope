// Configuration management for CitraScope

import { getConfig, saveConfig, getConfigStatus, getAdapterSchema } from './api.js';

let currentAdapterSchema = [];

/**
 * Initialize configuration management
 */
export function initConfig() {
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

    // Config form submission
    const configForm = document.getElementById('configForm');
    if (configForm) {
        configForm.addEventListener('submit', saveConfiguration);
    }

    // Load initial config
    loadConfiguration();
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
 * Load configuration from API and populate form
 */
async function loadConfiguration() {
    try {
        const config = await getConfig();

        // Core fields
        document.getElementById('personal_access_token').value = config.personal_access_token || '';
        document.getElementById('telescopeId').value = config.telescope_id || '';
        document.getElementById('hardwareAdapterSelect').value = config.hardware_adapter || '';
        document.getElementById('logLevel').value = config.log_level || 'INFO';
        document.getElementById('keep_images').checked = config.keep_images || false;
        document.getElementById('bypass_autofocus').checked = config.bypass_autofocus || false;

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

        html += '<div class="col-12 col-md-6">';
        html += `<label for="adapter_${field.name}" class="form-label">${field.name} ${isRequired}</label>`;

        if (field.type === 'bool') {
            html += `<div class="form-check mt-2">`;
            html += `<input class="form-check-input adapter-setting" type="checkbox" id="adapter_${field.name}" data-field="${field.name}" data-type="${field.type}">`;
            html += `<label class="form-check-label" for="adapter_${field.name}">${description}</label>`;
            html += `</div>`;
        } else if (field.options && field.options.length > 0) {
            html += `<select id="adapter_${field.name}" class="form-select adapter-setting" data-field="${field.name}" data-type="${field.type}" ${field.required ? 'required' : ''}>`;
            html += `<option value="">-- Select ${field.name} --</option>`;
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

    const config = {
        personal_access_token: document.getElementById('personal_access_token').value,
        telescope_id: document.getElementById('telescopeId').value,
        hardware_adapter: document.getElementById('hardwareAdapterSelect').value,
        adapter_settings: collectAdapterSettings(),
        log_level: document.getElementById('logLevel').value,
        keep_images: document.getElementById('keep_images').checked,
        bypass_autofocus: document.getElementById('bypass_autofocus').checked,
        // API settings (keep defaults for now)
        host: 'api.citra.space',
        port: 443,
        use_ssl: true,
        max_task_retries: 3,
        initial_retry_delay_seconds: 30,
        max_retry_delay_seconds: 300,
    };

    try {
        const result = await saveConfig(config);

        if (result.ok) {
            showConfigSuccess(result.data.message || 'Configuration saved and applied successfully!');
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

// Make showConfigSection available globally for onclick handlers in HTML
window.showConfigSection = showConfigSection;
