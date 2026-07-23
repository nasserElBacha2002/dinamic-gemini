import { redact as loggingRedact } from '../core/logging';
import type { ObservabilityAttributeValue, ObservabilityEvent } from './types';

const FORBIDDEN_ATTR_KEYS = new Set([
  'uri',
  'path',
  'filepath',
  'file_path',
  'local_uri',
  'transform_uri',
  'display_name',
  'filename',
  'file_name',
  'internal_code',
  'quantity',
  'label',
  'ocr',
  'payload',
  'ssid',
  'bssid',
  'ip',
  'mac',
  'operator',
  'carrier',
  'latitude',
  'longitude',
  'location',
  'authorization',
  'token',
  'access_token',
  'refresh_token',
]);

/**
 * Strip sensitive keys from observability attributes.
 * Reuses logging redaction for nested values / bearer patterns.
 */
export function sanitizeObservabilityAttributes(
  attrs: Readonly<Record<string, ObservabilityAttributeValue>> | undefined,
): Record<string, ObservabilityAttributeValue> {
  if (!attrs) {
    return {};
  }
  const out: Record<string, ObservabilityAttributeValue> = {};
  for (const [key, value] of Object.entries(attrs)) {
    const k = key.toLowerCase();
    if (FORBIDDEN_ATTR_KEYS.has(k) || k.includes('token') || k.includes('password')) {
      continue;
    }
    if (typeof value === 'string') {
      const redacted = loggingRedact({ [key]: value })[key];
      out[key] =
        typeof redacted === 'string' ||
        typeof redacted === 'number' ||
        typeof redacted === 'boolean' ||
        redacted === null
          ? (redacted as ObservabilityAttributeValue)
          : String(redacted);
    } else {
      out[key] = value;
    }
  }
  return out;
}

export function sanitizeObservabilityEvent(event: ObservabilityEvent): ObservabilityEvent {
  return {
    ...event,
    attributes: sanitizeObservabilityAttributes(event.attributes),
  };
}
