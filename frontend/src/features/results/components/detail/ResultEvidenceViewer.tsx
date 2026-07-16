/**
 * Sprint 4.3 — Evidence viewer: inline primary preview + generic fullscreen dialog.
 * Phase 4.8: When structural evidenceView exists, use backend imageUrl (no legacy asset loader).
 * Supports result-detail mode and asset mode (manual image coverage drawer).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Box, Chip, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { ImagePreviewDialog } from '../../../../components/ui';
import type { ResultDetail } from '../../types';
import { useEvidenceImageLoad } from '../../hooks/useEvidenceImageLoad';
import {
  isEvidenceDisplayable,
  isReviewContextDisplayable,
  resolveReviewContextImageUrl,
  resolveStructuralEvidenceImageUrl,
} from '../../utils/evidenceEligibility';
import { evidenceUnavailableMessage } from '../../utils/evidenceUnavailableMessage';
import i18n from '../../../../i18n';
import EvidencePreviewStage, {
  type EvidenceViewerVariant,
} from './EvidencePreviewStage';

export interface ResultEvidenceViewerResultProps {
  result: ResultDetail;
  inventoryId: string;
  aisleId: string;
  variant?: EvidenceViewerVariant;
  /** When false, skip authenticated image load (e.g. parent drawer closed). Default true. */
  enabled?: boolean;
}

export interface ResultEvidenceViewerAssetProps {
  result?: undefined;
  inventoryId: string;
  aisleId: string;
  assetId: string;
  jobId?: string | null;
  filename?: string | null;
  variant?: EvidenceViewerVariant;
  enabled?: boolean;
}

export type ResultEvidenceViewerProps =
  | ResultEvidenceViewerResultProps
  | ResultEvidenceViewerAssetProps;

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

function legacySpecForFrame(
  frame: EvidenceFrame | null,
  inventoryId: string,
  aisleId: string,
  jobId: string | null,
  enabled: boolean
) {
  if (!enabled || !frame?.useLegacyLoader) return null;
  return { inventoryId, aisleId, assetId: frame.key, jobId };
}

function frameAltText(frame: EvidenceFrame, t: (key: string, opts?: Record<string, string>) => string): string {
  return frame.fileName
    ? t('results.evidence_viewer.alt_file', { fileName: frame.fileName })
    : t('results.evidence_viewer.alt_image');
}

function frameDialogTitle(frame: EvidenceFrame, t: (key: string) => string): string {
  return frame.fileName
    ? `${frame.label} · ${frame.fileName}`
    : frame.label || t('results.evidence_viewer.title_fallback');
}

function isAssetProps(props: ResultEvidenceViewerProps): props is ResultEvidenceViewerAssetProps {
  return props.result == null && typeof (props as ResultEvidenceViewerAssetProps).assetId === 'string';
}

export default function ResultEvidenceViewer(props: ResultEvidenceViewerProps) {
  const inventoryId = props.inventoryId;
  const aisleId = props.aisleId;
  const variant: EvidenceViewerVariant =
    props.variant ?? (isAssetProps(props) ? 'manual-result' : 'review');
  const enabled = props.enabled !== false;

  if (isAssetProps(props)) {
    return (
      <AssetModeEvidenceViewer
        inventoryId={inventoryId}
        aisleId={aisleId}
        assetId={props.assetId}
        jobId={props.jobId ?? null}
        filename={props.filename ?? null}
        variant={variant}
        enabled={enabled}
      />
    );
  }

  return (
    <ResultModeEvidenceViewer
      result={props.result}
      inventoryId={inventoryId}
      aisleId={aisleId}
      variant={variant}
      enabled={enabled}
    />
  );
}

function AssetModeEvidenceViewer({
  inventoryId,
  aisleId,
  assetId,
  jobId,
  filename,
  variant,
  enabled,
}: {
  inventoryId: string;
  aisleId: string;
  assetId: string;
  jobId: string | null;
  filename: string | null;
  variant: EvidenceViewerVariant;
  enabled: boolean;
}) {
  const { t } = useTranslation();
  const [previewOpen, setPreviewOpen] = useState(false);

  const loadSpec = useMemo(
    () =>
      enabled && assetId.trim()
        ? { inventoryId, aisleId, assetId: assetId.trim(), jobId }
        : null,
    [enabled, inventoryId, aisleId, assetId, jobId]
  );
  const loadState = useEvidenceImageLoad(loadSpec);

  const src = loadState.status === 'loaded' ? loadState.imageSrc : null;
  const loading = loadState.status === 'loading';
  const error = loadState.status === 'error' ? loadState.message : null;
  const canOpen = Boolean(src) && !error;
  const alt = filename
    ? t('results.evidence_viewer.alt_file', { fileName: filename })
    : t('results.evidence_viewer.alt_image');

  return (
    <Box data-testid="result-evidence-viewer" data-mode="asset">
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1.5 }}>
        {t('results.evidence_viewer.heading')}
      </Typography>
      <EvidencePreviewStage
        src={src}
        alt={alt}
        loading={loading}
        error={error}
        fileName={filename}
        label={t('results.evidence_viewer.primary')}
        variant={variant}
        canOpenFullscreen={canOpen}
        onOpenFullscreen={() => {
          if (canOpen) setPreviewOpen(true);
        }}
      />
      <ImagePreviewDialog
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        title={
          filename
            ? `${t('results.evidence_viewer.primary')} · ${filename}`
            : t('results.evidence_viewer.title_fallback')
        }
        src={src}
        alt={alt}
        loading={loading}
        error={error}
        caption={filename}
      />
    </Box>
  );
}

