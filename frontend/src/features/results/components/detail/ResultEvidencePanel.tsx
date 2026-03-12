/**
 * Epic 4 — Evidence panel for Result Detail.
 *
 * Semantics:
 * - Source image preview: when result.sourceImageId + inventory/aisle are available we show the
 *   reference image (asset file) and optional source file name. This is the main visual evidence.
 * - Evidence metadata only: when evidence records exist but no source image URL can be built,
 *   we show a short message that evidence is recorded but preview is not available.
 * - No evidence: when there is no source image and no evidence records, we show an intentional
 *   "No evidence available" state.
 */

import { useState, useCallback } from 'react';
import { Paper, Typography, Box, Button, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import type { ResultDetail } from '../../types';
import { getReferenceImageFileUrl } from '../../../../api/client';

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
  const [imageError, setImageError] = useState(false);

  const sourceImageId =
    result.sourceImageId != null && String(result.sourceImageId).trim() !== ''
      ? result.sourceImageId.trim()
      : null;
  const canShowImage = Boolean(
    sourceImageId && inventoryId && aisleId
  );
  const imageUrl = canShowImage
    ? getReferenceImageFileUrl(inventoryId!, aisleId!, sourceImageId!)
    : null;

  const handleOpenImage = useCallback(() => {
    setImageError(false);
    setDialogOpen(true);
  }, []);
  const handleCloseImage = useCallback(() => {
    setDialogOpen(false);
    setImageError(false);
  }, []);

  const primaryEvidence = result.evidence.find((e) => e.role === 'PRIMARY');
  const supportingEvidence = result.evidence.filter((e) => e.role === 'SUPPORTING');
  const hasAnyEvidence = result.evidence.length > 0 || canShowImage;

  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Typography variant="subtitle1" sx={{ mb: 1.5, fontWeight: 600 }}>
        Evidence
      </Typography>

      {/* No evidence: no source image and no evidence records. */}
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

      {/* Source image preview: show reference image when sourceImageId + route context available. */}
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
            {imageUrl ? (
              <img
                src={imageUrl}
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
                onError={() => setImageError(true)}
              />
            ) : null}
            {imageError && (
              <Typography color="error" sx={{ p: 2 }}>
                Image could not be loaded.
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
          >
            View full image
          </Button>
        </Box>
      )}

      {/* Evidence metadata only: records exist but no source image URL can be built. */}
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
          {imageError ? (
            <Typography color="error">
              Image not available. It may have been removed or the file is missing.
            </Typography>
          ) : (
            imageUrl && (
              <img
                src={dialogOpen ? imageUrl : ''}
                alt="Source image"
                style={{ maxWidth: '100%', height: 'auto', display: 'block' }}
                onError={() => setImageError(true)}
              />
            )
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseImage}>Close</Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
