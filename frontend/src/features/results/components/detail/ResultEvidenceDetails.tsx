/**
 * Phase 4.8 — Compact audit panel for structural result_evidence contract.
 */

import { Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ResultEvidenceView } from '../../types';

export interface ResultEvidenceDetailsProps {
  evidenceView: ResultEvidenceView | null | undefined;
  /** Optional artifact status from job/position traceability metadata. */
  artifactStatus?: string | null;
  /** Optional artifact content hash from traceability_manifest metadata. */
  artifactHash?: string | null;
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: 'flex', gap: 1, py: 0.25 }}>
      <Typography variant="caption" color="text.secondary" sx={{ minWidth: 140, flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography variant="caption" component="span" sx={{ wordBreak: 'break-all' }}>
        {value}
      </Typography>
    </Box>
  );
}

export default function ResultEvidenceDetails({
  evidenceView,
  artifactStatus,
  artifactHash,
}: ResultEvidenceDetailsProps) {
  const { t } = useTranslation();

  if (
    evidenceView == null &&
    (artifactStatus == null || artifactStatus.trim() === '') &&
    (artifactHash == null || artifactHash.trim() === '')
  ) {
    return null;
  }

  const rows: Array<{ label: string; value: string }> = [];

  if (evidenceView != null) {
    rows.push({
      label: t('results.evidence_details.traceability_status'),
      value: String(evidenceView.traceabilityStatus),
    });

    if (
      evidenceView.traceabilityWarning != null &&
      evidenceView.traceabilityWarning.trim() !== ''
    ) {
      rows.push({
        label: t('results.evidence_details.traceability_warning'),
        value: evidenceView.traceabilityWarning.trim(),
      });
    }

    if (
      evidenceView.resolvedManifestEntryId != null &&
      evidenceView.resolvedManifestEntryId.trim() !== ''
    ) {
      rows.push({
        label: t('results.evidence_details.resolved_manifest_entry_id'),
        value: evidenceView.resolvedManifestEntryId.trim(),
      });
    }

    if (
      evidenceView.rawManifestEntryId != null &&
      evidenceView.rawManifestEntryId.trim() !== ''
    ) {
      rows.push({
        label: t('results.evidence_details.raw_manifest_entry_id'),
        value: evidenceView.rawManifestEntryId.trim(),
      });
    }

    if (evidenceView.provider != null && evidenceView.provider.trim() !== '') {
      rows.push({
        label: t('results.evidence_details.provider'),
        value: evidenceView.provider.trim(),
      });
    }

    if (evidenceView.modelName != null && evidenceView.modelName.trim() !== '') {
      rows.push({
        label: t('results.evidence_details.model_name'),
        value: evidenceView.modelName.trim(),
      });
    }

    if (evidenceView.sourceKind != null && String(evidenceView.sourceKind).trim() !== '') {
      rows.push({
        label: t('results.evidence_details.source_kind'),
        value: String(evidenceView.sourceKind),
      });
    }

    if (
      evidenceView.imageAccessStatus != null &&
      String(evidenceView.imageAccessStatus).trim() !== ''
    ) {
      rows.push({
        label: t('results.evidence_details.image_access_status'),
        value: String(evidenceView.imageAccessStatus),
      });
    }
  }

  if (artifactStatus != null && artifactStatus.trim() !== '') {
    rows.push({
      label: t('results.evidence_details.artifact_status'),
      value: artifactStatus.trim(),
    });
  }

  if (artifactHash != null && artifactHash.trim() !== '') {
    rows.push({
      label: t('results.evidence_details.artifact_hash'),
      value: artifactHash.trim(),
    });
  }

  if (rows.length === 0) {
    return null;
  }

  return (
    <Box
      sx={{
        mt: 2,
        p: 1.5,
        bgcolor: 'grey.50',
        borderRadius: 1,
        border: '1px solid',
        borderColor: 'divider',
      }}
    >
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: 'block', mb: 1, fontWeight: 700, textTransform: 'uppercase' }}
      >
        {t('results.evidence_details.heading')}
      </Typography>
      {rows.map((row) => (
        <DetailRow key={row.label} label={row.label} value={row.value} />
      ))}
    </Box>
  );
}
