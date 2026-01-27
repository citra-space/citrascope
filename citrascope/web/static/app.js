// CitraScope Dashboard - Main Application
import { connectWebSocket } from './websocket.js';
import { initConfig, currentConfig, initFilterConfig, setupAutofocusButton, createToast } from './config.js';
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

// --- Version Checking ---

/**
 * Compare two semantic version strings
 * Returns: 1 if v1 > v2, -1 if v1 < v2, 0 if equal
 */
function compareVersions(v1, v2) {
    // Strip 'v' prefix if present
    v1 = v1.replace(/^v/, '');
    v2 = v2.replace(/^v/, '');

    const parts1 = v1.split('.').map(n => parseInt(n) || 0);
    const parts2 = v2.split('.').map(n => parseInt(n) || 0);

    const maxLen = Math.max(parts1.length, parts2.length);

    for (let i = 0; i < maxLen; i++) {
        const num1 = parts1[i] || 0;
        const num2 = parts2[i] || 0;

        if (num1 > num2) return 1;
        if (num1 < num2) return -1;
    }

    return 0;
}

/**
 * Fetch and display current version
 */
async function fetchVersion() {
    try {
        const response = await fetch('/api/version');
        const data = await response.json();

        // Update header version
        const headerVersionEl = document.getElementById('headerVersion');

        if (headerVersionEl && data.version) {
            // Show "dev" for development, "v" prefix for releases
            if (data.version === 'development') {
                headerVersionEl.textContent = 'dev';
            } else {
                headerVersionEl.textContent = 'v' + data.version;
            }
        }
    } catch (error) {
        console.error('Error fetching version:', error);
        const headerVersionEl = document.getElementById('headerVersion');

        if (headerVersionEl) {
            headerVersionEl.textContent = 'v?';
        }
    }
}

/**
 * Check for available updates from GitHub
 * Returns the check result for modal display
 */
async function checkForUpdates() {
    try {
        // Get current version
        const versionResponse = await fetch('/api/version');
        const versionData = await versionResponse.json();
        const currentVersion = versionData.version;

        // Check GitHub for latest release
        const githubResponse = await fetch('https://api.github.com/repos/citra-space/citrascope/releases/latest');
        if (!githubResponse.ok) {
            return { status: 'error', currentVersion };
        }

        const releaseData = await githubResponse.json();
        const latestVersion = releaseData.tag_name.replace(/^v/, '');
        const releaseUrl = releaseData.html_url;

        // Skip comparison for development versions
        if (currentVersion === 'development' || currentVersion === 'unknown') {
            return { status: 'up-to-date', currentVersion };
        }

        // Compare versions
        if (compareVersions(latestVersion, currentVersion) > 0) {
            // Update available - show indicator badge with version
            const indicator = document.getElementById('updateIndicator');
            if (indicator) {
                indicator.textContent = `${latestVersion} Available!`;
                indicator.style.display = 'inline-block';
            }

            return {
                status: 'update-available',
                currentVersion,
                latestVersion,
                releaseUrl
            };
        } else {
            // Up to date - hide indicator badge
            const indicator = document.getElementById('updateIndicator');
            if (indicator) {
                indicator.style.display = 'none';
            }

            return { status: 'up-to-date', currentVersion };
        }
    } catch (error) {
        // Network error
        console.debug('Update check failed:', error);
        return { status: 'error', currentVersion: 'unknown' };
    }
}

/**
 * Show version check modal with results
 */
