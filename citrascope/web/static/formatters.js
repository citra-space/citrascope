/**
 * CitraScope Formatter Utilities
 *
 * Shared formatting functions for the dashboard UI.
 * These functions are exposed in the Alpine.js store for use in templates.
 */

/**
 * Strip ANSI color codes from text
 * @param {string} text - Text containing ANSI codes
 * @returns {string} Text with ANSI codes removed
 */
export function stripAnsiCodes(text) {
    const esc = String.fromCharCode(27);
    return text.replace(new RegExp(esc + '\\[\\d+m', 'g'), '').replace(/\[\d+m/g, '');
}

/**
 * Format ISO date string to local time
 * @param {string} isoString - ISO 8601 date string
 * @returns {string} Formatted local time string
 */
export function formatLocalTime(isoString) {
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

/**
 * Format milliseconds as countdown string
 * @param {number} milliseconds - Time in milliseconds
 * @returns {string} Formatted countdown string (e.g., "2h 30m 15s")
 */
export function formatCountdown(milliseconds) {
    const totalSeconds = Math.floor(milliseconds / 1000);
    if (totalSeconds < 0) return 'Starting soon...';
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
    if (minutes > 0) return `${minutes}m ${seconds}s`;
    return `${seconds}s`;
}

/**
 * Format elapsed time for "X ago" display
 * @param {number} milliseconds - Elapsed time in milliseconds
 * @returns {string} Human-readable elapsed time (e.g., "2 hours ago")
 */
export function formatElapsedTime(milliseconds) {
    const seconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    if (days > 0) return `${days} day${days !== 1 ? 's' : ''} ago`;
    if (hours > 0) return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
    if (minutes > 0) return `${minutes} minute${minutes !== 1 ? 's' : ''} ago`;
    return 'just now';
}

/**
 * Format minutes as "Xh Ym" display
 * @param {number} minutes - Time in minutes
 * @returns {string} Formatted time string (e.g., "2h 30m")
 */
export function formatMinutes(minutes) {
    const hours = Math.floor(minutes / 60);
    const mins = Math.floor(minutes % 60);
    if (hours > 0) return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
    return `${mins}m`;
}

/**
 * Format last autofocus timestamp
 * @param {Object} status - Status object containing last_autofocus_timestamp
 * @returns {string} Formatted autofocus time or "Never"
 */
export function formatLastAutofocus(status) {
    if (!status || !status.last_autofocus_timestamp) return 'Never';
    const elapsed = Date.now() - status.last_autofocus_timestamp * 1000;
    return formatElapsedTime(elapsed);
}

/**
 * Format time offset with source information
 * @param {Object} timeHealth - Time health object with offset_ms and source
 * @returns {string} Formatted time offset (e.g., "+50ms (ntp)")
 */
export function formatTimeOffset(timeHealth) {
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
