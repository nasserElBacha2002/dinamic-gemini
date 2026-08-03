/**
 * Frontend feature flags for client-scoped positioning labels.
 * Backend remains authoritative; these only gate UI affordances.
 */

function parseEnvBool(value: unknown, defaultValue: boolean): boolean {
  if (value === undefined || value === null || value === '') return defaultValue;
  const normalized = String(value).trim().toLowerCase();
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on';
}

export interface PositionLabelUiCapabilities {
  labelsEnabled: boolean;
  renderEnabled: boolean;
  reconciliationEnabled: boolean;
}

export function getPositionLabelUiCapabilities(): PositionLabelUiCapabilities {
  const labelsFallback = import.meta.env.VITE_AISLE_LOCATION_LABELS_ENABLED;
  const renderFallback = import.meta.env.VITE_AISLE_LOCATION_LABEL_RENDER_ENABLED;
  return {
    labelsEnabled: parseEnvBool(
      import.meta.env.VITE_POSITION_LABELS_ENABLED ?? labelsFallback,
      true
    ),
    renderEnabled: parseEnvBool(
      import.meta.env.VITE_POSITION_LABEL_RENDER_ENABLED ?? renderFallback,
      true
    ),
    reconciliationEnabled: parseEnvBool(
      import.meta.env.VITE_POSITION_RECONCILIATION_ENABLED,
      true
    ),
  };
}