async function showVersionModal() {
    const modal = new bootstrap.Modal(document.getElementById('versionModal'));
    modal.show();

    // Show loading state
    document.getElementById('versionCheckLoading').style.display = 'block';
    document.getElementById('versionCheckUpToDate').style.display = 'none';
    document.getElementById('versionCheckUpdateAvailable').style.display = 'none';
    document.getElementById('versionCheckError').style.display = 'none';

    // Perform check
    const result = await checkForUpdates();

    // Hide loading
    document.getElementById('versionCheckLoading').style.display = 'none';

    // Show appropriate result
    if (result.status === 'update-available') {
        document.getElementById('modalCurrentVersion').textContent = 'v' + result.currentVersion;
        document.getElementById('modalLatestVersion').textContent = 'v' + result.latestVersion;
        document.getElementById('releaseNotesLink').href = result.releaseUrl;
        document.getElementById('versionCheckUpdateAvailable').style.display = 'block';
    } else if (result.status === 'up-to-date') {
        document.getElementById('modalCurrentVersionUpToDate').textContent = result.currentVersion === 'development' ? 'development' : 'v' + result.currentVersion;
        document.getElementById('versionCheckUpToDate').style.display = 'block';
    } else {
        document.getElementById('modalCurrentVersionError').textContent = result.currentVersion === 'development' ? 'development' : result.currentVersion;
        document.getElementById('versionCheckError').style.display = 'block';
    }
}

// --- Task Management ---
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

        function navigateToSection(section) {
            const link = nav.querySelector(`a[data-section="${section}"]`);
            if (link) {
                activateNav(link);
                showSection(section);
                window.location.hash = section;

                // Reload filter config when config section is shown
                if (section === 'config') {
                    initFilterConfig();
                }
            }
        }

        nav.addEventListener('click', function(e) {
            const link = e.target.closest('a[data-section]');
            if (link) {
                e.preventDefault();
                const section = link.getAttribute('data-section');
                navigateToSection(section);
            }
        });

        // Handle hash changes (back/forward navigation)
        window.addEventListener('hashchange', function() {
            const hash = window.location.hash.substring(1);
            if (hash && sections[hash]) {
                const link = nav.querySelector(`a[data-section="${hash}"]`);
                if (link) {
                    activateNav(link);
                    showSection(hash);
                    if (hash === 'config') {
                        initFilterConfig();
                    }
                }
            }
        });

        // Initialize from hash or default to first nav item
        const hash = window.location.hash.substring(1);
        if (hash && sections[hash]) {
            navigateToSection(hash);
        } else {
            const first = nav.querySelector('a[data-section]');
            if (first) {
                navigateToSection(first.getAttribute('data-section'));
            }
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

// --- Camera Control ---
window.showCameraControl = function() {
    const modal = new bootstrap.Modal(document.getElementById('cameraControlModal'));

    // Populate images directory link from config
    const imagesDirLink = document.getElementById('imagesDirLink');
    if (imagesDirLink && currentConfig.images_dir_path) {
        imagesDirLink.textContent = currentConfig.images_dir_path;
        imagesDirLink.href = `file://${currentConfig.images_dir_path}`;
    }

    // Clear previous capture result
    document.getElementById('captureResult').style.display = 'none';

    modal.show();
};

window.captureImage = async function() {
    const captureButton = document.getElementById('captureButton');
    const buttonText = document.getElementById('captureButtonText');
    const spinner = document.getElementById('captureButtonSpinner');
    const exposureDuration = parseFloat(document.getElementById('exposureDuration').value);

    // Validate exposure duration
    if (isNaN(exposureDuration) || exposureDuration <= 0) {
        createToast('Invalid exposure duration', 'danger', false);
        return;
    }

    // Show loading state
    captureButton.disabled = true;
    spinner.style.display = 'inline-block';
    buttonText.textContent = 'Capturing...';

    try {
        const response = await fetch('/api/camera/capture', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ duration: exposureDuration })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Show capture result
            document.getElementById('captureFilename').textContent = data.filename;
            document.getElementById('captureFormat').textContent = data.format || 'Unknown';
            document.getElementById('captureResult').style.display = 'block';

            createToast('Image captured successfully', 'success', true);
        } else {
            const errorMsg = data.error || 'Failed to capture image';
            createToast(errorMsg, 'danger', false);
        }
    } catch (error) {
        console.error('Capture error:', error);
        createToast('Failed to capture image: ' + error.message, 'danger', false);
    } finally {
        // Reset button state
        captureButton.disabled = false;
        spinner.style.display = 'none';
        buttonText.textContent = 'Capture';
    }
};

