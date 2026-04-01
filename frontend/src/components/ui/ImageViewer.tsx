import { useCallback, useEffect, useState, ReactNode } from 'react';
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

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2.5;
const ZOOM_STEP = 0.25;

export interface ImageViewerProps {
  src: string | null;
  alt?: string;
  title?: string;
  loading?: boolean;
  error?: string | null;
  caption?: string | ReactNode;
  /** Height configuration for the stage. */
  minHeight?: number | string | Record<string, number | string>;
  maxHeight?: number | string | Record<string, number | string>;
}

/**
 * Shared image viewer foundation (Phase 2 refactor).
 * Provides zoom (transform-scale), fullscreen mode, and loading/error states.
 */
export default function ImageViewer({
  src,
  alt = 'Image',
  title = 'Image viewer',
  loading = false,
  error = null,
  caption,
  minHeight = 300,
  maxHeight = 'min(72vh, 720px)',
}: ImageViewerProps) {
  const [zoom, setZoom] = useState(1);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);

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

  /** Reset zoom when image source changes. */
  useEffect(() => {
    setZoom(1);
  }, [src]);

  const onZoomOut = useCallback(() => {
    setZoom((z) => Math.max(ZOOM_MIN, Math.round((z - ZOOM_STEP) * 100) / 100));
  }, []);
  const onZoomIn = useCallback(() => {
    setZoom((z) => Math.min(ZOOM_MAX, Math.round((z + ZOOM_STEP) * 100) / 100));
  }, []);

  const isLoaded = !loading && !error && Boolean(src);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minWidth: 0 }}>
      {/* Stage Area */}
      <Box
        sx={{
          flex: 1,
          minHeight,
          maxHeight,
          bgcolor: 'grey.100',
          borderRadius: 1,
          overflow: 'auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          position: 'relative',
        }}
      >
        {loading && (
          <Box sx={{ py: 6 }}>
            <CircularProgress size={36} />
          </Box>
        )}
        {isLoaded && (
          <Box
            component="img"
            src={src!}
            alt={alt}
            sx={{
              maxWidth: '100%',
              maxHeight: '100%',
              display: 'block',
              objectFit: 'contain',
              transform: `scale(${zoom})`,
              transformOrigin: 'center center',
              transition: 'transform 0.15s ease-out',
            }}
          />
        )}
        {error && (
          <Typography color="error" role="alert" sx={{ p: 2, textAlign: 'center' }}>
            {error}
          </Typography>
        )}
        {!loading && !error && !src && (
          <Typography color="text.secondary" sx={{ p: 2, textAlign: 'center' }}>
            No image available
          </Typography>
        )}
      </Box>

      {/* Metadata / Caption */}
      {caption && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ mt: 1, display: 'block', px: 0.5 }}
          noWrap
          title={typeof caption === 'string' ? caption : undefined}
        >
          {caption}
        </Typography>
      )}

      {/* Interaction Controls */}
      <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 0.5, mt: 1.5 }}>
        <Tooltip title="Zoom out">
          <span>
            <IconButton
              size="small"
              onClick={onZoomOut}
              disabled={!isLoaded || zoom <= ZOOM_MIN}
              aria-label="Zoom out"
            >
              <ZoomOutIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Zoom in">
          <span>
            <IconButton
              size="small"
              onClick={onZoomIn}
              disabled={!isLoaded || zoom >= ZOOM_MAX}
              aria-label="Zoom in"
            >
              <ZoomInIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        <Typography variant="caption" color="text.secondary" sx={{ mx: 0.5, minWidth: '2.5em', textAlign: 'center' }}>
          {Math.round(zoom * 100)}%
        </Typography>
        <Button
          size="small"
          variant="outlined"
          startIcon={<FullscreenIcon fontSize="small" />}
          onClick={() => setFullscreenOpen(true)}
          disabled={!isLoaded}
          aria-label="Open fullscreen"
          sx={{ ml: 1 }}
        >
          Fullscreen
        </Button>
      </Box>

      {/* Fullscreen Dialog */}
      <Dialog
        open={fullscreenOpen}
        onClose={() => setFullscreenOpen(false)}
        maxWidth={false}
        fullWidth
        fullScreen
        aria-labelledby="image-viewer-fullscreen-title"
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
              px: 2,
              py: 1,
              borderBottom: 1,
              borderColor: (theme) => alpha(theme.palette.common.white, 0.12),
            }}
          >
            <Typography
              id="image-viewer-fullscreen-title"
              variant="caption"
              sx={{
                flex: 1,
                minWidth: 0,
                color: 'grey.400',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                fontSize: '0.85rem',
              }}
              title={title}
            >
              {title}
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
            {isLoaded && (
              <Box
                component="img"
                src={src!}
                alt={alt}
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
              px: 2,
              py: 1,
              borderColor: (theme) => alpha(theme.palette.common.white, 0.12),
            }}
          >
            <Typography variant="caption" sx={{ flex: 1, color: 'grey.500' }}>
              Esc to close
            </Typography>
            <Button onClick={() => setFullscreenOpen(false)} color="inherit" size="small">
              Close
            </Button>
          </DialogActions>
        </Box>
      </Dialog>
    </Box>
  );
}
