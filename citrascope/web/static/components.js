/**
 * Alpine.js Component Definitions for CitraScope Dashboard
 *
 * Reusable component functions for common UI patterns.
 * These components reduce template complexity and improve maintainability.
 */

/**
 * Adapter field component - handles rendering different field types
 * (boolean, select, number, text) with appropriate validation and styling
 * @param {Object} field - The field object from adapterFields
 */
export function adapterField(field) {
    return {
        field: field,

        get inputId() {
            if (!this.field || !this.field.name) return '';
            return 'adapter_' + this.field.name;
        },

        get isBoolean() {
            if (!this.field) return false;
            return this.field.type === 'bool';
        },

        get isSelect() {
            if (!this.field) return false;
            return this.field.type !== 'bool' &&
                   this.field.options &&
                   Array.isArray(this.field.options) &&
                   this.field.options.length > 0;
        },

        get isNumber() {
            if (!this.field) return false;
            return this.field.type !== 'bool' &&
                   (!this.field.options || this.field.options.length === 0) &&
                   (this.field.type === 'int' || this.field.type === 'float');
        },

        get isText() {
            return !this.isBoolean && !this.isSelect && !this.isNumber;
        },

        get isVisible() {
            if (!this.field || !this.field.visible_when) return true;
            const cond = this.field.visible_when;
            const sibling = (this.$store.citrascope.adapterFields || [])
                .find(f => f.name === cond.field);
            return sibling ? String(sibling.value) === String(cond.value) : true;
        },

        handleChange(event) {
            if (!this.field) return;

            if (this.field.type === 'int') {
                this.field.value = parseInt(event.target.value, 10);
            } else if (this.field.type === 'float') {
                this.field.value = parseFloat(event.target.value);
            } else {
                this.field.value = event.target.value;
            }

            // Reload schema if device type changed
            if (this.field.name && ['camera_type', 'mount_type', 'filter_wheel_type', 'focuser_type'].includes(this.field.name)) {
                this.$store.citrascope.reloadAdapterSchema?.();
            }
        }
    };
}

/**
 * Task row component - displays a single task in the queue table
 * with active/inactive status styling
 * @param {Object} task - The task object
 */
export function taskRow(task) {
    return {
        task: task,

        get isActive() {
            if (!this.task || !this.task.id) return false;
            return this.task.id === this.$store.citrascope.currentTaskId;
        },

        get statusBadgeClass() {
            return this.isActive ? 'bg-success' : 'bg-info';
        },

        get statusText() {
            if (!this.task) return '';
            return this.isActive ? 'Active' : (this.task.status || '');
        },

        get rowClass() {
            return this.isActive ? 'table-active' : '';
        },

        // ── Live phase / countdown ────────────────────────────────────────
        //
        // All three getters below read `$store.citrascope.now`, which is
        // bumped once per second by the heartbeat in app.js — that's what
        // makes them tick without each row owning its own setInterval.
        //
        // `phase` collapses the {start, stop, now} state machine into a
        // single label that drives both the countdown text and the cell
        // color so the two can never disagree.

        get _phaseTimes() {
            const t = this.task || {};
            const now = this.$store?.citrascope?.now ?? Date.now();
            const start = t.start_time ? new Date(t.start_time).getTime() : null;
            const stop  = t.stop_time  ? new Date(t.stop_time).getTime()  : null;
            return { now, start, stop };
        },

        get phase() {
            const { now, start, stop } = this._phaseTimes;
            if (start == null) return 'unknown';
            // 30s grace after window close so a task that overran but is still
            // wrapping up doesn't immediately flip to "done" while the daemon
            // is still finalizing it.
            if (stop != null && now > stop + 30_000) return 'done';
            if (stop != null && now > stop)          return 'overdue';
            if (now >= start)                        return 'running';
            if (start - now <= 10_000)               return 'imminent';
            return 'upcoming';
        },

        get countdownText() {
            const { now, start, stop } = this._phaseTimes;
            if (start == null) return '—';
            switch (this.phase) {
                case 'done':     return 'done';
                case 'overdue':  return Math.round((now - stop) / 1000) + 's overdue';
                case 'running':  return stop != null
                    ? Math.max(0, Math.round((stop - now) / 1000)) + 's left'
                    : 'now';
                case 'imminent': return 'in ' + Math.max(0, Math.round((start - now) / 1000)) + 's';
                case 'upcoming': {
                    const secs = Math.round((start - now) / 1000);
                    if (secs < 60)    return 'in ' + secs + 's';
                    if (secs < 3600)  return 'in ' + Math.round(secs / 60) + 'm';
                    return 'in ' + Math.round(secs / 3600) + 'h';
                }
                default: return '—';
            }
        },

        get phaseClass() {
            switch (this.phase) {
                case 'running':  return 'text-success fw-semibold';
                case 'imminent': return 'text-warning fw-semibold';
                case 'overdue':  return 'text-danger fw-semibold';
                case 'done':     return 'text-muted';
                default:         return 'text-secondary';
            }
        }
    };
}

/**
 * Filter row component - displays a single filter configuration row
 * with colored badge styling
 * @param {Object} filter - The filter object
 * @param {string} filterId - The filter ID
 */
export function filterRow(filter, filterId) {
    return {
        filter: filter,
        filterId: filterId,

        get badgeStyle() {
            if (!this.filter || !this.filter.color) return 'background-color: gray; color: white;';
            return `background-color: ${this.filter.color}; color: white;`;
        }
    };
}

/**
 * Log entry component - displays a single log message
 * with formatted timestamp and stripped ANSI codes
 * @param {Object} log - The log entry object
 */
export function logEntry(log) {
    return {
        log: log,

        get timestamp() {
            if (!this.log || !this.log.timestamp) return '';
            return new Date(this.log.timestamp).toLocaleTimeString();
        },

        get levelClass() {
            if (!this.log || !this.log.level) return '';
            return 'log-level-' + this.log.level;
        },

        get strippedMessage() {
            if (!this.log || !this.log.message) return '';
            return this.$store.citrascope.stripAnsiCodes(this.log.message);
        }
    };
}
