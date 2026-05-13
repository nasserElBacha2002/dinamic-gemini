/**
 * Read-only panel: GET …/jobs/{jobId}/auditability (Phase H). Spanish copy via i18n only.
 */

import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Box, Chip, CircularProgress, Paper, Stack, Typography } from '@mui/material';
import type { RunAuditabilityView, RunAuditMetadataSources, LlmCostSnapshot } from '../api/types';
import { useJobAuditability } from '../hooks';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import {
  formatAuditCostFromApiString,
  formatAuditTokenCount,
  normalizeCurrency,
} from '../utils/formatLlmAuditCost';
import { ErrorAlert } from './ui';

export interface JobAuditabilityPanelProps {
  inventoryId: string;
  aisleId: string;
  jobId: string;
  /** When the parent workspace is not active, skip fetching. */
  active?: boolean;
  /** When set, skips network request (e.g. unit tests). */
  auditability?: RunAuditabilityView;
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'minmax(140px, 200px) 1fr' }, gap: 0.75 }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" sx={{ wordBreak: 'break-word' }} component="div">
        {children}
      </Typography>
    </Box>
  );
}

function boolTriLabel(value: boolean | null | undefined, t: (k: string) => string): string {
  if (value === true) return t('observability.auditability.yes');
  if (value === false) return t('observability.auditability.no');
  return t('observability.auditability.unknown');
}

function formatScalar(value: string | number | null | undefined, emptyLabel: string): string {
  if (value === null || value === undefined) return emptyLabel;
  const s = String(value).trim();
  return s === '' ? emptyLabel : s;
}

function captureStatusLabel(
  status: string | null | undefined,
  t: (key: string, options?: { defaultValue?: string }) => string
): string {
  const s = (status ?? '').trim().toLowerCase();
  if (s === 'exact') return t('observability.auditability.cost.status_exact');
  if (s === 'estimated') return t('observability.auditability.cost.status_estimated');
  if (s === 'unavailable') return t('observability.auditability.cost.status_unavailable');
  return formatScalar(status, t('observability.auditability.unknown'));
}

function JobAuditabilityCostCard({
  snap,
  notReported,
  t,
}: {
  snap: LlmCostSnapshot;
  notReported: string;
  t: (key: string, options?: { defaultValue?: string }) => string;
}) {
  const usage = snap.usage ?? {};
  const computed = snap.computed_cost ?? {};
  const pricingSnap = snap.pricing_snapshot ?? {};
  const currency = normalizeCurrency(
    computed.currency ?? pricingSnap.billing_currency ?? snap.billing_currency ?? 'USD'
  );

  const inputTok = usage.input_tokens ?? null;
  const outputTok = usage.output_tokens ?? null;
  const totalTok = usage.total_tokens ?? null;

  const pricingSource =
    typeof pricingSnap.pricing_source === 'string' ? pricingSnap.pricing_source.trim() : '';

  return (
    <Stack spacing={1}>
      <DetailRow label={t('observability.auditability.cost.provider')}>
        {formatScalar(snap.provider, notReported)}
      </DetailRow>
      <DetailRow label={t('observability.auditability.cost.model')}>{formatScalar(snap.model, notReported)}</DetailRow>
      <DetailRow label={t('observability.auditability.cost.inputTokens')}>
        {formatAuditTokenCount(inputTok, notReported)}
      </DetailRow>
      <DetailRow label={t('observability.auditability.cost.outputTokens')}>
        {formatAuditTokenCount(outputTok, notReported)}
      </DetailRow>
      <DetailRow label={t('observability.auditability.cost.totalTokens')}>
        {formatAuditTokenCount(totalTok, notReported)}
      </DetailRow>
      <DetailRow label={t('observability.auditability.cost.inputCost')}>
        {formatAuditCostFromApiString(computed.subtotal_input, currency, notReported)}
      </DetailRow>
      <DetailRow label={t('observability.auditability.cost.outputCost')}>
        {formatAuditCostFromApiString(computed.subtotal_output, currency, notReported)}
      </DetailRow>
      <DetailRow label={t('observability.auditability.cost.totalCost')}>
        {formatAuditCostFromApiString(computed.total_cost, currency, notReported)}
      </DetailRow>
      <DetailRow label={t('observability.auditability.cost.currency')}>{formatScalar(currency, notReported)}</DetailRow>
      <DetailRow label={t('observability.auditability.cost.captureStatus')}>
        {captureStatusLabel(snap.capture_status, t)}
      </DetailRow>
      {pricingSource ? (
        <DetailRow label={t('observability.auditability.cost.calculationSource')}>{pricingSource}</DetailRow>
      ) : null}
      {computed.total_cost_unavailable_reason ? (
        <DetailRow label={t('observability.auditability.cost.unavailableReason')}>
          {formatScalar(computed.total_cost_unavailable_reason, notReported)}
        </DetailRow>
      ) : null}
      {snap.capture_notes && snap.capture_notes.length > 0 ? (
        <Box>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
            {t('observability.auditability.cost.captureNotes')}
          </Typography>
          <Stack component="ul" spacing={0.5} sx={{ m: 0, pl: 2 }}>
            {snap.capture_notes.map((note, idx) => (
              <Typography key={`${idx}-${note}`} component="li" variant="body2">
                {note}
              </Typography>
            ))}
          </Stack>
        </Box>
      ) : null}
    </Stack>
  );
}

