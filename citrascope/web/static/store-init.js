/**
 * CitraScope Alpine store - must register BEFORE Alpine starts.
 * Load this script before Alpine.js so the alpine:init listener is attached in time.
 */
import * as formatters from './formatters.js';
import * as components from './components.js';
import { FILTER_COLORS } from './filters.js';

(() => {
    document.addEventListener('alpine:init', () => {
        // Register Alpine components FIRST (before Alpine starts processing the DOM)
        window.Alpine.data('adapterField', components.adapterField);
        window.Alpine.data('taskRow', components.taskRow);
        window.Alpine.data('filterRow', components.filterRow);
        window.Alpine.data('logEntry', components.logEntry);

        // Register store
        window.Alpine.store('citrascope', {
            status: {},
            tasks: [],
            logs: [],
            latestLog: null,
            wsConnected: false,
            wsReconnecting: false,
            currentTaskId: null,
            isTaskActive: false,
            nextTaskStartTime: null,
            countdown: '',
            config: {},
            apiEndpoint: 'production',
            hardwareAdapters: [], // [{value, label}]
            filters: {},
            savedAdapter: null,
            enabledFilters: [],
            filterConfigVisible: false,
            filterNamesEditable: false,
            filterNameOptions: [],
            filterColors: FILTER_COLORS,
            filterAdapterChangeMessageVisible: false,
            currentSection: 'monitoring',
            version: '',
            versionData: null,
            updateIndicator: '',
            versionCheckState: 'idle',
            versionCheckResult: null,

            // Autofocus target presets (loaded from API)
            autofocusPresets: [],

            // Loading states for async operations
            isSavingConfig: false,
            isReconnecting: false,
            isCapturing: false,
            isSaving: false,
            isAutofocusing: false,
            captureResult: null,
            // Focus loop state
            isLooping: false,
            previewDataUrl: null,
            loopCount: 0,
            previewExposure: 0.01,
            _lastTaskImageUrl: null,

            // Spread all formatter functions from shared module
            ...formatters,

            // Unified adapter fields (schema + values merged)
            adapterFields: [],

            // Computed property: Group adapter fields by their group property
            get groupedAdapterFields() {
                const grouped = {};
                this.adapterFields.forEach(f => {
                    const g = f.group || 'General';
                    if (!grouped[g]) grouped[g] = [];
                    grouped[g].push(f);
                });
                return Object.entries(grouped);
            },

            // Store methods
            previewFlipH: false,

            async captureImage() {
                const duration = this.previewExposure;
                if (Number.isNaN(duration) || duration <= 0) {
                    const { createToast } = await import('./config.js');
                    createToast('Invalid exposure duration', 'danger', false);
                    return;
                }

                this.isSaving = true;
                try {
                    const response = await fetch('/api/camera/capture', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ duration })
                    });
                    const data = await response.json();

                    if (response.ok && data.success) {
                        this.captureResult = data;
                        const { createToast } = await import('./config.js');
                        createToast('Image captured successfully', 'success', true);
                    } else {
                        const { createToast } = await import('./config.js');
                        createToast(data.error || 'Failed to capture image', 'danger', false);
                    }
                } catch (error) {
                    console.error('Capture error:', error);
                    const { createToast } = await import('./config.js');
                    createToast('Failed to capture image: ' + error.message, 'danger', false);
                } finally {
                    this.isSaving = false;
                }
            },

            async toggleProcessing(enabled) {
                const endpoint = enabled ? '/api/tasks/resume' : '/api/tasks/pause';
                try {
                    const response = await fetch(endpoint, { method: 'POST' });
                    const result = await response.json();
                    if (!response.ok) {
                        alert(result.error || 'Failed to toggle task processing');
                        // Revert on error
                        this.status.processing_active = !enabled;
                    }
                } catch (error) {
                    console.error('Error toggling processing:', error);
                    alert('Error toggling task processing');
                    this.status.processing_active = !enabled;
                }
            },

            async toggleAutomatedScheduling(enabled) {
                try {
                    const response = await fetch('/api/telescope/automated-scheduling', {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ enabled: enabled })
                    });
                    const result = await response.json();
                    if (!response.ok) {
                        alert(result.error || 'Failed to toggle automated scheduling');
                        // Revert on error
                        this.status.automated_scheduling = !enabled;
                    }
                } catch (error) {
                    console.error('Error toggling automated scheduling:', error);
                    alert('Error toggling automated scheduling');
                    this.status.automated_scheduling = !enabled;
                }
            },

            async reconnectHardware() {
                if (this.isReconnecting) return;
                this.isReconnecting = true;
                try {
                    const { reconnectHardware } = await import('./api.js');
                    const result = await reconnectHardware();
                    const { createToast } = await import('./config.js');
                    if (result.ok) {
                        createToast('Hardware reconnected successfully', 'success', true);
                    } else {
                        createToast(result.data?.error || 'Reconnect failed', 'danger', false);
                    }
                } catch (error) {
                    console.error('Reconnect error:', error);
                    const { createToast } = await import('./config.js');
                    createToast('Reconnect failed: ' + error.message, 'danger', false);
                } finally {
                    this.isReconnecting = false;
                }
            },

            get isImagingTaskActive() {
                return this.status?.processing_active === true;
            },

            async capturePreview() {
                if (this.isImagingTaskActive) {
                    this.isLooping = false;
                    return;
                }
                try {
                    const response = await fetch('/api/camera/preview', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ duration: this.previewExposure, flip_horizontal: this.previewFlipH })
                    });
                    if (response.status === 409) {
                        // Camera busy with previous capture — wait and retry
                        if (this.isLooping) {
                            setTimeout(() => this.capturePreview(), 250);
                        }
                        return;
                    }
                    const data = await response.json();
                    if (response.ok && data.image_data) {
                        this.previewDataUrl = data.image_data;
                        this.loopCount++;
                    } else {
                        const { createToast } = await import('./config.js');
                        createToast(data.error || 'Preview failed', 'danger', false);
                        this.isLooping = false;
                        return;
                    }
                } catch (error) {
                    console.error('Preview error:', error);
                    this.isLooping = false;
                    return;
                }

                if (this.isLooping) {
                    requestAnimationFrame(() => this.capturePreview());
                }
            },

            startFocusLoop() {
                if (this.isLooping || this.isImagingTaskActive) return;
                this.isLooping = true;
                this.loopCount = 0;
                this.capturePreview();
            },

            stopFocusLoop() {
                this.isLooping = false;
            },

            async singlePreview() {
                if (this.isLooping) return;
                this.isCapturing = true;
                try {
                    const response = await fetch('/api/camera/preview', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ duration: this.previewExposure, flip_horizontal: this.previewFlipH })
                    });
                    const data = await response.json();
                    if (response.ok && data.image_data) {
                        this.previewDataUrl = data.image_data;
                        this.loopCount++;
                    } else {
                        const { createToast } = await import('./config.js');
                        createToast(data.error || 'Preview failed', 'danger', false);
                    }
                } catch (error) {
                    const { createToast } = await import('./config.js');
                    createToast('Preview failed: ' + error.message, 'danger', false);
                } finally {
                    this.isCapturing = false;
                }
            },

            async showVersionModal() {
                this.versionCheckState = 'loading';
                this.versionCheckResult = null;

                const modal = new bootstrap.Modal(document.getElementById('versionModal'));
                modal.show();

                const result = await checkForUpdates();
                this.versionCheckResult = result;
                this.versionCheckState = result.status === 'update-available' ? 'update-available'
                    : result.status === 'error' ? 'error'
                    : 'up-to-date';
            },

            showConfigSection() {
                // Close setup wizard modal
                const wizardModal = bootstrap.Modal.getInstance(document.getElementById('setupWizard'));
                if (wizardModal) {
                    wizardModal.hide();
                }

                // Navigate to config section
                this.currentSection = 'config';
                window.location.hash = 'config';
            }
        });
    });
})();
