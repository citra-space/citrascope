// CitraScope Dashboard - Main Application
import { connectWebSocket } from './websocket.js';
import { initConfig } from './config.js';
import { getTasks, getLogs } from './api.js';

// --- Utility Functions ---
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

// --- Navigation Logic ---
function initNavigation() {
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
}

// --- WebSocket Status Display ---
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

// --- Status Updates ---
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

// --- Task Management ---
async function loadTasks() {
    try {
        const tasks = await getTasks();
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

// --- Log Display ---
async function loadLogs() {
    try {
        const data = await getLogs(100);
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

// --- Initialize Application ---
document.addEventListener('DOMContentLoaded', function() {
    // Initialize UI navigation
    initNavigation();

    // Initialize configuration management
    initConfig();

    // Connect WebSocket with handlers
    connectWebSocket({
        onStatus: updateStatus,
        onLog: appendLog,
        onConnectionChange: updateWSStatus
    });

    // Load initial data
    loadTasks();
    loadLogs();

    // Refresh tasks periodically
    setInterval(loadTasks, 10000);
});
