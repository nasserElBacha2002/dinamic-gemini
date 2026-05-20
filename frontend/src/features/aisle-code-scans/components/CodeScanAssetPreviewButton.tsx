import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
} from '@mui/material';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import { fetchEvidenceImageDisplay } from '../../../api/client';
import { ApiError } from '../../../api/types';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';

export interface CodeScanAssetPreviewButtonProps {
  inventoryId: string;
  aisleId: string;
  assetId: string;
  jobIdForPreview?: string | null;
}

export default function CodeScanAssetPreviewButton({
  inventoryId,
  aisleId,
  assetId,
  jobIdForPreview,
}: CodeScanAssetPreviewButtonProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revoke, setRevoke] = useState<(() => void) | null>(null);

  const handleClose = useCallback(() => {
    setOpen(false);
    revoke?.();
    setRevoke(null);
    setImageSrc(null);
    setError(null);
  }, [revoke]);

  const handleOpen = useCallback(async () => {
    setOpen(true);
    setLoading(true);
    setError(null);
    revoke?.();
    setRevoke(null);
    setImageSrc(null);
    try {
      const res = await fetchEvidenceImageDisplay({
        inventoryId,
        aisleId,
        assetId,
        jobId: jobIdForPreview ?? null,
      });
      if (!res.ok) {
        throw new ApiError(
          res.detail ?? t('errors.preview_aisle_asset_failed'),
          res.status,
          res.detail ? { detail: res.detail } : undefined
        );
      }
      setImageSrc(res.imageSrc);
      setRevoke(() => res.revoke);
    } catch (e) {
      setError(resolveApiErrorMessage(e, 'errors.preview_aisle_asset_failed'));
    } finally {
      setLoading(false);
    }
  }, [aisleId, assetId, inventoryId, jobIdForPreview, revoke, t]);

  return (
    <>
      <Button size="small" variant="text" onClick={() => void handleOpen()}>
        {t('aisleCodeScans.actions.viewImage')}
      </Button>
      <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', pr: 1 }}>
          {t('aisleCodeScans.actions.viewImage')}
          <IconButton
            aria-label={t('aisleCodeScans.actions.close')}
            onClick={handleClose}
            sx={{ ml: 'auto' }}
          >
            <CloseRoundedIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress size={32} />
            </Box>
          ) : null}
          {error ? (
            <Box sx={{ color: 'error.main', py: 2 }} role="alert">
              {error}
            </Box>
          ) : null}
          {imageSrc ? (
            <Box
              component="img"
              src={imageSrc}
              alt={t('aisleCodeScans.actions.viewImage')}
              sx={{ maxWidth: '100%', height: 'auto', display: 'block', mx: 'auto' }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
