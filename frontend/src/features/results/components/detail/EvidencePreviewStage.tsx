/**
 * Shared evidence image stage used by ResultEvidenceViewer (review + manual-result).
 * Dark canvas, object-fit contain, fullscreen affordance — no authenticated load logic here.
 */

import { Box, Button, CircularProgress, IconButton, Typography } from '@mui/material';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import { useTranslation } from 'react-i18next';

export type EvidenceViewerVariant = 'review' | 'manual-result';

export interface EvidencePreviewStageProps {
  src: string | null;
  alt: string;
  loading?: boolean;
  error?: string | null;
  fileName?: string | null;
  label?: string | null;
  variant?: EvidenceViewerVariant;
  canOpenFullscreen?: boolean;
  onOpenFullscreen?: () => void;
  onImageLoad?: () => void;
  onImageError?: () => void;
  /** When false, omit the bottom meta row (filename / fullscreen button). */
  showMeta?: boolean;
}

const STAGE_LAYOUT: Record<
  EvidenceViewerVariant,
  {
    minHeight: { xs: number; sm: number; md: number };
    maxHeight: string;
  }
> = {
  review: {
    minHeight: { xs: 220, sm: 280, md: 340 },
    maxHeight: 'min(55vh, 560px)',
  },
  'manual-result': {
    minHeight: { xs: 280, sm: 360, md: 440 },
    maxHeight: 'min(65vh, 720px)',
  },
};

export default function EvidencePreviewStage({
  src,
  alt,
  loading = false,
  error = null,
  fileName = null,
  label = null,
  variant = 'review',
  canOpenFullscreen = false,
  onOpenFullscreen,
  onImageLoad,
  onImageError,
  showMeta = true,
}: EvidencePreviewStageProps) {
  const { t } = useTranslation();
  const layout = STAGE_LAYOUT[variant];
  const imageRenderable = Boolean(src) && !error && !loading;

  return (
    <Box
      data-testid="result-evidence-inline-preview"
      data-variant={variant}
      sx={{
        width: '100%',
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 2,
        overflow: 'hidden',
        bgcolor: 'background.default',
      }}
    >
      <Box
        data-testid="evidence-preview-stage"
        sx={{
          position: 'relative',
          width: '100%',
          bgcolor: 'grey.900',
          minHeight: layout.minHeight,
          maxHeight: layout.maxHeight,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
        }}
      >
        {loading ? (
          <CircularProgress
            size={28}
            sx={{ color: 'grey.400' }}
            aria-label={t('results.evidence_viewer.loading', { defaultValue: 'Loading image' })}
          />
        ) : null}
        {error ? (
          <Typography
            variant="body2"
            color="error.light"
            role="alert"
            sx={{ px: 2, textAlign: 'center' }}
          >
            {error}
          </Typography>
        ) : null}
        {imageRenderable ? (
          <>
            <Box
              component="button"
              type="button"
              onClick={onOpenFullscreen}
              disabled={!canOpenFullscreen}
              aria-label={t('results.evidence_viewer.expand_image')}
              sx={{
                border: 0,
                p: 0,
                m: 0,
                width: '100%',
                height: '100%',
                minHeight: layout.minHeight,
                maxHeight: layout.maxHeight,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                bgcolor: 'transparent',
                cursor: canOpenFullscreen ? 'pointer' : 'default',
              }}
            >
              <Box
                component="img"
                src={src ?? undefined}
                alt={alt}
                onLoad={onImageLoad}
                onError={onImageError}
                data-testid="evidence-preview-image"
                sx={{
                  display: 'block',
                  width: '100%',
                  maxWidth: '100%',
                  height: '100%',
                  maxHeight: layout.maxHeight,
                  objectFit: 'contain',
                  objectPosition: 'center',
                }}
              />
            </Box>
            {onOpenFullscreen ? (
              <IconButton
                size="small"
                onClick={onOpenFullscreen}
                disabled={!canOpenFullscreen}
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
            ) : null}
          </>
        ) : null}
      </Box>

      {showMeta ? (
        <Box sx={{ px: 2, py: 1.5 }}>
          <Typography variant="body2" fontWeight={600} noWrap title={fileName ?? undefined}>
            {fileName || t('results.evidence_viewer.subtitle_fallback')}
          </Typography>
          {label ? (
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>
              {label}
            </Typography>
          ) : null}
          {onOpenFullscreen ? (
            <Button
              variant="outlined"
              size="small"
              onClick={onOpenFullscreen}
              disabled={!canOpenFullscreen && !loading}
              data-testid="result-evidence-open-fullscreen"
              sx={{ mt: 1.25, textTransform: 'none' }}
            >
              {t('results.evidence_viewer.open_fullscreen')}
            </Button>
          ) : null}
        </Box>
      ) : null}
    </Box>
  );
}
