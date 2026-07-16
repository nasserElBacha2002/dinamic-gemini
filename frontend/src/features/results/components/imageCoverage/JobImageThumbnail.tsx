/**
 * Job image coverage — authenticated thumbnail for one source asset.
 * Reuses the same authenticated image-display-url + blob fallback as evidence viewers.
 */

import { Box, CircularProgress, Typography } from '@mui/material';
import BrokenImageOutlinedIcon from '@mui/icons-material/BrokenImageOutlined';
import { useEvidenceImageLoad } from '../../hooks/useEvidenceImageLoad';

export interface JobImageThumbnailProps {
  inventoryId: string;
  aisleId: string;
  sourceAssetId: string;
  jobId: string;
  alt: string;
  size?: number;
}

export default function JobImageThumbnail({
  inventoryId,
  aisleId,
  sourceAssetId,
  jobId,
  alt,
  size = 96,
}: JobImageThumbnailProps) {
  const loadState = useEvidenceImageLoad({
    inventoryId,
    aisleId,
    assetId: sourceAssetId,
    jobId,
  });

  return (
    <Box
      sx={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: 1,
        overflow: 'hidden',
        bgcolor: 'grey.900',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        border: '1px solid',
        borderColor: 'divider',
      }}
    >
      {loadState.status === 'loading' ? <CircularProgress size={20} sx={{ color: 'grey.400' }} /> : null}
      {loadState.status === 'error' ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.5, px: 0.5 }}>
          <BrokenImageOutlinedIcon fontSize="small" sx={{ color: 'grey.500' }} />
        </Box>
      ) : null}
      {loadState.status === 'loaded' ? (
        <Box
          component="img"
          src={loadState.imageSrc}
          alt={alt}
          sx={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
        />
      ) : null}
      {loadState.status === 'idle' ? (
        <Typography variant="caption" color="text.secondary">
          —
        </Typography>
      ) : null}
    </Box>
  );
}
