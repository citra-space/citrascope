import { loadAdapterSchema, loadFilterConfig, buildAdapterFields } from '../config.js';
import { showToast } from '../toast.js';
import * as api from '../api.js';

export const configMethods = {
    async handleAdapterChange(adapter) {
        if (adapter) {
            const sensorCfg = this.config.sensors?.[this.configSensorIndex] || {};
            const currentSettings = sensorCfg.adapter_settings || {};
            await loadAdapterSchema(adapter, currentSettings);
            await loadFilterConfig();
        } else {
            this.adapterFields = [];
            this.filterConfigVisible = false;
        }
    },

    async reloadAdapterSchema() {
        const adapter = this.config.sensors?.[this.configSensorIndex]?.adapter;
        if (!adapter) return;

        const currentSettings = {};
        (this.adapterFields || []).forEach(field => {
            currentSettings[field.name] = field.value;
        });

        await loadAdapterSchema(adapter, currentSettings);
    },

    async scanHardware() {
        const adapter = this.config.sensors?.[this.configSensorIndex]?.adapter;
        if (!adapter) return;

        this.isScanning = true;
        try {
            const currentSettings = {};
            (this.adapterFields || []).forEach(field => {
                currentSettings[field.name] = field.value;
            });

            const result = await api.scanHardware(adapter, currentSettings);

            if (!result.ok) {
                showToast(result.error || 'Hardware scan failed', 'danger');
                return;
            }

            this.adapterFields = buildAdapterFields(result.data?.schema || [], currentSettings);
        } catch (error) {
            console.error('Hardware scan failed:', error);
            showToast('Hardware scan failed — check connection', 'danger');
        } finally {
            this.isScanning = false;
        }
    },
};
