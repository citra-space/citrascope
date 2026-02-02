/**
 * CitraScope Alpine store - must register BEFORE Alpine starts.
 * Load this script before Alpine.js so the alpine:init listener is attached in time.
 */
(() => {
    function stripAnsiCodes(text) {
        const esc = String.fromCharCode(27);
        return text.replace(new RegExp(esc + '\\[\\d+m', 'g'), '').replace(/\[\d+m/g, '');
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
        if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
        if (minutes > 0) return `${minutes}m ${seconds}s`;
        return `${seconds}s`;
    }

    function formatElapsedTime(milliseconds) {
        const seconds = Math.floor(milliseconds / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);
        if (days > 0) return `${days} day${days !== 1 ? 's' : ''} ago`;
        if (hours > 0) return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
        if (minutes > 0) return `${minutes} minute${minutes !== 1 ? 's' : ''} ago`;
        return 'just now';
    }

    function formatMinutes(minutes) {
        const hours = Math.floor(minutes / 60);
        const mins = Math.floor(minutes % 60);
        if (hours > 0) return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
        return `${mins}m`;
    }

    function formatLastAutofocus(status) {
        if (!status || !status.last_autofocus_timestamp) return 'Never';
        const elapsed = Date.now() - status.last_autofocus_timestamp * 1000;
        return formatElapsedTime(elapsed);
    }

    function formatTimeOffset(timeHealth) {
        if (!timeHealth || timeHealth.offset_ms == null) return '-';
        const o = timeHealth.offset_ms;
        const abs = Math.abs(o);
        const s = o >= 0 ? '+' : '-';
        let result;
        if (abs < 1) result = `${s}${abs.toFixed(2)}ms`;
        else if (abs < 1000) result = `${s}${abs.toFixed(0)}ms`;
        else result = `${s}${(abs / 1000).toFixed(2)}s`;
        if (timeHealth.source && timeHealth.source !== 'unknown') result += ` (${timeHealth.source})`;
        return result;
    }

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
            stripAnsiCodes,
            formatLocalTime,
            formatCountdown,
            formatElapsedTime,
            formatMinutes,
            formatTimeOffset,
            formatLastAutofocus,

            // Unified adapter fields (schema + values merged)
            adapterFields: []
        });
    });
})();
