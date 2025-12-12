// --- Monitoring/Config Navigation Logic (Style + Section Toggle) ---
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.forEach(function (tooltipTriggerEl) {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });

    const nav = document.getElementById('mainNav');
    if (nav) {
        // Find all nav links and all dashboard sections with id ending in 'Section'
        const navLinks = nav.querySelectorAll('a[data-section]');
        const sections = {};
        navLinks.forEach(link => {
            const section = link.getAttribute('data-section');
            const sectionEl = document.getElementById(section + 'Section');
            if (sectionEl) {
                sections[section] = sectionEl
            }
            else {
                console.log(`No section element found for section: ${section}`);
            }
        });


        function activateNav(link) {
            navLinks.forEach(a => {
                a.classList.remove('text-white');
                a.removeAttribute('aria-current');
            });
            link.classList.add('text-white');
            link.setAttribute('aria-current', 'page');
        }

        function showSection(section) {
            Object.values(sections).forEach(sec => sec.style.display = 'none');
            if (sections[section]) {sections[section].style.display = '';} else {
                console.log(`No section found to show for section: ${section}`);
            }
        }

        nav.addEventListener('click', function(e) {
            const link = e.target.closest('a[data-section]');
            if (link) {
                e.preventDefault();
                const section = link.getAttribute('data-section');
                activateNav(link);
                showSection(section);
            }
        });

        // Default to first nav item
        const first = nav.querySelector('a[data-section]');
        if (first) {
            activateNav(first);
            showSection(first.getAttribute('data-section'));
        }
    }
});
let ws = null;
let reconnectAttempts = 0;
let reconnectTimer = null;
let connectionTimer = null;
const reconnectDelay = 5000; // Fixed 5 second delay between reconnect attempts
const connectionTimeout = 5000; // 5 second timeout for connection attempts

function connectWebSocket() {
    // Clear any existing reconnect timer
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    // Clear any existing connection timeout
    if (connectionTimer) {
        clearTimeout(connectionTimer);
        connectionTimer = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    console.log('Attempting WebSocket connection to:', wsUrl);

    try {
        // Close existing connection if any
        if (ws && ws.readyState !== WebSocket.CLOSED) {
            ws.close();
        }

        ws = new WebSocket(wsUrl);

        // Set a timeout for connection attempt
        connectionTimer = setTimeout(() => {
            console.log('WebSocket connection timeout');
            if (ws && ws.readyState !== WebSocket.OPEN) {
                ws.close();
                scheduleReconnect();
            }
        }, connectionTimeout);

        ws.onopen = () => {
            console.log('WebSocket connected successfully');
            if (connectionTimer) {
                clearTimeout(connectionTimer);
                connectionTimer = null;
            }
            reconnectAttempts = 0;
            updateWSStatus(true);
        };

        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            if (message.type === 'status') {
                updateStatus(message.data);
            } else if (message.type === 'log') {
                appendLog(message.data);
            }
        };

        ws.onclose = (event) => {
            console.log('WebSocket closed', event.code, event.reason);
            if (connectionTimer) {
                clearTimeout(connectionTimer);
                connectionTimer = null;
            }
            ws = null;
            scheduleReconnect();
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            console.log('WebSocket readyState:', ws?.readyState);
            // Close will be called automatically after error
        };
    } catch (error) {
        console.error('Failed to create WebSocket:', error);
        if (connectionTimer) {
            clearTimeout(connectionTimer);
            connectionTimer = null;
        }
        ws = null;
        scheduleReconnect();
    }
}

function scheduleReconnect() {
    // Fixed 5 second delay between reconnect attempts
    const delay = reconnectDelay;

    const reconnectMsg = 'reconnecting';
    updateWSStatus(false, reconnectMsg);

    console.log(`Scheduling reconnect in ${delay/1000}s... (attempt ${reconnectAttempts + 1})`);

    reconnectAttempts++;
    reconnectTimer = setTimeout(connectWebSocket, delay);
}

function updateWSStatus(connected, reconnectInfo = '') {
    const statusEl = document.getElementById('wsStatus');

    if (connected) {
        statusEl.innerHTML = '<span class="badge rounded-pill bg-success" data-bs-toggle="tooltip" data-bs-placement="bottom" title="Dashboard connected - receiving live updates">Connected</span>';
    } else if (reconnectInfo) {
        statusEl.innerHTML = '<span class="badge rounded-pill bg-warning text-dark" data-bs-toggle="tooltip" data-bs-placement="bottom" title="Dashboard reconnecting - attempting to restore connection">Reconnecting</span>';
    } else {
        statusEl.innerHTML = '<span class="badge rounded-pill bg-danger" data-bs-toggle="tooltip" data-bs-placement="bottom" title="Dashboard disconnected - no live updates">Disconnected</span>';
    }

    // Reinitialize tooltips after updating the DOM
    const tooltipTrigger = statusEl.querySelector('[data-bs-toggle="tooltip"]');
    if (tooltipTrigger) {
        new bootstrap.Tooltip(tooltipTrigger);
    }
}

