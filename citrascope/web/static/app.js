// CitraScope Dashboard - Main Application
import { connectWebSocket } from './websocket.js';
import { initConfig } from './config.js';
import { getTasks, getLogs } from './api.js';

// Global state for countdown
let nextTaskStartTime = null;
let countdownInterval = null;
let isTaskActive = false;
let currentTaskId = null;

// --- Utility Functions ---
function stripAnsiCodes(text) {
    // Remove ANSI color codes (e.g., [92m, [0m, etc.)
    return text.replace(/\x1B\[\d+m/g, '').replace(/\[\d+m/g, '');
}

function formatLocalTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
    });
}

function formatCountdown(milliseconds) {
    const totalSeconds = Math.floor(milliseconds / 1000);

    if (totalSeconds < 0) return 'Starting soon...';

    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    if (hours > 0) {
        return `${hours}h ${minutes}m ${seconds}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${seconds}s`;
    } else {
        return `${seconds}s`;
    }
}

function updateCountdown() {
    if (!nextTaskStartTime || isTaskActive) return;

    const now = new Date();
    const timeUntil = nextTaskStartTime - now;

    const currentTaskDisplay = document.getElementById('currentTaskDisplay');
    if (currentTaskDisplay && timeUntil > 0) {
        const countdown = formatCountdown(timeUntil);
        currentTaskDisplay.innerHTML = `<p class="no-task-message">No active task - next task in ${countdown}</p>`;
    }
}

function startCountdown(startTime) {
    nextTaskStartTime = new Date(startTime);

    // Clear any existing interval
    if (countdownInterval) {
        clearInterval(countdownInterval);
    }

    // Update immediately
    updateCountdown();

    // Update every second
    countdownInterval = setInterval(updateCountdown, 1000);
}

function stopCountdown() {
    nextTaskStartTime = null;
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }
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

    // Update current task display
    const currentTaskDisplay = document.getElementById('currentTaskDisplay');
    if (status.current_task && status.current_task !== 'None') {
        isTaskActive = true;
        currentTaskId = status.current_task;
        stopCountdown();
        currentTaskDisplay.innerHTML = `
            <div class="fw-semibold mb-2 task-title">${status.current_task}</div>
            <div class="text-secondary small">In progress...</div>
        `;
    } else if (isTaskActive) {
        // Task just finished, set to idle state
        isTaskActive = false;
        currentTaskId = null;
        currentTaskDisplay.innerHTML = '<p class="no-task-message">No active task</p>';
    }
    // If isTaskActive is already false, don't touch the display (countdown is updating it)

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
        gsNameEl.innerHTML = `<a href="${status.ground_station_url}" target="_blank" class="ground-station-link">${status.ground_station_name} ↗</a>`;
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
function updateTasks(tasks) {
    renderTasks(tasks);
}

async function loadTasks() {
    try {
        const tasks = await getTasks();
        renderTasks(tasks);
    } catch (error) {
        console.error('Failed to load tasks:', error);
    }
}

function renderTasks(tasks) {
    try {
        const taskList = document.getElementById('taskList');

        if (tasks.length === 0) {
            taskList.innerHTML = '<p class="p-3 text-muted-dark">No pending tasks</p>';
            stopCountdown();
        } else {
            // Sort tasks by start time (earliest first)
            const sortedTasks = tasks.sort((a, b) => new Date(a.start_time) - new Date(b.start_time));

            // Start countdown for next task if no current task is active
            if (!isTaskActive && sortedTasks.length > 0) {
                startCountdown(sortedTasks[0].start_time);
            }

            const tableHTML = `
                <table class="table table-dark table-hover mb-0">
                    <thead>
                        <tr>
                            <th>Target</th>
                            <th>Start Time</th>
                            <th>End Time</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${sortedTasks.map(task => {
                            const isActive = task.id === currentTaskId;
                            const badgeClass = isActive ? 'bg-success' : 'bg-info';
                            const statusText = isActive ? 'Active' : task.status;
                            return `
                            <tr${isActive ? ' class="table-active"' : ''}>
                                <td class="fw-semibold">${task.target}</td>
                                <td class="text-secondary small">${formatLocalTime(task.start_time)}</td>
                                <td class="text-secondary small">${task.stop_time ? formatLocalTime(task.stop_time) : '-'}</td>
                                <td><span class="badge rounded-pill ${badgeClass}">${statusText}</span></td>
                            </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            `;
            taskList.innerHTML = tableHTML;
        }
    } catch (error) {
        console.error('Failed to render tasks:', error);
    }
}

// --- Log Display ---
async function loadLogs() {
    try {
        const data = await getLogs(100);
        const logContainer = document.getElementById('logContainer');

        if (data.logs.length === 0) {
            logContainer.innerHTML = '<p class="text-muted-dark">No logs available</p>';
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
    logEntry.className = 'log-entry';

    const timestamp = new Date(log.timestamp).toLocaleTimeString();
    const cleanMessage = stripAnsiCodes(log.message);

    logEntry.innerHTML = `
        <span class="log-timestamp">${timestamp}</span>
        <span class="log-level log-level-${log.level}">${log.level}</span>
        <span class="log-message">${cleanMessage}</span>
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
        const timestamp = new Date(latestLog.timestamp).toLocaleTimeString();
        const cleanMessage = stripAnsiCodes(latestLog.message);
        latestLogLine.innerHTML = `
            <span class="log-timestamp">${timestamp}</span>
            <span class="log-level log-level-${latestLog.level}">${latestLog.level}</span>
            <span class="log-message">${cleanMessage}</span>
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
        onTasks: updateTasks,
        onConnectionChange: updateWSStatus
    });

    // Load initial data
    loadTasks();
    loadLogs();
});
