/**
 * Analysis tab — fetches pipeline metrics and renders the task table / stats.
 */

const PROCESSOR_COLORS = {
    calibration_s:        '#00b894',
    plate_solve_s:        '#fdcb6e',
    source_extractor_s:   '#e17055',
    photometry_s:         '#74b9ff',
    satellite_matcher_s:  '#a29bfe',
    annotated_image_s:    '#636e72',
};

const PROCESSOR_LABELS = {
    calibration_s:        'Cal',
    plate_solve_s:        'Solve',
    source_extractor_s:   'SExtract',
    photometry_s:         'Phot',
    satellite_matcher_s:  'Match',
    annotated_image_s:    'Annotate',
};

document.addEventListener('alpine:init', () => {
    Alpine.data('analysisTab', () => ({
        stats: {},
        tasks: [],
        total: 0,
        offset: 0,
        pageSize: 50,
        sortCol: 'completed_at',
        sortOrder: 'desc',
        filterTarget: '',
        filterSolved: '',
        filterMatched: '',
        filterWindow: '',
        loading: false,
        loaded: false,
        expanded: null,
        detail: null,

        async loadAll() {
            this.loading = true;
            await Promise.all([this.loadStats(), this.loadTasks()]);
            this.loaded = true;
            this.loading = false;
        },

        async loadStats() {
            try {
                const resp = await fetch('/api/analysis/stats?hours=24');
                this.stats = await resp.json();
            } catch (e) {
                console.error('Failed to load analysis stats', e);
            }
        },

        async loadTasks() {
            try {
                const params = new URLSearchParams({
                    limit: this.pageSize,
                    offset: this.offset,
                    sort: this.sortCol,
                    order: this.sortOrder,
                });
                if (this.filterTarget) params.set('target_name', this.filterTarget);
                if (this.filterSolved) params.set('plate_solved', this.filterSolved);
                if (this.filterMatched) params.set('target_matched', this.filterMatched);
                if (this.filterWindow) params.set('missed_window', this.filterWindow);

                const resp = await fetch('/api/analysis/tasks?' + params.toString());
                const data = await resp.json();
                this.tasks = data.tasks || [];
                this.total = data.total || 0;
            } catch (e) {
                console.error('Failed to load analysis tasks', e);
            }
        },

        toggleSort(col) {
            if (this.sortCol === col) {
                this.sortOrder = this.sortOrder === 'desc' ? 'asc' : 'desc';
            } else {
                this.sortCol = col;
                this.sortOrder = 'desc';
            }
            this.offset = 0;
            this.loadTasks();
        },

        sortIcon(col) {
            if (this.sortCol !== col) return '';
            return this.sortOrder === 'desc' ? '▾' : '▴';
        },

        async toggleDetail(taskId) {
            if (this.expanded === taskId) {
                this.expanded = null;
                this.detail = null;
                return;
            }
            try {
                const resp = await fetch('/api/analysis/tasks/' + taskId);
                this.detail = await resp.json();
                this.expanded = taskId;
            } catch (e) {
                console.error('Failed to load task detail', e);
            }
        },

        formatTime(iso) {
            if (!iso) return '—';
            try {
                const d = new Date(iso);
                return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                    + ' ' + d.toLocaleDateString([], { month: 'short', day: 'numeric' });
            } catch { return iso; }
        },

        pointingClass(arcsec) {
            if (arcsec == null) return 'text-muted';
            if (arcsec < 30) return 'text-success';
            if (arcsec < 120) return 'text-warning';
            return 'text-danger';
        },

        // Mini duration bar (slew / queue / proc) — proportional widths
        _durationTotal(task) {
            return (task.total_slew_time_s || 0) + (task.processing_queue_wait_s || 0) + (task.total_processing_time_s || 0);
        },
        durationPct(task, segment) {
            const tot = this._durationTotal(task);
            if (tot <= 0) return 0;
            const vals = {
                slew: task.total_slew_time_s || 0,
                queue: task.processing_queue_wait_s || 0,
                proc: task.total_processing_time_s || 0,
            };
            return Math.round((vals[segment] / tot) * 100);
        },
        durationTitle(task) {
            const parts = [];
            if (task.total_slew_time_s) parts.push('Slew: ' + task.total_slew_time_s.toFixed(1) + 's');
            if (task.processing_queue_wait_s) parts.push('Queue: ' + task.processing_queue_wait_s.toFixed(1) + 's');
            if (task.total_processing_time_s) parts.push('Processing: ' + task.total_processing_time_s.toFixed(1) + 's');
            return parts.join(' | ') || 'No timing data';
        },

        // Processor segments for the summary bar
        get processorSegments() {
            const pp = this.stats.per_processor_timing;
            if (!pp) return [];
            const keys = Object.keys(PROCESSOR_COLORS);
            const vals = keys.map(k => pp[k] || 0);
            const total = vals.reduce((a, b) => a + b, 0);
            if (total <= 0) return [];
            return keys.map((k, i) => ({
                name: PROCESSOR_LABELS[k],
                val: vals[i].toFixed(2),
                pct: Math.round((vals[i] / total) * 100),
                color: PROCESSOR_COLORS[k],
            }));
        },

        // Detail timing bar — uses actual values as proportional widths
        detailTimingPct(detail, field) {
            if (!detail) return 0;
            const fields = [
                'total_slew_time_s', 'processing_queue_wait_s',
                'calibration_time_s', 'plate_solve_time_s', 'source_extractor_time_s',
                'photometry_time_s', 'matcher_time_s', 'annotated_image_time_s'
            ];
            const total = fields.reduce((s, f) => s + (detail[f] || 0), 0);
            if (total <= 0) return 0;
            return Math.round(((detail[field] || 0) / total) * 100);
        },

        // Window timeline proportional positioning
        windowPct(detail, part) {
            if (!detail.window_start || !detail.window_stop || !detail.imaging_started_at) return 0;
            try {
                const ws = new Date(detail.window_start).getTime();
                const we = new Date(detail.window_stop).getTime();
                const is = new Date(detail.imaging_started_at).getTime();
                const ie = detail.imaging_finished_at ? new Date(detail.imaging_finished_at).getTime() : is;
                const span = we - ws;
                if (span <= 0) return 0;
                if (part === 'start') return Math.max(0, Math.min(100, ((is - ws) / span) * 100));
                if (part === 'width') return Math.max(1, Math.min(100, ((ie - is) / span) * 100));
            } catch { return 0; }
            return 0;
        },
    }));
});

window.loadAnalysisData = function () {
    const el = document.querySelector('#analysisSection');
    if (el && el.__x) {
        el.__x.$data.loadAll();
    }
};
