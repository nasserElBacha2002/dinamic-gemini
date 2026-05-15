/**
 * Epic 4 — Evidence panel for Result Detail.
 * Phase 6: Primary vs supporting evidence clearly labeled for operator hierarchy.
 */

import { useState, useCallback, useMemo } from 'react';
import { Paper, Typography, Box, Button, CircularProgress } from '@mui/material';
import { useTranslation } from 'react-i18next';
import BaseDialog from '../../../../components/ui/BaseDialog';
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
  const { t } = useTranslation();
  const [dialogOpen, setDialogOpen] = useState(false);

  const sourceImageId =
    result.sourceImageId != null && String(result.sourceImageId).trim() !== ''
      ? result.sourceImageId.trim()
      : null;
  const canShowImage = Boolean(sourceImageId && inventoryId && aisleId);
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
        {t('results.evidence_panel.heading')}
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
          <Typography color="text.secondary">{t('results.evidence_panel.none')}</Typography>
        </Box>
      )}

      {canShowImage && (
        <Box>
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
            {t('results.evidence_panel.primary_heading')}
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
                    ? t('results.evidence_panel.alt_source_named', { fileName: result.sourceFileName })
                    : t('results.evidence_panel.alt_source_generic')
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
              {t('results.evidence_panel.source_file', { name: result.sourceFileName })}
            </Typography>
          )}
          <Button
            size="small"
            variant="outlined"
            onClick={handleOpenImage}
            sx={{ mt: 1 }}
            aria-label={t('results.view_full_image')}
            disabled={loadState.status !== 'loaded'}
          >
            {t('results.view_full_image')}
          </Button>
          {supportingEvidence.length > 0 && (
            <>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 2, mb: 0.5 }}>
                {t('results.evidence_panel.supporting_heading')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('results.evidence_panel.supporting_count', { count: supportingEvidence.length })}
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
                {t('results.evidence_panel.primary_heading')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('results.evidence_panel.recorded_no_preview')}
              </Typography>
            </>
          )}
          {supportingEvidence.length > 0 && (
            <>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1.5, mb: 0.5 }}>
                {t('results.evidence_panel.supporting_heading')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('results.evidence_panel.supporting_count', { count: supportingEvidence.length })}
              </Typography>
            </>
          )}
        </Box>
      )}

      <BaseDialog
        open={dialogOpen}
        onClose={handleCloseImage}
        maxWidth="md"
        fullWidth
        title={t('results.evidence_panel.dialog_title')}
        actions={<Button onClick={handleCloseImage}>{t('common.close')}</Button>}
      >
        {loadState.status === 'loaded' && (
          <img
            src={loadState.imageSrc}
            alt={t('results.evidence_panel.dialog_alt')}
            style={{ maxWidth: '100%', height: 'auto', display: 'block' }}
          />
        )}
        {loadState.status === 'error' && <Typography color="error">{loadState.message}</Typography>}
        {loadState.status === 'loading' && (
          <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}>
            <CircularProgress />
          </Box>
        )}
        {loadState.status === 'idle' && null}
      </BaseDialog>
    </Paper>
  );
}
