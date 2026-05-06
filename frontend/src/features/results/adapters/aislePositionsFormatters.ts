import type { TFunction } from 'i18next';
import type { MergeResultsSummary } from './aislePositionsViewModel';

export function mergeConsolidatedDetail(t: TFunction, summary: MergeResultsSummary): string {
  const examples =
    summary.skuExamples.length > 0
      ? t('positions.merge_examples_paren', { list: summary.skuExamples.join(', ') })
      : '';
  if (summary.groupCount === 1) {
    return t('positions.merge_repeated_sku_one', { examples });
  }
  return t('positions.merge_repeated_sku_other', { count: summary.groupCount, examples });
}
