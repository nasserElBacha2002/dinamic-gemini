/**
 * Phase 9 corrections — typed domain outcomes for offline executors.
 * Success is never inferred from "no throw".
 */

export type DomainOperationOutcome =
  | { readonly status: 'completed'; readonly remoteId?: string }
  | { readonly status: 'retryable'; readonly code: string; readonly message: string }
  | { readonly status: 'auth'; readonly code: string; readonly message?: string }
  | {
      readonly status: 'conflict';
      readonly code: string;
      readonly message?: string;
      readonly details?: unknown;
    }
  | { readonly status: 'terminal'; readonly code: string; readonly message: string }
  | { readonly status: 'pending'; readonly code?: string; readonly message?: string }
  | { readonly status: 'dependency'; readonly code: string; readonly message: string };

export function mapDomainOutcomeToExecutor(
  outcome: DomainOperationOutcome,
):
  | { readonly outcome: 'completed' }
  | {
      readonly outcome: 'retryable' | 'terminal' | 'conflict' | 'auth' | 'dependency';
      readonly code: string;
      readonly message: string;
    } {
  switch (outcome.status) {
    case 'completed':
      return { outcome: 'completed' };
    case 'pending':
      return {
        outcome: 'retryable',
        code: outcome.code ?? 'PENDING',
        message: outcome.message ?? 'Target still pending',
      };
    case 'retryable':
      return { outcome: 'retryable', code: outcome.code, message: outcome.message };
    case 'auth':
      return {
        outcome: 'auth',
        code: outcome.code,
        message: outcome.message ?? outcome.code,
      };
    case 'conflict':
      return {
        outcome: 'conflict',
        code: outcome.code,
        message: outcome.message ?? outcome.code,
      };
    case 'terminal':
      return { outcome: 'terminal', code: outcome.code, message: outcome.message };
    case 'dependency':
      return { outcome: 'dependency', code: outcome.code, message: outcome.message };
    default: {
      const _exhaustive: never = outcome;
      return {
        outcome: 'terminal',
        code: 'UNKNOWN_OUTCOME',
        message: String(_exhaustive),
      };
    }
  }
}
