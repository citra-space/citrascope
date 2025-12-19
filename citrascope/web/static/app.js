// CitraScope Dashboard - Main Application
import { connectWebSocket } from './websocket.js';
import { initConfig, currentConfig } from './config.js';
import { getTasks, getLogs } from './api.js';

function updateAppUrlLinks() {
    const appUrl = currentConfig.app_url;
    [document.getElementById('appUrlLink'), document.getElementById('setupAppUrlLink')].forEach(link => {
        if (link && appUrl) {
            link.href = appUrl;
            link.textContent = appUrl.replace('https://', '');
        }
    });
}

// Global state for countdown
let nextTaskStartTime = null;
let countdownInterval = null;
let isTaskActive = false;
let currentTaskId = null;
let currentTasks = []; // Store tasks for lookup

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
    const template = document.getElementById('connectionStatusTemplate');
    const content = template.content.cloneNode(true);
    const badge = content.querySelector('.connection-status-badge');
    const statusText = content.querySelector('.status-text');

    if (connected) {
        badge.classList.add('bg-success');
        badge.setAttribute('title', 'Dashboard connected - receiving live updates');
        statusText.textContent = 'Connected';
    } else if (reconnectInfo) {
        badge.classList.add('bg-warning', 'text-dark');
        badge.setAttribute('title', 'Dashboard reconnecting - attempting to restore connection');
        statusText.textContent = 'Reconnecting';
    } else {
        badge.classList.add('bg-danger');
        badge.setAttribute('title', 'Dashboard disconnected - no live updates');
        statusText.textContent = 'Disconnected';
    }

    statusEl.innerHTML = '';
    statusEl.appendChild(content);

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
    if (status.current_task && status.current_task !== 'None') {
        isTaskActive = true;
        currentTaskId = status.current_task;
        stopCountdown();
        updateCurrentTaskDisplay();
    } else if (isTaskActive) {
        // Task just finished, set to idle state
        isTaskActive = false;
        currentTaskId = null;
        updateCurrentTaskDisplay();
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
function getCurrentTaskDetails() {
    if (!currentTaskId) return null;
    return currentTasks.find(task => task.id === currentTaskId);
}

function updateCurrentTaskDisplay() {
    const currentTaskDisplay = document.getElementById('currentTaskDisplay');
    if (!currentTaskDisplay) return;

    if (currentTaskId) {
        const taskDetails = getCurrentTaskDetails();
        if (taskDetails) {
            currentTaskDisplay.innerHTML = `
                <div class="d-flex align-items-center gap-2 mb-2">
                    <div class="spinner-border spinner-border-sm text-success" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <div class="fw-bold" style="font-size: 1.3em;">${taskDetails.target}</div>
                </div>
                <div class="text-secondary small">
                    <span>Task ID: ${currentTaskId}</span>
                </div>
            `;
        }
        // Don't show fallback - just wait for task details to arrive
    } else if (!isTaskActive && !nextTaskStartTime) {
        // Only show "No active task" if we're not in countdown mode
        currentTaskDisplay.innerHTML = '<p class="no-task-message">No active task</p>';
    }
}

function updateTasks(tasks) {
    currentTasks = tasks;
    renderTasks(tasks);
    // Re-render current task display with updated task info
    updateCurrentTaskDisplay();
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

            // Create table structure
            const table = document.createElement('table');
            table.className = 'table table-dark table-hover mb-0';

            const thead = document.createElement('thead');
            thead.innerHTML = `
                <tr>
                    <th>Target</th>
                    <th>Start Time</th>
                    <th>End Time</th>
                    <th>Status</th>
                </tr>
            `;
            table.appendChild(thead);

            const tbody = document.createElement('tbody');
            const template = document.getElementById('taskRowTemplate');

            sortedTasks.forEach(task => {
                const isActive = task.id === currentTaskId;
                const row = template.content.cloneNode(true);
                const tr = row.querySelector('.task-row');

                if (isActive) {
                    tr.classList.add('table-active');
                }

                row.querySelector('.task-target').textContent = task.target;
                row.querySelector('.task-start').textContent = formatLocalTime(task.start_time);
                row.querySelector('.task-end').textContent = task.stop_time ? formatLocalTime(task.stop_time) : '-';

                const badge = row.querySelector('.task-status');
                badge.classList.add(isActive ? 'bg-success' : 'bg-info');
                badge.textContent = isActive ? 'Active' : task.status;

                tbody.appendChild(row);
            });

            table.appendChild(tbody);
            taskList.innerHTML = '';
            taskList.appendChild(table);
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
    const template = document.getElementById('logEntryTemplate');
    const entry = template.content.cloneNode(true);

    const timestamp = new Date(log.timestamp).toLocaleTimeString();
    const cleanMessage = stripAnsiCodes(log.message);

    entry.querySelector('.log-timestamp').textContent = timestamp;
    const levelSpan = entry.querySelector('.log-level');
    levelSpan.classList.add(`log-level-${log.level}`);
    levelSpan.textContent = log.level;
    entry.querySelector('.log-message').textContent = cleanMessage;

    const logEntryElement = logContainer.appendChild(entry);

    const scrollParent = logContainer.closest('.accordion-body');
    if (scrollParent) {
        const isNearBottom = (scrollParent.scrollHeight - scrollParent.scrollTop - scrollParent.clientHeight) < 100;
        if (isNearBottom) {
            // Get the actual appended element (first child of the DocumentFragment)
            const lastEntry = logContainer.lastElementChild;
            if (lastEntry) {
                lastEntry.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }
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
        latestLogLine.textContent = 'Activity';
        return;
    }
    if (latestLog) {
        const template = document.getElementById('latestLogLineTemplate');
        const content = template.content.cloneNode(true);

        const timestamp = new Date(latestLog.timestamp).toLocaleTimeString();
        const cleanMessage = stripAnsiCodes(latestLog.message);
        // Truncate message to ~150 chars for collapsed header (approx 2 lines)
        const truncatedMessage = cleanMessage.length > 150 ? cleanMessage.substring(0, 150) + '...' : cleanMessage;

        content.querySelector('.log-timestamp').textContent = timestamp;
        const levelSpan = content.querySelector('.log-level');
        levelSpan.classList.add(`log-level-${latestLog.level}`);
        levelSpan.textContent = latestLog.level;
        content.querySelector('.log-message').textContent = truncatedMessage;

        latestLogLine.innerHTML = '';
        latestLogLine.appendChild(content);
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
document.addEventListener('DOMContentLoaded', async function() {
    // Initialize UI navigation
    initNavigation();

    // Initialize configuration management (loads config)
    await initConfig();

    // Update app URL links from loaded config
    updateAppUrlLinks();

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
