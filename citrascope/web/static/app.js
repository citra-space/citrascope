let ws = null;
let reconnectAttempts = 0;
let reconnectTimer = null;
let connectionTimer = null;
const maxReconnectDelay = 30000; // Max 30 seconds between attempts
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
    // Calculate reconnect delay with exponential backoff
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), maxReconnectDelay);

    const reconnectMsg = `(reconnecting in ${delay/1000}s, attempt ${reconnectAttempts + 1})`;
    updateWSStatus(false, reconnectMsg);

    console.log(`Scheduling reconnect in ${delay/1000}s... (attempt ${reconnectAttempts + 1})`);

    reconnectAttempts++;
    reconnectTimer = setTimeout(connectWebSocket, delay);
}

function updateWSStatus(connected, reconnectInfo = '') {
    const statusEl = document.getElementById('wsStatus');
    const textEl = document.getElementById('wsStatusText');
    const reconnectEl = document.getElementById('reconnectInfo');

    if (connected) {
        statusEl.className = 'status-indicator status-connected';
        textEl.textContent = 'Connected';
        reconnectEl.textContent = '';
    } else {
        statusEl.className = 'status-indicator status-disconnected';
        textEl.textContent = 'Disconnected';
        reconnectEl.textContent = reconnectInfo;
    }
}

function updateStatus(status) {
    document.getElementById('hardwareAdapter').textContent = status.hardware_adapter || '-';
    document.getElementById('telescopeConnected').textContent = status.telescope_connected ? '✓ Yes' : '✗ No';
    document.getElementById('cameraConnected').textContent = status.camera_connected ? '✓ Yes' : '✗ No';
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

    if (status.last_update) {
        const date = new Date(status.last_update);
        document.getElementById('lastUpdate').textContent = `Last update: ${date.toLocaleTimeString()}`;
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

function appendLog(log) {
    const logContainer = document.getElementById('logContainer');
    const logEntry = document.createElement('div');
    logEntry.style.marginBottom = '4px';

    const levelColor = {
        'DEBUG': '#a0aec0',
        'INFO': '#48bb78',
        'WARNING': '#f6ad55',
        'ERROR': '#f56565',
        'CRITICAL': '#c53030'
    }[log.level] || '#e2e8f0';

    const timestamp = new Date(log.timestamp).toLocaleTimeString();

    // Strip ANSI codes from the message
    const cleanMessage = stripAnsiCodes(log.message);

    logEntry.innerHTML = `
        <span style="color: #a0aec0;">${timestamp}</span>
        <span style="color: ${levelColor}; font-weight: bold; margin: 0 8px;">${log.level}</span>
        <span style="color: #e2e8f0;">${cleanMessage}</span>
    `;

    logContainer.appendChild(logEntry);

    // Auto-scroll to bottom if already near bottom
    const isNearBottom = logContainer.scrollHeight - logContainer.scrollTop - logContainer.clientHeight < 100;
    if (isNearBottom) {
        logContainer.scrollTop = logContainer.scrollHeight;
    }
}

async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const config = await response.json();

        document.getElementById('hardwareAdapterSelect').value = config.hardware_adapter || 'indi';
        document.getElementById('telescopeId').value = config.telescope_id || '';
        document.getElementById('logLevel').value = config.log_level || 'INFO';
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

async function saveConfig() {
    const config = {
        hardware_adapter: document.getElementById('hardwareAdapterSelect').value,
        telescope_id: document.getElementById('telescopeId').value,
        log_level: document.getElementById('logLevel').value
    };

    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config)
        });

        const result = await response.json();
        alert(result.message);
    } catch (error) {
        alert('Failed to save configuration: ' + error.message);
    }
}



// --- Roll-up Terminal Overlay Logic ---
let isLogExpanded = false;
let latestLog = null;

function setLogTerminalState(expanded) {
    const rollup = document.getElementById('rollupTerminal');
    isLogExpanded = expanded;
    if (expanded) {
        rollup.classList.remove('rollup-terminal-collapsed');
        rollup.classList.add('rollup-terminal-expanded');
    } else {
        rollup.classList.remove('rollup-terminal-expanded');
        rollup.classList.add('rollup-terminal-collapsed');
        updateLatestLogLine();
    }
}

function updateLatestLogLine() {
    const latestLogLine = document.getElementById('latestLogLine');
    if (latestLog && latestLogLine) {
        const levelColor = {
            'DEBUG': '#a0aec0',
            'INFO': '#48bb78',
            'WARNING': '#f6ad55',
            'ERROR': '#f56565',
            'CRITICAL': '#c53030'
        }[latestLog.level] || '#e2e8f0';
        const timestamp = new Date(latestLog.timestamp).toLocaleTimeString();
        const cleanMessage = stripAnsiCodes(latestLog.message);
        latestLogLine.innerHTML = `
            <span style=\"color: #a0aec0;\">${timestamp}</span>
            <span style=\"color: ${levelColor}; font-weight: bold; margin: 0 8px;\">${latestLog.level}</span>
            <span style=\"color: #e2e8f0;\">${cleanMessage}</span>
        `;
    } else if (latestLogLine) {
        latestLogLine.textContent = '';
    }
}

window.addEventListener('DOMContentLoaded', () => {
    // Set up log terminal toggle
    const toggleBtn = document.getElementById('toggleLogTerminal');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            setLogTerminalState(!isLogExpanded);
        });
    }
    // Collapsed bar click also expands
    const collapsedBar = document.getElementById('logCollapsedBar');
    if (collapsedBar) {
        collapsedBar.addEventListener('click', () => setLogTerminalState(true));
    }
    // Start collapsed by default
    setLogTerminalState(false);
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
loadConfig();
loadTasks();
loadLogs();

// Refresh tasks periodically
setInterval(loadTasks, 10000);