function updateStatus(status) {
    document.getElementById('hardwareAdapter').textContent = status.hardware_adapter || '-';
    document.getElementById('telescopeConnected').innerHTML = status.telescope_connected
        ? '<span class="badge rounded-pill bg-success">Connected</span>'
        : '<span class="badge rounded-pill bg-danger">Disconnected</span>';
    document.getElementById('cameraConnected').innerHTML = status.camera_connected
        ? '<span class="badge rounded-pill bg-success">Connected</span>'
        : '<span class="badge rounded-pill bg-danger">Disconnected</span>';
    document.getElementById('currentTask').textContent = status.current_task || 'None';
    document.getElementById('tasksPending').textContent = status.tasks_pending || '0';

    if (status.telescope_ra !== null) {
        document.getElementById('telescopeRA').textContent = status.telescope_ra.toFixed(4) + '°';
    }
    if (status.telescope_dec !== null) {
        document.getElementById('telescopeDEC').textContent = status.telescope_dec.toFixed(4) + '°';
    }

    // Update ground station information
    const gsNameEl = document.getElementById('groundStationName');
    const taskScopeButton = document.getElementById('taskScopeButton');

    if (status.ground_station_name && status.ground_station_url) {
        gsNameEl.innerHTML = `<a href="${status.ground_station_url}" target="_blank" style="color: #4299e1; text-decoration: none;">${status.ground_station_name} ↗</a>`;
        // Update the Task My Scope button
        taskScopeButton.href = status.ground_station_url;
        taskScopeButton.style.display = 'inline-block';
    } else if (status.ground_station_name) {
        gsNameEl.textContent = status.ground_station_name;
        taskScopeButton.style.display = 'none';
    } else {
        gsNameEl.textContent = '-';
        taskScopeButton.style.display = 'none';
    }
}

