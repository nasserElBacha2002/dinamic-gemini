/**
 * Phase 10 — mobile/backend payload compatibility gates (client-side).
 * Reject incompatible builds with a clear Spanish message (no silent degrade).
 */

export interface CompatibilityRequirement {
  readonly minimumMobileVersionCode: number;
  readonly minimumBackendApiMajor: number;
  readonly supportedPayloadVersions: readonly number[];
}

export const DEFAULT_COMPATIBILITY: CompatibilityRequirement = {
  minimumMobileVersionCode: 1,
  minimumBackendApiMajor: 3,
  supportedPayloadVersions: [1],
};

export type CompatibilityCheckResult =
  | { readonly ok: true }
  | { readonly ok: false; readonly message: string };

export function checkMobileVersionCompatibility(
  versionCode: number,
  requirement: CompatibilityRequirement = DEFAULT_COMPATIBILITY,
): CompatibilityCheckResult {
  if (versionCode < requirement.minimumMobileVersionCode) {
    return {
      ok: false,
      message: `Versión de app no soportada (code ${versionCode}). Mínimo requerido: ${requirement.minimumMobileVersionCode}. Actualizá la aplicación.`,
    };
  }
  return { ok: true };
}

export function checkPayloadVersionCompatibility(
  payloadVersion: number,
  requirement: CompatibilityRequirement = DEFAULT_COMPATIBILITY,
): CompatibilityCheckResult {
  if (!requirement.supportedPayloadVersions.includes(payloadVersion)) {
    return {
      ok: false,
      message: `Versión de payload ${payloadVersion} no compatible. Soportadas: ${requirement.supportedPayloadVersions.join(', ')}.`,
    };
  }
  return { ok: true };
}
