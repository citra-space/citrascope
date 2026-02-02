/**
 * CitraScope Alpine store - must register BEFORE Alpine starts.
 * Load this script before Alpine.js so the alpine:init listener is attached in time.
 */
import * as formatters from './formatters.js';

(() => {
    document.addEventListener('alpine:init', () => {
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
            filterAdapterChangeMessageVisible: false,
            currentSection: 'monitoring',
            version: '',
            updateIndicator: '',
            versionCheckState: 'idle',
            versionCheckResult: null,

            // Spread all formatter functions from shared module
            ...formatters,

            // Unified adapter fields (schema + values merged)
            adapterFields: []
        });
    });
})();