async function loadTasks() {
    try {
        const response = await fetch('/api/tasks');
        const tasks = await response.json();
        const taskList = document.getElementById('taskList');

        if (tasks.length === 0) {
            taskList.innerHTML = '<p style="color: #a0aec0;">No pending tasks</p>';
        } else {
            taskList.innerHTML = tasks.map(task => `
                <div class="task-item">
                    <div class="task-id">${task.id}</div>
                    <div style="font-size: 0.9em; color: #718096;">
                        Start: ${new Date(task.start_time).toLocaleString()}
                    </div>
                    <div style="font-size: 0.9em; color: #718096;">
                        Status: ${task.status}
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('Failed to load tasks:', error);
    }
}

async function loadLogs() {
    try {
        const response = await fetch('/api/logs?limit=100');
        const data = await response.json();
        const logContainer = document.getElementById('logContainer');

        if (data.logs.length === 0) {
            logContainer.innerHTML = '<p style="color: #a0aec0;">No logs available</p>';
        } else {
            logContainer.innerHTML = '';
            data.logs.forEach(log => {
                appendLog(log);
            });
            // Scroll to bottom
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    } catch (error) {
        console.error('Failed to load logs:', error);
    }
}

function stripAnsiCodes(text) {
    // Remove ANSI color codes (e.g., [92m, [0m, etc.)
    return text.replace(/\x1B\[\d+m/g, '').replace(/\[\d+m/g, '');
}

function levelColor(level) {
    return {
        'DEBUG': '#a0aec0',
        'INFO': '#48bb78',
        'WARNING': '#f6ad55',
        'ERROR': '#f56565',
        'CRITICAL': '#c53030'
    }[level] || '#e2e8f0'
}

function appendLog(log) {
    const logContainer = document.getElementById('logContainer');
    const logEntry = document.createElement('div');
    logEntry.style.marginBottom = '4px';

    const levelColorValue = levelColor(log.level);
    const timestamp = new Date(log.timestamp).toLocaleTimeString();
    const cleanMessage = stripAnsiCodes(log.message);

    logEntry.innerHTML = `
        <span style="color: #a0aec0;">${timestamp}</span>
        <span style="color: ${levelColorValue}; font-weight: bold; margin: 0 8px;">${log.level}</span>
        <span style="color: #e2e8f0;">${cleanMessage}</span>
    `;

    logContainer.appendChild(logEntry);

    const scrollParent = logContainer.closest('.accordion-body');
    if (scrollParent) {
        const isNearBottom = (scrollParent.scrollHeight - scrollParent.scrollTop - scrollParent.clientHeight) < 100;
        if (isNearBottom) {
            logEntry.scrollIntoView({ behavior: 'smooth', block: 'end' });
        }
    }
}

// --- Configuration Management ---
let currentAdapterSchema = [];

async function checkConfigStatus() {
    try {
        const response = await fetch('/api/config/status');
        const status = await response.json();

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

async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const config = await response.json();

        if (response.status === 503) {
            console.warn('Configuration not available yet');
            return;
        }

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

async function loadAdapterSchema(adapterName) {
    try {
        const response = await fetch(`/api/hardware-adapters/${adapterName}/schema`);
        const data = await response.json();

        if (response.ok) {
            currentAdapterSchema = data.schema || [];
            renderAdapterSettings(currentAdapterSchema);
        } else {
            console.error('Failed to load adapter schema:', data.error);
            showConfigError(`Failed to load settings for ${adapterName}: ${data.error}`);
        }
    } catch (error) {
        console.error('Failed to load adapter schema:', error);
        showConfigError(`Failed to load settings for ${adapterName}`);
    }
}

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
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (response.ok) {
            showConfigSuccess(result.message || 'Configuration saved and applied successfully!');
        } else {
            showConfigError(result.error || result.message || 'Failed to save configuration');
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

function showConfigError(message) {
    const errorDiv = document.getElementById('configError');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
}

function showConfigSuccess(message) {
    const successDiv = document.getElementById('configSuccess');
    successDiv.textContent = message;
    successDiv.style.display = 'block';

    // Auto-hide after 5 seconds
    setTimeout(() => {
        successDiv.style.display = 'none';
    }, 5000);
}

function hideConfigMessages() {
    document.getElementById('configError').style.display = 'none';
    document.getElementById('configSuccess').style.display = 'none';
}

function showConfigSection() {
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

// Event listeners for configuration
document.addEventListener('DOMContentLoaded', function() {
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
});



// --- Roll-up Terminal Overlay Logic (Bootstrap Accordion) ---
let isLogExpanded = false;
let latestLog = null;

function updateLatestLogLine() {
    const latestLogLine = document.getElementById('latestLogLine');
    if (!latestLogLine) return;
    if (isLogExpanded) {
        latestLogLine.textContent = 'Logs';
        return;
    }
    if (latestLog) {
        const levelColorValue = levelColor(latestLog.level);
        const timestamp = new Date(latestLog.timestamp).toLocaleTimeString();
        const cleanMessage = stripAnsiCodes(latestLog.message);
        latestLogLine.innerHTML = `
            <span style=\"color: #a0aec0;\">${timestamp}</span>
            <span style=\"color: ${levelColorValue}; font-weight: bold; margin: 0 8px;\">${latestLog.level}</span>
            <span style=\"color: #e2e8f0;\">${cleanMessage}</span>
        `;
    } else {
        latestLogLine.textContent = '';
    }
}

window.addEventListener('DOMContentLoaded', () => {
    // Bootstrap accordion events for log terminal
    const logAccordionCollapse = document.getElementById('logAccordionCollapse');
    if (logAccordionCollapse) {
        logAccordionCollapse.addEventListener('shown.bs.collapse', () => {
            isLogExpanded = true;
            updateLatestLogLine();
            const logContainer = document.getElementById('logContainer');
            if (logContainer) {
                setTimeout(() => {
                    const lastLog = logContainer.lastElementChild;
                    if (lastLog) {
                        lastLog.scrollIntoView({ behavior: 'smooth', block: 'end' });
                    } else {
                        logContainer.scrollTop = logContainer.scrollHeight;
                    }
                }, 100);
            }
        });
        logAccordionCollapse.addEventListener('hide.bs.collapse', () => {
            isLogExpanded = false;
            updateLatestLogLine();
        });
    }
    // Start collapsed by default
    isLogExpanded = false;
    updateLatestLogLine();
});
// --- End Roll-up Terminal Overlay Logic ---

// Patch appendLog to update latestLog and handle collapsed state
const origAppendLog = appendLog;
appendLog = function(log) {
    latestLog = log;
    if (!isLogExpanded) {
        updateLatestLogLine();
    }
    origAppendLog(log);
};

// Patch loadLogs to only show latest log in collapsed mode
const origLoadLogs = loadLogs;
loadLogs = async function() {
    await origLoadLogs();
    if (!isLogExpanded) {
        updateLatestLogLine();
    }
};

// Initialize
connectWebSocket();
checkConfigStatus();  // Check if configuration is needed
loadConfig();
loadTasks();
loadLogs();

// Refresh tasks periodically
setInterval(loadTasks, 10000);
