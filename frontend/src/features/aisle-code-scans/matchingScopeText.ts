import type { TFunction } from 'i18next';

export function codeScanMatchingScopeHelperText(
  t: TFunction,
  metadata: Record<string, unknown> | null | undefined,
): string | null {
  const matching = metadata?.matching;
  if (!matching || typeof matching !== 'object') {
    return null;
  }
  const block = matching as Record<string, unknown>;
  const status = block.status;
  if (status === 'skipped') {
    return t('aisleCodeScans.matching.scopeSkipped');
  }
  if (status === 'failed') {
    return t('aisleCodeScans.matching.scopeFailed');
  }
  if (status !== 'completed') {
    return null;
  }
  const scope = block.scope;
  if (scope === 'job' && block.job_id) {
    return t('aisleCodeScans.matching.scopeJob');
  }
  if (scope === 'legacy') {
    return t('aisleCodeScans.matching.scopeLegacy');
  }
  return t('aisleCodeScans.matching.scopeCurrent');
}