function ResultModeEvidenceViewer({
  result,
  inventoryId,
  aisleId,
  variant,
  enabled,
}: {
  result: ResultDetail;
  inventoryId: string;
  aisleId: string;
  variant: EvidenceViewerVariant;
  enabled: boolean;
}) {
  const { t } = useTranslation();
  const evidenceIsDisplayable = isEvidenceDisplayable(
    result.traceabilityStatus,
    result.hasValidEvidence,
    result.sourceImageId,
    result.evidenceView
  );
  const reviewContextDisplayable = isReviewContextDisplayable(result.evidenceView);
  const reviewContextUrl = resolveReviewContextImageUrl(result.evidenceView);
  const frames = useMemo(() => {
    if (evidenceIsDisplayable) {
      return buildFrames(result);
    }
    if (reviewContextDisplayable && reviewContextUrl) {
      return [
        {
          key: 'review-context-primary',
          label: t('results.evidence_viewer.scan_image'),
          fileName: result.sourceFileName,
          imageUrl: reviewContextUrl,
          useLegacyLoader: false,
        },
      ];
    }
    return [];
  }, [result, evidenceIsDisplayable, reviewContextDisplayable, reviewContextUrl, t]);
  const primaryFrame = frames[0] ?? null;
  const additionalFrames = frames.slice(1);

  const [previewFrame, setPreviewFrame] = useState<EvidenceFrame | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [directImageLoadError, setDirectImageLoadError] = useState(false);

  const primaryDirectUrl =
    primaryFrame && !primaryFrame.useLegacyLoader ? primaryFrame.imageUrl : null;

  useEffect(() => {
    setDirectImageLoadError(false);
  }, [primaryDirectUrl]);

  const jobId = jobIdFromResult(result);

  const primaryLegacySpec = useMemo(
    () => legacySpecForFrame(primaryFrame, inventoryId, aisleId, jobId, enabled),
    [primaryFrame, inventoryId, aisleId, jobId, enabled]
  );
  const primaryLoadState = useEvidenceImageLoad(primaryLegacySpec);

  const secondaryLegacySpec = useMemo(() => {
    if (!enabled || !previewFrame?.useLegacyLoader || previewFrame.key === primaryFrame?.key) {
      return null;
    }
    return legacySpecForFrame(previewFrame, inventoryId, aisleId, jobId, enabled);
  }, [previewFrame, primaryFrame, inventoryId, aisleId, jobId, enabled]);
  const secondaryLoadState = useEvidenceImageLoad(secondaryLegacySpec);

  const resolveFrameSrc = useCallback(
    (frame: EvidenceFrame | null): string | null => {
      if (!frame) return null;
      if (!frame.useLegacyLoader) return frame.imageUrl;
      if (frame.key === primaryFrame?.key) {
        return primaryLoadState.status === 'loaded' ? primaryLoadState.imageSrc : null;
      }
      if (previewFrame?.key === frame.key && secondaryLoadState.status === 'loaded') {
        return secondaryLoadState.imageSrc;
      }
      return null;
    },
    [primaryFrame, primaryLoadState, previewFrame, secondaryLoadState]
  );

  const resolveFrameLoading = useCallback(
    (frame: EvidenceFrame | null): boolean => {
      if (!frame?.useLegacyLoader) return false;
      if (frame.key === primaryFrame?.key) return primaryLoadState.status === 'loading';
      if (previewFrame?.key === frame.key) return secondaryLoadState.status === 'loading';
      return false;
    },
    [primaryFrame, primaryLoadState, previewFrame, secondaryLoadState]
  );

  const resolveFrameError = useCallback(
    (frame: EvidenceFrame | null): string | null => {
      if (!frame?.useLegacyLoader) return null;
      if (frame.key === primaryFrame?.key && primaryLoadState.status === 'error') {
        return primaryLoadState.message;
      }
      if (previewFrame?.key === frame.key && secondaryLoadState.status === 'error') {
        return secondaryLoadState.message;
      }
      return null;
    },
    [primaryFrame, primaryLoadState, previewFrame, secondaryLoadState]
  );

  const resolveDirectImageError = useCallback(
    (frame: EvidenceFrame | null): boolean => {
      if (!frame || frame.useLegacyLoader) return false;
      return frame.key === primaryFrame?.key && directImageLoadError;
    },
    [primaryFrame, directImageLoadError]
  );

  const canOpenFrameFullscreen = useCallback(
    (frame: EvidenceFrame | null): boolean => {
      if (!frame) return false;
      const src = resolveFrameSrc(frame);
      if (!src) return false;
      if (resolveFrameError(frame)) return false;
      if (resolveDirectImageError(frame)) return false;
      return true;
    },
    [resolveFrameSrc, resolveFrameError, resolveDirectImageError]
  );

  const openFullscreen = useCallback(
    (frame: EvidenceFrame) => {
      if (!canOpenFrameFullscreen(frame)) return;
      setPreviewFrame(frame);
      setPreviewOpen(true);
    },
    [canOpenFrameFullscreen]
  );

  const closeFullscreen = useCallback(() => {
    setPreviewOpen(false);
    setPreviewFrame(null);
  }, []);

  useEffect(() => {
    if (!evidenceIsDisplayable && !reviewContextDisplayable) {
      closeFullscreen();
    }
  }, [evidenceIsDisplayable, reviewContextDisplayable, closeFullscreen]);

  const primarySrc = resolveFrameSrc(primaryFrame);
  const primaryLoading = resolveFrameLoading(primaryFrame);
  const primaryLegacyError = resolveFrameError(primaryFrame);
  const primaryDirectLoadFailed = resolveDirectImageError(primaryFrame);
  const primaryError =
    primaryLegacyError ??
    (primaryDirectLoadFailed ? t('results.evidence_viewer.image_load_error') : null);
  const dialogFrame = previewFrame ?? primaryFrame;
  const dialogSrc = resolveFrameSrc(dialogFrame);
  const dialogLoading = resolveFrameLoading(dialogFrame);
  const dialogLegacyError = resolveFrameError(dialogFrame);
  const dialogDirectLoadFailed = resolveDirectImageError(dialogFrame);
  const dialogError =
    dialogLegacyError ??
    (dialogDirectLoadFailed ? t('results.evidence_viewer.image_load_error') : null);

  const hasRecordOnly =
    evidenceIsDisplayable && result.evidence.length > 0 && frames.length === 0;
  const structuralUrlMissing =
    evidenceIsDisplayable &&
    result.evidenceView != null &&
    resolveStructuralEvidenceImageUrl(result.evidenceView) == null;

  return (
    <Box data-testid="result-evidence-viewer" data-mode="result">
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1.5 }}>
        {t('results.evidence_viewer.heading')}
      </Typography>

      {!evidenceIsDisplayable && !reviewContextDisplayable && (
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

      {!evidenceIsDisplayable && reviewContextDisplayable && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="body2" color="warning.main">
            {t('results.evidence_viewer.review_context_warning')}
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

      {primaryFrame ? (
        <>
          <EvidencePreviewStage
            src={primarySrc}
            alt={frameAltText(primaryFrame, t)}
            loading={primaryLoading}
            error={primaryError}
            fileName={primaryFrame.fileName}
            label={primaryFrame.label}
            variant={variant}
            canOpenFullscreen={canOpenFrameFullscreen(primaryFrame)}
            onOpenFullscreen={() => openFullscreen(primaryFrame)}
            onImageLoad={() => setDirectImageLoadError(false)}
            onImageError={() => {
              if (!primaryFrame.useLegacyLoader) {
                setDirectImageLoadError(true);
              }
            }}
          />

          {additionalFrames.length > 0 ? (
            <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 1.5 }}>
              {additionalFrames.map((frame) => (
                <Chip
                  key={frame.key}
                  size="small"
                  variant="outlined"
                  label={frame.fileName ? `${frame.label} · ${frame.fileName}` : frame.label}
                  onClick={() => openFullscreen(frame)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      openFullscreen(frame);
                    }
                  }}
                  clickable
                  component="button"
                  sx={{ maxWidth: '100%' }}
                />
              ))}
            </Stack>
          ) : null}

          <ImagePreviewDialog
            open={previewOpen}
            onClose={closeFullscreen}
            title={dialogFrame ? frameDialogTitle(dialogFrame, t) : t('results.evidence_viewer.title_fallback')}
            src={dialogSrc}
            alt={dialogFrame ? frameAltText(dialogFrame, t) : t('results.evidence_viewer.alt_image')}
            loading={dialogLoading}
            error={dialogError}
            caption={dialogFrame?.fileName ?? dialogFrame?.label}
          />
        </>
      ) : null}
    </Box>
  );
}
