/**
 * Epic 4 — Evidence panel for Result Detail.
 * Phase 6: Primary vs supporting evidence clearly labeled for operator hierarchy.
 *
 * Semantics:
 * - Primary evidence: source image (when available) or primary evidence record; labeled "Primary evidence".
 * - Supporting evidence: all other evidence; labeled "Supporting evidence".
 * - No evidence: intentional "No evidence available" state.
 */

import { useState, useCallback, useMemo } from 'react';
import { Paper, Typography, Box, Button, Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress } from '@mui/material';
import type { ResultDetail } from '../../types';
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
  const imageSpec = useMemo(
    () =>
      canShowImage && inventoryId && aisleId && sourceImageId
        ? { inventoryId, aisleId, assetId: sourceImageId, jobId }
        : null,
    [canShowImage, inventoryId, aisleId, sourceImageId, jobId]
  );
  const loadState = useEvidenceImageLoad(imageSpec);

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
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
            Primary evidence
          </Typography>
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
                src={loadState.imageSrc}
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
          {supportingEvidence.length > 0 && (
            <>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 2, mb: 0.5 }}>
                Supporting evidence
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {supportingEvidence.length} supporting item(s).
              </Typography>
            </>
          )}
        </Box>
      )}

      {!canShowImage && hasAnyEvidence && (
        <Box sx={{ py: 2 }}>
          {primaryEvidence && (
            <>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>
                Primary evidence
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Primary evidence recorded. Image preview is not available for this result.
              </Typography>
            </>
          )}
          {supportingEvidence.length > 0 && (
            <>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1.5, mb: 0.5 }}>
                Supporting evidence
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {supportingEvidence.length} supporting item(s).
              </Typography>
            </>
          )}
        </Box>
      )}

      <Dialog open={dialogOpen} onClose={handleCloseImage} maxWidth="md" fullWidth>
        <DialogTitle>Source image</DialogTitle>
        <DialogContent>
          {loadState.status === 'loaded' && (
            <img
              src={loadState.imageSrc}
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
