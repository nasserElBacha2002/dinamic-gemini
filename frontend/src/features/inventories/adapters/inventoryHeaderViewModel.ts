/**
 * Header presentation for inventory detail — avoids scattering DTO field reads in page JSX.
 */

import type { TFunction } from 'i18next';
import type { Inventory } from '../../../api/types';
import type { StatusBadgeSemantic } from '../../../components/ui/StatusBadge';
import { formatDate } from '../../../utils/formatDate';
import { formatInventoryStatusLabel, inventoryStatusToBadgeSemantic } from '../../../utils/inventoryRowStatus';

export interface InventoryHeaderViewModel {
  title: string;
  statusLabel: string;
  statusSemantic: StatusBadgeSemantic;
  processingModeLabel: string;
  processingModeSemantic: StatusBadgeSemantic;
  primaryConfigCaption: string | null;
  createdDateCaption: string;
}

export function toInventoryHeaderViewModel(
  inventory: Inventory,
  t: TFunction
): InventoryHeaderViewModel {
  const primaryConfigCaption = inventory.primary_execution_config
    ? t('inventory.primary_config_summary', {
        provider: inventory.primary_execution_config.provider_name,
        model: inventory.primary_execution_config.model_name,
        prompt: inventory.primary_execution_config.prompt_key,
      })
    : null;

  return {
    title: inventory.name,
    statusLabel: formatInventoryStatusLabel(String(inventory.status)),
    statusSemantic: inventoryStatusToBadgeSemantic(String(inventory.status)),
    processingModeLabel:
      inventory.processing_mode === 'test'
        ? t('inventory.processing_mode_test')
        : t('inventory.processing_mode_production'),
    processingModeSemantic: inventory.processing_mode === 'test' ? 'warning' : 'neutral',
    primaryConfigCaption: primaryConfigCaption
      ? `${t('inventory.primary_config_title')}: ${primaryConfigCaption}`
      : null,
    createdDateCaption: t('inventory.created_date_label', {
      date: formatDate(inventory.created_at ?? undefined),
    }),
  };
}
