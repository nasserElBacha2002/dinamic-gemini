# Preliminary reconciliation — Phase 5 metrics report

## Measured in this implementation cycle

No production or labeled-dataset agreement rates were measured (flags default off; no device E2E).

## Metrics implemented (computed from persisted reconciliations)

| Metric | Notes |
|--------|-------|
| `comparability_rate` | comparable / total |
| `server_agreement_rate` | code-match family / comparable |
| `code_match_rate` | same |
| `quantity_match_rate` | qty-match / code-match |
| `local_false_positive_rate_proxy` | LOCAL_ONLY / comparable |
| `local_false_negative_rate_proxy` | REMOTE_ONLY / comparable |
| `ambiguous_rate` | ambiguous outcomes / comparable |

These are **server-agreement proxies**, not human ground-truth accuracy.

## Numerators / denominators

Persisted on list response: `numerator_agreement`, `denominator_comparable`.  
`NOT_COMPARABLE` excluded from agreement denominators.
