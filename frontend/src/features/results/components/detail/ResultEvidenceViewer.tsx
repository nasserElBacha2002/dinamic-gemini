/**
 * Sprint 4.3 — Evidence viewer: inline primary preview + generic fullscreen dialog.
 * Phase 4.8: When structural evidenceView exists, use backend imageUrl (no legacy asset loader).
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  IconButton,
  Stack,
  Typography,
} from '@mui/material';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
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

function legacySpecForFrame(
  frame: EvidenceFrame | null,
  inventoryId: string,
  aisleId: string,
  jobId: string | null
) {
  if (!frame?.useLegacyLoader) return null;
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

export default function ResultEvidenceViewer({ result, inventoryId, aisleId }: ResultEvidenceViewerProps) {
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
    () => legacySpecForFrame(primaryFrame, inventoryId, aisleId, jobId),
    [primaryFrame, inventoryId, aisleId, jobId]
  );
  const primaryLoadState = useEvidenceImageLoad(primaryLegacySpec);

  const secondaryLegacySpec = useMemo(() => {
    if (!previewFrame?.useLegacyLoader || previewFrame.key === primaryFrame?.key) {
      return null;
    }
    return legacySpecForFrame(previewFrame, inventoryId, aisleId, jobId);
  }, [previewFrame, primaryFrame, inventoryId, aisleId, jobId]);
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
  const primaryError = primaryLegacyError
    ?? (primaryDirectLoadFailed ? t('results.evidence_viewer.image_load_error') : null);
  const primaryImageRenderable = Boolean(primarySrc) && !primaryLegacyError && !primaryDirectLoadFailed;
  const dialogFrame = previewFrame ?? primaryFrame;
  const dialogSrc = resolveFrameSrc(dialogFrame);
  const dialogLoading = resolveFrameLoading(dialogFrame);
  const dialogLegacyError = resolveFrameError(dialogFrame);
  const dialogDirectLoadFailed = resolveDirectImageError(dialogFrame);
  const dialogError = dialogLegacyError
    ?? (dialogDirectLoadFailed ? t('results.evidence_viewer.image_load_error') : null);

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
          <Box
            data-testid="result-evidence-inline-preview"
            sx={{
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 2,
              overflow: 'hidden',
              bgcolor: 'background.default',
            }}
          >
            <Box
              sx={{
                position: 'relative',
                bgcolor: 'grey.900',
                minHeight: 180,
                maxHeight: 320,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {primaryLoading ? (
                <CircularProgress size={28} sx={{ color: 'grey.400' }} />
              ) : null}
              {primaryError ? (
                <Typography variant="body2" color="error.light" sx={{ px: 2, textAlign: 'center' }}>
                  {primaryError}
                </Typography>
              ) : null}
              {primaryImageRenderable ? (
                <>
                  <Box
                    component="button"
                    type="button"
                    onClick={() => openFullscreen(primaryFrame)}
                    aria-label={t('results.evidence_viewer.expand_image')}
                    sx={{
                      border: 0,
                      p: 0,
                      m: 0,
                      width: '100%',
                      maxHeight: 320,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      bgcolor: 'transparent',
                      cursor: 'pointer',
                    }}
                  >
                    <Box
                      component="img"
                      src={primarySrc ?? undefined}
                      alt={frameAltText(primaryFrame, t)}
                      onLoad={() => setDirectImageLoadError(false)}
                      onError={() => {
                        if (!primaryFrame.useLegacyLoader) {
                          setDirectImageLoadError(true);
                        }
                      }}
                      sx={{
                        display: 'block',
                        maxWidth: '100%',
                        maxHeight: 320,
                        width: 'auto',
                        height: 'auto',
                        objectFit: 'contain',
                      }}
                    />
                  </Box>
                  <IconButton
                    size="small"
                    onClick={() => openFullscreen(primaryFrame)}
                    aria-label={t('results.evidence_viewer.open_fullscreen')}
                    sx={{
                      position: 'absolute',
                      top: 8,
                      right: 8,
                      bgcolor: 'rgba(0,0,0,0.45)',
                      color: 'common.white',
                      '&:hover': { bgcolor: 'rgba(0,0,0,0.6)' },
                    }}
                  >
                    <FullscreenIcon fontSize="small" />
                  </IconButton>
                </>
              ) : null}
            </Box>

            <Box sx={{ px: 2, py: 1.5 }}>
              <Typography variant="body2" fontWeight={600} noWrap title={primaryFrame.fileName ?? undefined}>
                {primaryFrame.fileName || t('results.evidence_viewer.subtitle_fallback')}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>
                {primaryFrame.label}
              </Typography>
              <Button
                variant="outlined"
                size="small"
                onClick={() => openFullscreen(primaryFrame)}
                disabled={!canOpenFrameFullscreen(primaryFrame) && !primaryLoading}
                data-testid="result-evidence-open-fullscreen"
                sx={{ mt: 1.25, textTransform: 'none' }}
              >
                {t('results.evidence_viewer.open_fullscreen')}
              </Button>
            </Box>
          </Box>

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
