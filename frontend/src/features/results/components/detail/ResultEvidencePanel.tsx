/**
 * Epic 4 — Evidence panel for Result Detail.
 *
 * Semantics:
 * - Source image preview: when result.sourceImageId + inventory/aisle are available we load the
 *   reference image via fetch (with auth) and show blob URL or a differentiated error state.
 * - Evidence metadata only: when evidence records exist but no source image URL can be built,
 *   we show a short message that evidence is recorded but preview is not available.
 * - No evidence: when there is no source image and no evidence records, we show an intentional
 *   "No evidence available" state.
 *
 * Error differentiation: 404 not_found, 403/401 forbidden, HEIC preview missing, network/unknown.
 */

import { useState, useCallback } from 'react';
import { Paper, Typography, Box, Button, Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress } from '@mui/material';
import type { ResultDetail } from '../../types';
import { getReferenceImageFileUrl } from '../../../../api/client';
import { useEvidenceImageLoad } from '../../hooks/useEvidenceImageLoad';

export interface ResultEvidencePanelProps {
  result: ResultDetail;
  inventoryId: string | undefined;
  aisleId: string | undefined;
}

export default function ResultEvidencePanel({
  result,
  inventoryId,
  aisleId,
}: ResultEvidencePanelProps) {
  const [dialogOpen, setDialogOpen] = useState(false);

  const sourceImageId =
    result.sourceImageId != null && String(result.sourceImageId).trim() !== ''
      ? result.sourceImageId.trim()
      : null;
  const canShowImage = Boolean(
    sourceImageId && inventoryId && aisleId
  );
  const jobId = (() => {
    const entityId = result.technicalMetadata?.entityId;
    if (!entityId || typeof entityId !== 'string') return null;
    const idx = entityId.lastIndexOf('_');
    return idx > 0 ? entityId.slice(0, idx) : null;
  })();
  const imageUrl = canShowImage
    ? getReferenceImageFileUrl(inventoryId!, aisleId!, sourceImageId!, jobId)
    : null;
  const loadState = useEvidenceImageLoad(canShowImage ? imageUrl : null);

  const handleOpenImage = useCallback(() => setDialogOpen(true), []);
  const handleCloseImage = useCallback(() => setDialogOpen(false), []);

  const primaryEvidence = result.evidence.find((e) => e.role === 'PRIMARY');
  const supportingEvidence = result.evidence.filter((e) => e.role === 'SUPPORTING');
  const hasAnyEvidence = result.evidence.length > 0 || canShowImage;

  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Typography variant="subtitle1" sx={{ mb: 1.5, fontWeight: 600 }}>
        Evidence
      </Typography>

      {!hasAnyEvidence && !canShowImage && (
        <Box
          sx={{
            py: 3,
            px: 2,
            textAlign: 'center',
            bgcolor: 'action.hover',
            borderRadius: 1,
          }}
        >
          <Typography color="text.secondary">
            No evidence available for this result.
          </Typography>
        </Box>
      )}

      {canShowImage && (
        <Box>
          <Box
            sx={{
              bgcolor: 'grey.100',
              borderRadius: 1,
              overflow: 'hidden',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: 200,
              position: 'relative',
            }}
          >
            {loadState.status === 'idle' && null}
            {loadState.status === 'loading' && (
              <Box sx={{ py: 4 }}>
                <CircularProgress size={32} />
              </Box>
            )}
            {loadState.status === 'loaded' && (
              <img
                src={loadState.blobUrl}
                alt={
                  result.sourceFileName
                    ? `Source: ${result.sourceFileName}`
                    : 'Source image for this result'
                }
                style={{
                  maxWidth: '100%',
                  maxHeight: 320,
                  objectFit: 'contain',
                }}
              />
            )}
            {loadState.status === 'error' && (
              <Typography color="error" sx={{ p: 2 }} role="alert">
                {loadState.message}
              </Typography>
            )}
          </Box>
          {result.sourceFileName && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Source file: {result.sourceFileName}
            </Typography>
          )}
          <Button
            size="small"
            variant="outlined"
            onClick={handleOpenImage}
            sx={{ mt: 1 }}
            aria-label="View full image"
            disabled={loadState.status !== 'loaded'}
          >
            View full image
          </Button>
        </Box>
      )}

      {!canShowImage && hasAnyEvidence && (
        <Box sx={{ py: 2 }}>
          <Typography variant="body2" color="text.secondary">
            {primaryEvidence && 'Primary evidence recorded.'}
            {supportingEvidence.length > 0 &&
              ` ${supportingEvidence.length} supporting item(s).`}
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            Image preview is not available for this result.
          </Typography>
        </Box>
      )}

      <Dialog open={dialogOpen} onClose={handleCloseImage} maxWidth="md" fullWidth>
        <DialogTitle>Source image</DialogTitle>
        <DialogContent>
          {loadState.status === 'loaded' && (
            <img
              src={loadState.blobUrl}
              alt="Source image"
              style={{ maxWidth: '100%', height: 'auto', display: 'block' }}
            />
          )}
          {loadState.status === 'error' && (
            <Typography color="error">{loadState.message}</Typography>
          )}
          {loadState.status === 'loading' && (
            <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}>
              <CircularProgress />
            </Box>
          )}
          {loadState.status === 'idle' && null}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseImage}>Close</Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
