/**
 * Frontend feature flags for physical locations / positioning labels.
 * Backend remains authoritative; these only gate UI affordances.
 */

function parseEnvBool(value: unknown, defaultValue: boolean): boolean {
  if (value === undefined || value === null || value === '') return defaultValue;
  const normalized = String(value).trim().toLowerCase();
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on';
}

export interface AisleLocationUiCapabilities {
  domainEnabled: boolean;
  labelsEnabled: boolean;
  renderEnabled: boolean;
  batchEnabled: boolean;
}

export function getAisleLocationUiCapabilities(): AisleLocationUiCapabilities {
  return {
    domainEnabled: parseEnvBool(import.meta.env.VITE_AISLE_LOCATION_DOMAIN_ENABLED, true),
    labelsEnabled: parseEnvBool(import.meta.env.VITE_AISLE_LOCATION_LABELS_ENABLED, true),
    renderEnabled: parseEnvBool(import.meta.env.VITE_AISLE_LOCATION_LABEL_RENDER_ENABLED, true),
    batchEnabled: parseEnvBool(import.meta.env.VITE_POSITION_LABEL_BATCH_ENABLED, true),
  };
}