const SOURCE_KEYS: (keyof RunAuditMetadataSources)[] = [
  'job_row',
  'result_json',
  'aisle_join',
  'inventory_join',
  'hybrid_report',
  'execution_log',
  'run_audit_snapshot',
];

export default function JobAuditabilityPanel({
  inventoryId,
  aisleId,
  jobId,
  active = true,
  auditability: controlled,
}: JobAuditabilityPanelProps) {
  const { t } = useTranslation();
  const empty = t('observability.auditability.notAvailable');
  const skipFetch = Boolean(controlled);
  const q = useJobAuditability(inventoryId, aisleId, jobId, {
    enabled: !skipFetch && active && Boolean(inventoryId && aisleId && jobId),
  });
  const data = controlled ?? q.data;
  const loading = !skipFetch && q.isLoading;
  const error = !skipFetch ? q.error : null;

  if (!jobId) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
        {t('jobs.obs_select_job_metadata_hint')}
      </Typography>
    );
  }

  if (loading) {
    return (
      <Stack direction="row" spacing={1} alignItems="center" sx={{ py: 3 }}>
        <CircularProgress size={22} />
        <Typography variant="body2" color="text.secondary">
          {t('observability.auditability.loading')}
        </Typography>
      </Stack>
    );
  }

  if (error) {
    return (
      <ErrorAlert
        message={resolveApiErrorMessage(error, 'observability.auditability.loadError')}
        onRetry={() => {
          void q.refetch();
        }}
      />
    );
  }

  if (!data) {
    return null;
  }

  const src = data.metadata_sources;
  const refUsage = data.reference_usage;

  return (
    <Stack spacing={2} data-testid="job-auditability-panel">
      <Typography variant="h6" component="h3">
        {t('observability.auditability.title')}
      </Typography>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          {t('observability.auditability.summary')}
        </Typography>
        <Stack spacing={1}>
          <DetailRow label={t('observability.auditability.jobId')}>{formatScalar(data.job_id, empty)}</DetailRow>
          <DetailRow label={t('observability.auditability.status')}>{formatScalar(data.status, empty)}</DetailRow>
          <DetailRow label={t('observability.auditability.legacyMode')}>{boolTriLabel(data.legacy_mode, t)}</DetailRow>
          <DetailRow label={t('observability.auditability.client')}>
            {formatScalar(data.client_id, t('observability.auditability.unknown'))}
          </DetailRow>
          <DetailRow label={t('observability.auditability.clientSupplier')}>
            {formatScalar(data.client_supplier_id, t('observability.auditability.unknown'))}
          </DetailRow>
          <DetailRow label={t('observability.auditability.provider')}>
            {formatScalar(data.provider_name, empty)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.model')}>{formatScalar(data.model_name, empty)}</DetailRow>
          <DetailRow label={t('observability.auditability.createdAt')}>
            {formatScalar(data.created_at, empty)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.startedAt')}>
            {formatScalar(data.started_at, empty)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.finishedAt')}>
            {formatScalar(data.finished_at, empty)}
          </DetailRow>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }} data-testid="job-auditability-cost">
        <Typography variant="subtitle2" gutterBottom>
          {t('observability.auditability.cost.title')}
        </Typography>
        {!data.cost_snapshot ? (
          <Typography variant="body2" color="text.secondary">
            {t('observability.auditability.cost.noData')}
          </Typography>
        ) : (
          <JobAuditabilityCostCard
            snap={data.cost_snapshot}
            notReported={t('observability.auditability.unknown')}
            t={t}
          />
        )}
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          {t('observability.auditability.effectivePrompt')}
        </Typography>
        <Stack spacing={1}>
          <DetailRow label={t('observability.auditability.promptKey')}>
            {formatScalar(data.prompt_key, empty)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.promptVersion')}>
            {formatScalar(data.prompt_version, empty)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.supplierConfigId')}>
            {formatScalar(data.supplier_prompt_config_id, empty)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.supplierConfigVersion')}>
            {formatScalar(data.supplier_prompt_config_version, empty)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.protectedContractKey')}>
            {formatScalar(data.protected_prompt_contract_key, empty)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.protectedContractVersion')}>
            {formatScalar(data.protected_prompt_contract_version, empty)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.effectiveHash')}>
            {formatScalar(data.effective_prompt_hash, empty)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.compositionAvailable')}>
            {boolTriLabel(data.prompt_composition_available, t)}
          </DetailRow>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          {t('observability.auditability.fallbackAndWarnings')}
        </Typography>
        <Stack spacing={1}>
          <DetailRow label={t('observability.auditability.fallbackApplied')}>
            {boolTriLabel(data.supplier_prompt_fallback_used, t)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.fallbackReason')}>
            {formatScalar(data.supplier_prompt_fallback_reason, t('observability.auditability.unknown'))}
          </DetailRow>
          {data.warnings?.length ? (
            <Box>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                {t('observability.auditability.warnings')}
              </Typography>
              <Stack component="ul" spacing={0.5} sx={{ m: 0, pl: 2 }}>
                {data.warnings.map((w) => (
                  <Typography key={w} component="li" variant="body2">
                    {w}
                  </Typography>
                ))}
              </Stack>
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">
              {t('observability.auditability.noWarnings')}
            </Typography>
          )}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          {t('observability.auditability.visualReferences')}
        </Typography>
        <Stack spacing={1}>
          <DetailRow label={t('observability.auditability.referenceSource')}>
            {formatScalar(data.reference_source, empty)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.referenceImageCount')}>
            {data.reference_image_count != null ? String(data.reference_image_count) : empty}
          </DetailRow>
          <DetailRow label={t('observability.auditability.supplierRefsUsed')}>
            {boolTriLabel(data.supplier_reference_images_used, t)}
          </DetailRow>
          <DetailRow label={t('observability.auditability.inventoryVisualRefsUsed')}>
            {data.inventory_visual_references_used === null ? (
              <Stack spacing={0.5}>
                <span>{t('observability.auditability.unknown')}</span>
                <Typography variant="caption" color="text.secondary">
                  {t('observability.auditability.inventoryVisualRefsHint')}
                </Typography>
              </Stack>
            ) : (
              boolTriLabel(data.inventory_visual_references_used, t)
            )}
          </DetailRow>
          {refUsage ? (
            <>
              <DetailRow label={t('observability.auditability.refResolved')}>
                {boolTriLabel(refUsage.resolved, t)}
              </DetailRow>
              <DetailRow label={t('observability.auditability.refResolvedCount')}>
                {String(refUsage.resolved_count)}
              </DetailRow>
              <DetailRow label={t('observability.auditability.refProviderConsumed')}>
                {boolTriLabel(refUsage.provider_consumed, t)}
              </DetailRow>
              <DetailRow label={t('observability.auditability.refProviderConsumedCount')}>
                {String(refUsage.provider_consumed_count)}
              </DetailRow>
              {refUsage.resolution_error ? (
                <DetailRow label={t('observability.auditability.refResolutionError')}>
                  {refUsage.resolution_error}
                </DetailRow>
              ) : null}
            </>
          ) : null}
          <DetailRow label={t('observability.auditability.referenceIds')}>
            {data.reference_ids?.length
              ? data.reference_ids.join(', ')
              : data.reference_ids?.length === 0
                ? t('observability.auditability.none')
                : empty}
          </DetailRow>
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          {t('observability.auditability.metadataSources')}
        </Typography>
        <Stack direction="row" flexWrap="wrap" gap={1}>
          {SOURCE_KEYS.map((key) => (
            <Chip
              key={key}
              size="small"
              label={t(`observability.auditability.source_${key}`)}
              color={src[key] ? 'success' : 'default'}
              variant={src[key] ? 'filled' : 'outlined'}
            />
          ))}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          {t('observability.auditability.missingMetadata')}
        </Typography>
        {data.missing_metadata?.length ? (
          <>
            <Alert severity="info" sx={{ mb: 1 }}>
              {t('observability.auditability.missingMetadataDescription')}
            </Alert>
            <Stack component="ul" spacing={0.5} sx={{ m: 0, pl: 2 }}>
              {data.missing_metadata.map((k) => (
                <Typography key={k} component="li" variant="body2" sx={{ fontFamily: 'monospace' }}>
                  {k}
                </Typography>
              ))}
            </Stack>
          </>
        ) : (
          <Typography variant="body2" color="text.secondary">
            {t('observability.auditability.noMissingMetadata')}
          </Typography>
        )}
      </Paper>
    </Stack>
  );
}
