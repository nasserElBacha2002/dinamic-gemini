/**
 * Sprint 4.3 — Evidence viewer: main image anchor, zoom, fullscreen, multi-image selection (label chips).
 * Auth-loaded images use useEvidenceImageLoad; switching images selects which URL to load.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  IconButton,
  Tooltip,
  Typography,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import CloseIcon from '@mui/icons-material/Close';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import ZoomOutIcon from '@mui/icons-material/ZoomOut';
import type { ResultDetail } from '../../types';
import { getReferenceImageFileUrl } from '../../../../api/client';
import { useEvidenceImageLoad } from '../../hooks/useEvidenceImageLoad';

export interface ResultEvidenceViewerProps {
  result: ResultDetail;
  inventoryId: string;
  aisleId: string;
}

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2.5;
const ZOOM_STEP = 0.25;

interface EvidenceFrame {
  key: string;
  label: string;
  fileName: string | null;
  imageUrl: string;
}

/** Desktop stage: stable minimum height without cropping; max avoids awkward vertical dominance. */
const STAGE_MIN_HEIGHT = { xs: 300, sm: 360, md: 480 } as const;
const STAGE_MAX_HEIGHT = { xs: '56vh', md: 'min(72vh, 720px)' } as const;

function jobIdFromResult(result: ResultDetail): string | null {
  const entityId = result.technicalMetadata?.entityId;
  if (!entityId || typeof entityId !== 'string') return null;
  const idx = entityId.lastIndexOf('_');
  return idx > 0 ? entityId.slice(0, idx) : null;
}

function buildFrames(result: ResultDetail, inventoryId: string, aisleId: string): EvidenceFrame[] {
  const jobId = jobIdFromResult(result);
  const seen = new Set<string>();
  const drafts: Array<{ key: string; fileName: string | null; imageUrl: string }> = [];

  const push = (assetId: string | null | undefined, fileName: string | null) => {
    const id = assetId != null ? String(assetId).trim() : '';
    if (!id || seen.has(id)) return;
    seen.add(id);
    drafts.push({
      key: id,
      fileName,
      imageUrl: getReferenceImageFileUrl(inventoryId, aisleId, id, jobId),
    });
  };

  push(result.sourceImageId, result.sourceFileName);
  result.evidence.forEach((ev) => {
    push(ev.sourceImageId, ev.sourceFileName);
  });

  return drafts.map((d, idx) => ({
    ...d,
    label: idx === 0 ? 'Primary' : `View ${idx + 1}`,
  }));
}

