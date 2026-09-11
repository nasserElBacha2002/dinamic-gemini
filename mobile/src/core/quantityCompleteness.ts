/**
 * Shared quantity completeness decision table.
 * Source of truth: contracts/offline-recognition/v1/quantity-completeness-matrix.json
 */

export type QuantityKind = 'ITEM' | 'POSITION';

export interface QuantityCompletenessInput {
  kind: QuantityKind | string;
  required: boolean;
  expected_presence?: string | null | undefined;
  missing_quantity_action?: string | null | undefined;
  allow_external_fallback?: boolean;
  required_fields?: ReadonlyArray<string> | null | undefined;
}

export interface QuantityCompletenessDecision {
  quantity_required_for_completion: boolean;
  fallback_policy: boolean;
}

export function decideQuantityCompleteness(
  input: QuantityCompletenessInput,
): QuantityCompletenessDecision {
  const kind = String(input.kind || '').trim().toUpperCase();
  if (kind === 'POSITION') {
    return { quantity_required_for_completion: false, fallback_policy: false };
  }

  const presence = String(input.expected_presence || '').trim().toUpperCase();
  const action = String(
    input.missing_quantity_action || 'PENDING_MANUAL_REVIEW',
  ).trim().toUpperCase();
  const requiredFields = new Set(
    (input.required_fields ?? []).map((field) => String(field).trim().toLowerCase()).filter(Boolean),
  );
  const explicitlyRequired =
    Boolean(input.required) || presence === 'ALWAYS' || requiredFields.has('quantity');
  const fallbackPolicy =
    Boolean(input.allow_external_fallback) || action === 'EXTERNAL_FALLBACK';

  if (action === 'RESOLVE_CODE_ONLY' && !explicitlyRequired) {
    return { quantity_required_for_completion: false, fallback_policy: false };
  }
  if (explicitlyRequired) {
    return { quantity_required_for_completion: true, fallback_policy: fallbackPolicy };
  }
  if (presence === 'OPTIONAL' && !input.required) {
    return {
      quantity_required_for_completion: fallbackPolicy,
      fallback_policy: fallbackPolicy,
    };
  }
  if (action === 'EXTERNAL_FALLBACK') {
    return { quantity_required_for_completion: true, fallback_policy: true };
  }
  if (action === 'PENDING_MANUAL_REVIEW' || action === 'UNRECOGNIZED') {
    return { quantity_required_for_completion: true, fallback_policy: fallbackPolicy };
  }
  return {
    quantity_required_for_completion: Boolean(input.allow_external_fallback),
    fallback_policy: fallbackPolicy,
  };
}

export function fallbackEligible(
  decision: QuantityCompletenessDecision,
  options: { identityComplete: boolean; quantityPresent: boolean },
): boolean {
  return (
    options.identityComplete &&
    !options.quantityPresent &&
    decision.quantity_required_for_completion &&
    decision.fallback_policy
  );
}