// --- Status Updates ---
function updateStatus(status) {
    document.getElementById('hardwareAdapter').textContent = status.hardware_adapter || '-';
    document.getElementById('telescopeConnected').innerHTML = status.telescope_connected
        ? '<span class="badge rounded-pill bg-success">Connected</span>'
        : '<span class="badge rounded-pill bg-danger">Disconnected</span>';
    // Update camera status with control button when connected
    const cameraEl = document.getElementById('cameraConnected');
    if (status.camera_connected) {
        cameraEl.innerHTML = `
            <span class="badge rounded-pill bg-success">Connected</span>
            <button class="btn btn-sm btn-outline-light" onclick="showCameraControl()">
                <i class="bi bi-camera"></i> Control
            </button>
        `;
    } else {
        cameraEl.innerHTML = '<span class="badge rounded-pill bg-danger">Disconnected</span>';
    }

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

    if (status.tasks_pending !== undefined) {
        document.getElementById('tasksPending').textContent = status.tasks_pending || '0';
    }

    if (status.telescope_ra !== null && status.telescope_dec !== null) {
        document.getElementById('telescopeCoords').textContent =
            status.telescope_ra.toFixed(3) + '° / ' + status.telescope_dec.toFixed(3) + '°';
    }

    // Update ground station information
    if (status.ground_station_name !== undefined || status.ground_station_url !== undefined) {
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

    // Update task processing state
    if (status.processing_active !== undefined) {
        updateProcessingState(status.processing_active);
    }

    // Update automated scheduling state
    if (status.automated_scheduling !== undefined) {
        updateAutomatedSchedulingState(status.automated_scheduling);
    }

    // Update autofocus status
    updateAutofocusStatus(status);

    // Update time sync status
    updateTimeSyncStatus(status);

    // Update missing dependencies display
    updateMissingDependencies(status.missing_dependencies || []);
}

function updateMissingDependencies(missingDeps) {
    const dashboardContainer = document.getElementById('missingDependenciesAlert');
    const configContainer = document.getElementById('configMissingDependenciesAlert');

    const containers = [dashboardContainer, configContainer].filter(c => c);

    if (missingDeps.length === 0) {
        containers.forEach(container => container.style.display = 'none');
        return;
    }

    let html = '<strong><i class="bi bi-exclamation-triangle-fill me-2"></i>Missing Dependencies:</strong><ul class="mb-0 mt-2">';
    missingDeps.forEach(dep => {
        html += `<li><strong>${dep.device_name}</strong>: Missing ${dep.missing_packages}<br>`;
        html += `<code class="small">${dep.install_cmd}</code></li>`;
    });
    html += '</ul>';

    containers.forEach(container => {
        container.innerHTML = html;
        container.style.display = 'block';
    });
}

function updateAutofocusStatus(status) {
    // Update autofocus button state
    const button = document.getElementById('runAutofocusButton');
    const buttonText = document.getElementById('autofocusButtonText');

    if (button && buttonText && status.autofocus_requested !== undefined) {
        if (status.autofocus_requested) {
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

    // Update last autofocus display
    const lastAutofocusDisplay = document.getElementById('lastAutofocusDisplay');
    if (lastAutofocusDisplay) {
        if (status.last_autofocus_timestamp) {
            const timestamp = status.last_autofocus_timestamp * 1000; // Convert to milliseconds
            const now = Date.now();
            const elapsed = now - timestamp;
            lastAutofocusDisplay.textContent = formatElapsedTime(elapsed);
        } else {
            lastAutofocusDisplay.textContent = 'Never';
        }
    }

    // Update next autofocus display
    const nextAutofocusDisplay = document.getElementById('nextAutofocusDisplay');
    const nextAutofocusTime = document.getElementById('nextAutofocusTime');

    if (nextAutofocusDisplay && nextAutofocusTime) {
        if (status.next_autofocus_minutes !== null && status.next_autofocus_minutes !== undefined) {
            nextAutofocusDisplay.style.display = 'block';
            if (status.next_autofocus_minutes === 0) {
                nextAutofocusTime.textContent = 'now (overdue)';
            } else {
                nextAutofocusTime.textContent = formatMinutes(status.next_autofocus_minutes);
            }
        } else {
            nextAutofocusDisplay.style.display = 'none';
        }
    }
}

function updateTimeSyncStatus(status) {
    const statusEl = document.getElementById('timeSyncStatus');
    const offsetEl = document.getElementById('timeOffsetDisplay');

    if (!statusEl || !offsetEl) {
        return;
    }

    const timeHealth = status.time_health;

    // Handle missing health data
    if (!timeHealth) {
        statusEl.innerHTML = '<span class="badge rounded-pill bg-secondary" data-bs-toggle="tooltip" title="Time sync status unknown">Unknown</span>';
        offsetEl.textContent = '-';
        return;
    }

    // Determine badge color based on status
    let badgeClass = 'bg-secondary';
    let badgeText = 'Unknown';
    let tooltipText = 'Time sync status unknown';

    switch (timeHealth.status) {
        case 'ok':
            badgeClass = 'bg-success';
            badgeText = 'OK';
            tooltipText = 'Time sync within threshold';
            break;
        case 'critical':
            badgeClass = 'bg-danger';
            badgeText = 'Paused';
            tooltipText = 'Time drift exceeded threshold - tasks paused';
            break;
        case 'unknown':
        default:
            badgeClass = 'bg-secondary';
            badgeText = 'Unknown';
            tooltipText = 'Unable to check time sync';
            break;
    }

    statusEl.innerHTML = `<span class="badge rounded-pill ${badgeClass}" data-bs-toggle="tooltip" title="${tooltipText}">${badgeText}</span>`;

    // Format offset display
    if (timeHealth.offset_ms !== null && timeHealth.offset_ms !== undefined) {
        const offset = timeHealth.offset_ms;
        const absOffset = Math.abs(offset);
        const sign = offset >= 0 ? '+' : '-';

        if (absOffset < 1) {
            offsetEl.textContent = `${sign}${absOffset.toFixed(2)}ms`;
        } else if (absOffset < 1000) {
            offsetEl.textContent = `${sign}${absOffset.toFixed(0)}ms`;
        } else {
            offsetEl.textContent = `${sign}${(absOffset / 1000).toFixed(2)}s`;
        }

        // Add source indicator
        if (timeHealth.source && timeHealth.source !== 'unknown') {
            offsetEl.textContent += ` (${timeHealth.source})`;
        }
    } else {
        offsetEl.textContent = '-';
    }

    // Reinitialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

function formatElapsedTime(milliseconds) {
    const seconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) {
        return `${days} day${days !== 1 ? 's' : ''} ago`;
    } else if (hours > 0) {
        return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
    } else if (minutes > 0) {
        return `${minutes} minute${minutes !== 1 ? 's' : ''} ago`;
    } else {
        return 'just now';
    }
}

function formatMinutes(minutes) {
    const hours = Math.floor(minutes / 60);
    const mins = Math.floor(minutes % 60);

    if (hours > 0) {
        if (mins > 0) {
            return `${hours}h ${mins}m`;
        }
        return `${hours}h`;
    }
    return `${mins}m`;
}

function updateProcessingState(isActive) {
    const statusEl = document.getElementById('processingStatus');
    const switchEl = document.getElementById('toggleProcessingSwitch');

    if (!statusEl || !switchEl) return;

    if (isActive) {
        statusEl.innerHTML = '<span class="badge rounded-pill bg-success">Enabled</span>';
        switchEl.checked = true;
    } else {
        statusEl.innerHTML = '<span class="badge rounded-pill bg-secondary">Disabled</span>';
        switchEl.checked = false;
    }
}

function updateAutomatedSchedulingState(isEnabled) {
    const statusEl = document.getElementById('automatedSchedulingStatus');
    const switchEl = document.getElementById('toggleAutomatedSchedulingSwitch');

    if (!statusEl || !switchEl) return;

    if (isEnabled) {
        statusEl.innerHTML = '<span class="badge rounded-pill bg-success">Enabled</span>';
        switchEl.checked = true;
    } else {
        statusEl.innerHTML = '<span class="badge rounded-pill bg-secondary">Disabled</span>';
        switchEl.checked = false;
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

    // Initialize filter configuration
    await initFilterConfig();

    // Setup autofocus button (only once)
    setupAutofocusButton();

    // Update app URL links from loaded config
    updateAppUrlLinks();

    // Fetch and display version
    fetchVersion();

    // Check for updates on load and every hour
    checkForUpdates();
    setInterval(checkForUpdates, 3600000); // Check every hour

    // Wire up version click to open modal
    const headerVersion = document.getElementById('headerVersion');
    if (headerVersion) {
        headerVersion.addEventListener('click', showVersionModal);
    }

    // Wire up update indicator badge click to open modal
    const updateIndicator = document.getElementById('updateIndicator');
    if (updateIndicator) {
        updateIndicator.addEventListener('click', showVersionModal);
    }

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

    // Initialize Bootstrap tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));

    // Add pause/resume switch handler
    const toggleSwitch = document.getElementById('toggleProcessingSwitch');
    if (toggleSwitch) {
        toggleSwitch.addEventListener('change', async (e) => {
            const isChecked = e.target.checked;
            const endpoint = isChecked ? '/api/tasks/resume' : '/api/tasks/pause';

            try {
                toggleSwitch.disabled = true;
                const response = await fetch(endpoint, { method: 'POST' });
                const result = await response.json();

                if (!response.ok) {
                    console.error('Failed to toggle processing:', result);
                    // Show specific error message (e.g., "Cannot resume during autofocus")
                    alert((result.error || 'Failed to toggle task processing') +
                          (response.status === 409 ? '' : ' - Unknown error'));
                    // Revert switch state on error
                    toggleSwitch.checked = !isChecked;
                }
                // State will be updated via WebSocket broadcast within 2 seconds
            } catch (error) {
                console.error('Error toggling processing:', error);
                alert('Error toggling task processing');
                // Revert switch state on error
                toggleSwitch.checked = !isChecked;
            } finally {
                toggleSwitch.disabled = false;
            }
        });
    }

    // Add automated scheduling switch handler
    const automatedSchedulingSwitch = document.getElementById('toggleAutomatedSchedulingSwitch');
    if (automatedSchedulingSwitch) {
        automatedSchedulingSwitch.addEventListener('change', async (e) => {
            const isChecked = e.target.checked;

            try {
                automatedSchedulingSwitch.disabled = true;
                const response = await fetch('/api/telescope/automated-scheduling', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: isChecked })
                });
                const result = await response.json();

                if (!response.ok) {
                    console.error('Failed to toggle automated scheduling:', result);
                    alert(result.error || 'Failed to toggle automated scheduling');
                    // Revert switch state on error
                    automatedSchedulingSwitch.checked = !isChecked;
                }
                // State will be updated via WebSocket broadcast
            } catch (error) {
                console.error('Error toggling automated scheduling:', error);
                alert('Error toggling automated scheduling');
                // Revert switch state on error
                automatedSchedulingSwitch.checked = !isChecked;
            } finally {
                automatedSchedulingSwitch.disabled = false;
            }
        });
    }
});
