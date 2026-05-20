import type { TFunction } from 'i18next';

export function formatCodeScanCodeType(t: TFunction, codeType: string): string {
  const key = `aisleCodeScans.codeTypes.${codeType}`;
  const translated = t(key);
  return translated === key ? t('aisleCodeScans.codeTypes.unknown') : translated;
}

export function formatCodeScanRunStatus(t: TFunction, status: string): string {
  const key = `aisleCodeScans.runStatuses.${status}`;
  const translated = t(key);
  return translated === key ? status : translated;
}

export function formatCodeScanDetectionStatus(t: TFunction, status: string): string {
  const key = `aisleCodeScans.detectionStatuses.${status}`;
  const translated = t(key);
  return translated === key ? status : translated;
}

export function formatCodeScanMatchStatus(
  t: TFunction,
  status: string | null | undefined,
): string {
  if (!status) return t('aisleCodeScans.matching.not_evaluated');
  if (status === 'mixed') {
    return t('aisleCodeScans.matching.mixed');
  }
  const key = `aisleCodeScans.matching.${status}`;
  const translated = t(key);
  return translated === key ? status : translated;
}

export function formatCodeScanMatchType(t: TFunction, matchType: string | null | undefined): string {
  if (!matchType) return '—';
  const key = `aisleCodeScans.matching.${matchType}`;
  const translated = t(key);
  return translated === key ? matchType : translated;
}