export default function ResultEvidenceViewer({ result, inventoryId, aisleId }: ResultEvidenceViewerProps) {
  const frames = useMemo(
    () => buildFrames(result, inventoryId, aisleId),
    [result, inventoryId, aisleId]
  );
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);

  const safeIndex = Math.min(selectedIndex, Math.max(0, frames.length - 1));
  const currentUrl = frames[safeIndex]?.imageUrl ?? null;
  const loadState = useEvidenceImageLoad(currentUrl);

  useEffect(() => {
    setSelectedIndex((i) => Math.min(i, Math.max(0, frames.length - 1)));
  }, [frames.length]);

  useEffect(() => {
    if (!fullscreenOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setFullscreenOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [fullscreenOpen]);

  const onZoomOut = useCallback(() => {
    setZoom((z) => Math.max(ZOOM_MIN, Math.round((z - ZOOM_STEP) * 100) / 100));
  }, []);
  const onZoomIn = useCallback(() => {
    setZoom((z) => Math.min(ZOOM_MAX, Math.round((z + ZOOM_STEP) * 100) / 100));
  }, []);

  const hasRecordOnly =
    result.evidence.length > 0 && frames.length === 0;

  return (
    <Box
      sx={{
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        bgcolor: 'background.paper',
        p: 2,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        minHeight: { xs: 320, md: 520 },
      }}
    >
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1.5 }}>
        Evidence
      </Typography>

      {frames.length === 0 && !hasRecordOnly && (
        <Box
          sx={{
            py: 4,
            px: 2,
            textAlign: 'center',
            bgcolor: 'action.hover',
            borderRadius: 1,
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Typography color="text.secondary">No image evidence available for this result.</Typography>
        </Box>
      )}

      {hasRecordOnly && (
        <Box sx={{ py: 3, px: 2, bgcolor: 'action.hover', borderRadius: 1, flex: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Evidence is recorded for this result, but no image is available to display here. Use{' '}
            <strong>Technical metadata</strong> below if you need internal reference fields.
          </Typography>
        </Box>
      )}

      {frames.length > 0 && (
        <>
          {frames.length > 1 && (
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 1.5, alignItems: 'center' }}>
              <Typography variant="caption" color="text.secondary" sx={{ width: '100%', mb: -0.25 }}>
                Evidence image ({frames.length})
              </Typography>
              {frames.map((f, i) => (
                <Button
                  key={f.key}
                  size="small"
                  variant={i === safeIndex ? 'contained' : 'outlined'}
                  color={i === safeIndex ? 'primary' : 'inherit'}
                  onClick={() => {
                    setSelectedIndex(i);
                    setZoom(1);
                  }}
                  aria-label={`Show ${f.label}${f.fileName ? `: ${f.fileName}` : ''}`}
                  aria-pressed={i === safeIndex}
                  sx={{ textTransform: 'none', py: 0.25, minWidth: 0 }}
                >
                  {f.label}
                </Button>
              ))}
            </Box>
          )}

          <Box
            sx={{
              flex: 1,
              minHeight: STAGE_MIN_HEIGHT,
              maxHeight: STAGE_MAX_HEIGHT,
              bgcolor: 'grey.100',
              borderRadius: 1,
              overflow: 'auto',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              position: 'relative',
            }}
          >
            {loadState.status === 'loading' && (
              <Box sx={{ py: 6 }}>
                <CircularProgress size={36} />
              </Box>
            )}
            {loadState.status === 'loaded' && (
              <Box
                component="img"
                src={loadState.blobUrl}
                alt={frames[safeIndex]?.fileName ? `Evidence: ${frames[safeIndex].fileName}` : 'Evidence image'}
                sx={{
                  maxWidth: '100%',
                  display: 'block',
                  objectFit: 'contain',
                  transform: `scale(${zoom})`,
                  transformOrigin: 'center center',
                  transition: 'transform 0.15s ease-out',
                }}
              />
            )}
            {loadState.status === 'error' && (
              <Typography color="error" role="alert" sx={{ p: 2 }}>
                {loadState.message}
              </Typography>
            )}
            {loadState.status === 'idle' && null}
          </Box>

          {(frames[safeIndex]?.fileName || frames[safeIndex]?.label) && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }} noWrap title={frames[safeIndex]?.fileName ?? undefined}>
              {frames[safeIndex]?.fileName ?? frames[safeIndex]?.label}
            </Typography>
          )}

          <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 0.5, mt: 1.5 }}>
            <Tooltip title="Zoom out">
              <span>
                <IconButton
                  size="small"
                  onClick={onZoomOut}
                  disabled={loadState.status !== 'loaded' || zoom <= ZOOM_MIN}
                  aria-label="Zoom out"
                >
                  <ZoomOutIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title="Zoom in">
              <span>
                <IconButton size="small" onClick={onZoomIn} disabled={loadState.status !== 'loaded' || zoom >= ZOOM_MAX} aria-label="Zoom in">
                  <ZoomInIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <Typography variant="caption" color="text.secondary" sx={{ mx: 0.5 }}>
              {Math.round(zoom * 100)}%
            </Typography>
            <Button
              size="small"
              variant="outlined"
              startIcon={<FullscreenIcon fontSize="small" />}
              onClick={() => setFullscreenOpen(true)}
              disabled={loadState.status !== 'loaded'}
              aria-label="Open fullscreen"
            >
              Fullscreen
            </Button>
          </Box>

          <Dialog
            open={fullscreenOpen}
            onClose={() => setFullscreenOpen(false)}
            maxWidth={false}
            fullWidth
            fullScreen
            aria-labelledby="evidence-fullscreen-title"
          >
            <Box
              sx={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                bgcolor: 'grey.900',
                color: 'common.white',
              }}
            >
              <Box
                sx={{
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  px: 1,
                  py: 0.5,
                  borderBottom: 1,
                  borderColor: (theme) => alpha(theme.palette.common.white, 0.12),
                }}
              >
                <Typography
                  id="evidence-fullscreen-title"
                  variant="caption"
                  sx={{
                    flex: 1,
                    minWidth: 0,
                    color: 'grey.400',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                  title={
                    frames[safeIndex]?.fileName
                      ? `${frames[safeIndex].label} · ${frames[safeIndex].fileName}`
                      : frames[safeIndex]?.label
                  }
                >
                  {frames[safeIndex]?.fileName
                    ? `${frames[safeIndex].label} · ${frames[safeIndex].fileName}`
                    : frames[safeIndex]?.label ?? 'Evidence'}
                </Typography>
                <Tooltip title="Exit fullscreen (Esc)">
                  <IconButton
                    color="inherit"
                    onClick={() => setFullscreenOpen(false)}
                    aria-label="Exit fullscreen"
                    edge="end"
                    size="small"
                  >
                    <CloseIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
              <DialogContent
                sx={{
                  flex: 1,
                  minHeight: 0,
                  p: 2,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  overflow: 'auto',
                  bgcolor: 'grey.900',
                }}
              >
                {loadState.status === 'loaded' && (
                  <Box
                    component="img"
                    src={loadState.blobUrl}
                    alt={
                      frames[safeIndex]?.fileName
                        ? `Evidence: ${frames[safeIndex].fileName}`
                        : 'Evidence fullscreen'
                    }
                    sx={{
                      maxWidth: '100%',
                      maxHeight: '100%',
                      objectFit: 'contain',
                    }}
                  />
                )}
              </DialogContent>
              <DialogActions
                sx={{
                  flexShrink: 0,
                  bgcolor: 'grey.900',
                  borderTop: 1,
                  borderColor: (theme) => alpha(theme.palette.common.white, 0.12),
                }}
              >
                <Typography variant="caption" sx={{ flex: 1, pl: 1, color: 'grey.500' }}>
                  Esc to close
                </Typography>
                <Button onClick={() => setFullscreenOpen(false)} color="inherit" size="small">
                  Close
                </Button>
              </DialogActions>
            </Box>
          </Dialog>
        </>
      )}
    </Box>
  );
}
