/**
 * Sprint 4.3 — Evidence viewer: main image anchor, zoom, fullscreen, multi-image selection (label chips).
 * Phase 4.8: When structural evidenceView exists, use backend imageUrl (no legacy asset loader).
 */

import { useEffect, useMemo, useState } from 'react';
import { Box, Button, Typography, Divider } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { ImageAssetCard, ImagePreviewDialog } from '../../../../components/ui';
import type { ResultDetail } from '../../types';
import { useEvidenceImageLoad } from '../../hooks/useEvidenceImageLoad';
import {
  isEvidenceDisplayable,
  resolveStructuralEvidenceImageUrl,
} from '../../utils/evidenceEligibility';
import { evidenceUnavailableMessage } from '../../utils/evidenceUnavailableMessage';
import i18n from '../../../../i18n';

export interface ResultEvidenceViewerProps {
  result: ResultDetail;
  inventoryId: string;
  aisleId: string;
}

interface EvidenceFrame {
  key: string;
  label: string;
  fileName: string | null;
  imageUrl: string | null;
  useLegacyLoader: boolean;
}

function jobIdFromResult(result: ResultDetail): string | null {
  const entityId = result.technicalMetadata?.entityId;
  if (!entityId || typeof entityId !== 'string') return null;
  const idx = entityId.lastIndexOf('_');
  return idx > 0 ? entityId.slice(0, idx) : null;
}

function buildFrames(result: ResultDetail): EvidenceFrame[] {
  const evidenceIsDisplayable = isEvidenceDisplayable(
    result.traceabilityStatus,
    result.hasValidEvidence,
    result.sourceImageId,
    result.evidenceView
  );
  if (!evidenceIsDisplayable) {
    return [];
  }

  const structuralUrl = resolveStructuralEvidenceImageUrl(result.evidenceView);
  if (result.evidenceView != null) {
    if (structuralUrl == null) {
      return [];
    }
    return [
      {
        key: 'structural-primary',
        label: i18n.t('results.evidence_viewer.primary'),
        fileName: result.sourceFileName,
        imageUrl: structuralUrl,
        useLegacyLoader: false,
      },
    ];
  }

  const seen = new Set<string>();
  const drafts: Array<{
    key: string;
    fileName: string | null;
    label: string;
    imageUrl: string | null;
    useLegacyLoader: boolean;
  }> = [];

  const push = (assetId: string | null | undefined, fileName: string | null, label: string) => {
    const id = assetId != null ? String(assetId).trim() : '';
    if (!id || seen.has(id)) return;
    seen.add(id);
    drafts.push({
      key: id,
      fileName,
      label,
      imageUrl: null,
      useLegacyLoader: true,
    });
  };

  const primaryEvidenceId = result.technicalMetadata?.primaryEvidenceId?.trim() || null;
  const sortedEvidence = [...result.evidence].sort((a, b) => {
    if (primaryEvidenceId) {
      if (a.id === primaryEvidenceId) return -1;
      if (b.id === primaryEvidenceId) return 1;
    }
    if (a.role === 'PRIMARY' && b.role !== 'PRIMARY') return -1;
    if (b.role === 'PRIMARY' && a.role !== 'PRIMARY') return 1;
    return 0;
  });

  let supportingOrdinal = 0;
  sortedEvidence.forEach((ev) => {
    const isPrimary =
      (primaryEvidenceId != null && ev.id === primaryEvidenceId) ||
      (primaryEvidenceId == null && ev.role === 'PRIMARY');
    let label: string;
    if (isPrimary) {
      label = i18n.t('results.evidence_viewer.primary');
    } else if (sortedEvidence.length === 1) {
      label = i18n.t('results.evidence_viewer.generic');
    } else {
      supportingOrdinal += 1;
      label = i18n.t('results.evidence_viewer.supporting', { n: supportingOrdinal });
    }
    push(ev.sourceImageId, ev.sourceFileName, label);
  });

  push(result.sourceImageId, result.sourceFileName, i18n.t('results.evidence_viewer.full_source'));

  return drafts.map((d) => ({
    key: d.key,
    fileName: d.fileName,
    label: d.label,
    imageUrl: d.imageUrl,
    useLegacyLoader: d.useLegacyLoader,
  }));
}

export default function ResultEvidenceViewer({ result, inventoryId, aisleId }: ResultEvidenceViewerProps) {
  const { t } = useTranslation();
  const evidenceIsDisplayable = isEvidenceDisplayable(
    result.traceabilityStatus,
    result.hasValidEvidence,
    result.sourceImageId,
    result.evidenceView
  );
  const frames = useMemo(
    () => (evidenceIsDisplayable ? buildFrames(result) : []),
    [result, evidenceIsDisplayable]
  );
  const [previewTarget, setPreviewTarget] = useState<EvidenceFrame | null>(null);

  useEffect(() => {
    if (!evidenceIsDisplayable) {
      setPreviewTarget(null);
    }
  }, [evidenceIsDisplayable]);

  const jobId = jobIdFromResult(result);
  const legacyImageSpec =
    previewTarget?.useLegacyLoader === true
      ? { inventoryId, aisleId, assetId: previewTarget.key, jobId }
      : null;

  const loadState = useEvidenceImageLoad(legacyImageSpec);

  const previewSrc =
    previewTarget?.useLegacyLoader === false
      ? previewTarget.imageUrl
      : loadState.status === 'loaded'
        ? loadState.imageSrc
        : null;

  const hasRecordOnly =
    evidenceIsDisplayable && result.evidence.length > 0 && frames.length === 0;
  const structuralUrlMissing =
    evidenceIsDisplayable &&
    result.evidenceView != null &&
    resolveStructuralEvidenceImageUrl(result.evidenceView) == null;

  return (
    <Box>
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1.5 }}>
        {t('results.evidence_viewer.heading')}
      </Typography>

      {!evidenceIsDisplayable && (
        <Box
          sx={{
            py: 4,
            px: 2,
            textAlign: 'center',
            bgcolor: 'action.hover',
            borderRadius: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Typography color="text.secondary">
            {evidenceUnavailableMessage(result.traceabilityStatus, t)}
          </Typography>
        </Box>
      )}

      {structuralUrlMissing && (
        <Box sx={{ py: 4, px: 2, bgcolor: 'action.hover', borderRadius: 1, textAlign: 'center' }}>
          <Typography color="text.secondary">{t('results.evidence_viewer.url_unavailable')}</Typography>
        </Box>
      )}

      {hasRecordOnly && (
        <Box sx={{ py: 3, px: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
          <Typography variant="body2" color="text.secondary">
            {t('results.evidence_viewer.record_only')}
          </Typography>
        </Box>
      )}

      {frames.length > 0 && (
        <>
          <Box
            sx={{
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 2,
              overflow: 'hidden',
              bgcolor: 'background.default',
            }}
          >
            {frames.map((f, i) => (
              <Box key={f.key}>
                {i > 0 && <Divider />}
                <ImageAssetCard
                  title={f.fileName || f.label}
                  subtitle={f.fileName ? f.label : t('results.evidence_viewer.subtitle_fallback')}
                  actions={
                    <Button variant="outlined" size="small" onClick={() => setPreviewTarget(f)}>
                      {t('results.evidence_viewer.preview')}
                    </Button>
                  }
                />
              </Box>
            ))}
          </Box>

          <ImagePreviewDialog
            open={Boolean(previewTarget)}
            onClose={() => setPreviewTarget(null)}
            title={
              previewTarget?.fileName
                ? `${previewTarget.label} · ${previewTarget.fileName}`
                : previewTarget?.label ?? t('results.evidence_viewer.title_fallback')
            }
            src={previewSrc}
            alt={
              previewTarget?.fileName
                ? t('results.evidence_viewer.alt_file', { fileName: previewTarget.fileName })
                : t('results.evidence_viewer.alt_image')
            }
            loading={previewTarget?.useLegacyLoader === true && loadState.status === 'loading'}
            error={
              previewTarget?.useLegacyLoader === true && loadState.status === 'error'
                ? loadState.message
                : null
            }
            caption={previewTarget?.fileName ?? previewTarget?.label}
          />
        </>
      )}
    </Box>
  );
}
