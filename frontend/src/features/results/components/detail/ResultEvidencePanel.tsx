/**
 * Epic 4 — Evidence panel for Result Detail.
 * Phase 6: Primary vs supporting evidence clearly labeled for operator hierarchy.
 * Phase 4.8: Display image only when backend structural evidenceView.displayable is true
 * and use backend-provided imageUrl (no legacy asset loader when evidenceView exists).
 */

import { useState, useCallback, useMemo, useEffect } from 'react';
import { Paper, Typography, Box, Button } from '@mui/material';
import { useTranslation } from 'react-i18next';
import BaseDialog from '../../../../components/ui/BaseDialog';
import type { ResultDetail } from '../../types';
import { useEvidenceImageLoad } from '../../hooks/useEvidenceImageLoad';
import {
  isEvidenceDisplayable,
  resolveStructuralEvidenceImageUrl,
} from '../../utils/evidenceEligibility';
import { evidenceUnavailableMessage } from '../../utils/evidenceUnavailableMessage';
import ResultEvidenceDetails from './ResultEvidenceDetails';

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

  const structuralView = result.evidenceView;
  const evidenceIsDisplayable = isEvidenceDisplayable(
    result.traceabilityStatus,
    result.hasValidEvidence,
    result.sourceImageId,
    structuralView
  );
  const structuralImageUrl = resolveStructuralEvidenceImageUrl(structuralView);
  const usesStructuralContract = structuralView != null;

  const sourceImageId =
    result.sourceImageId != null && String(result.sourceImageId).trim() !== ''
      ? result.sourceImageId.trim()
      : null;

  const canShowStructuralImage = evidenceIsDisplayable && structuralImageUrl != null;
  const canShowLegacyImage =
    !usesStructuralContract &&
    evidenceIsDisplayable &&
    Boolean(inventoryId && aisleId && sourceImageId);

  const canShowImage = canShowStructuralImage || canShowLegacyImage;

  useEffect(() => {
    if (!canShowImage) {
      setDialogOpen(false);
    }
  }, [canShowImage]);

  const jobId = (() => {
    const entityId = result.technicalMetadata?.entityId;
    if (!entityId || typeof entityId !== 'string') return null;
    const idx = entityId.lastIndexOf('_');
    return idx > 0 ? entityId.slice(0, idx) : null;
  })();

  const legacyImageSpec = useMemo(
    () =>
      canShowLegacyImage && inventoryId && aisleId && sourceImageId
        ? { inventoryId, aisleId, assetId: sourceImageId, jobId }
        : null,
    [canShowLegacyImage, inventoryId, aisleId, sourceImageId, jobId]
  );
  const legacyLoadState = useEvidenceImageLoad(legacyImageSpec);

  const imageSrc = canShowStructuralImage
    ? structuralImageUrl
    : legacyLoadState.status === 'loaded'
      ? legacyLoadState.imageSrc
      : null;

  const imageLoading = !canShowStructuralImage && legacyLoadState.status === 'loading';
  const imageError =
    !canShowStructuralImage && legacyLoadState.status === 'error' ? legacyLoadState.message : null;

  const handleOpenImage = useCallback(() => setDialogOpen(true), []);
  const handleCloseImage = useCallback(() => setDialogOpen(false), []);

  const primaryEvidence = result.evidence.find((e) => e.role === 'PRIMARY');
  const supportingEvidence = result.evidence.filter((e) => e.role === 'SUPPORTING');
  const hasCropRecords = result.evidence.length > 0;
  const showUnavailableState = !evidenceIsDisplayable || (evidenceIsDisplayable && !imageSrc && !imageLoading);

  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Typography variant="subtitle1" sx={{ mb: 1.5, fontWeight: 600 }}>
        {t('results.evidence_panel.heading')}
      </Typography>

      {showUnavailableState && !hasCropRecords && (
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
            {evidenceIsDisplayable && usesStructuralContract && structuralImageUrl == null
              ? t('results.evidence_viewer.url_unavailable')
              : evidenceUnavailableMessage(result.traceabilityStatus, t)}
          </Typography>
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
            {imageLoading && (
              <Typography color="text.secondary" sx={{ p: 2 }}>
                {t('common.loading')}
              </Typography>
            )}
            {imageSrc && (
              <img
                src={imageSrc}
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
            {imageError && (
              <Typography color="error" sx={{ p: 2 }} role="alert">
                {imageError}
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
            disabled={!imageSrc}
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

      {showUnavailableState && hasCropRecords && (
        <Box sx={{ py: 2 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {evidenceIsDisplayable && usesStructuralContract && structuralImageUrl == null
              ? t('results.evidence_viewer.url_unavailable')
              : evidenceUnavailableMessage(result.traceabilityStatus, t)}
          </Typography>
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
        {imageSrc && (
          <img
            src={imageSrc}
            alt={t('results.evidence_panel.dialog_alt')}
            style={{ maxWidth: '100%', height: 'auto', display: 'block' }}
          />
        )}
        {imageError && <Typography color="error">{imageError}</Typography>}
        {imageLoading && (
          <Typography color="text.secondary">{t('common.loading')}</Typography>
        )}
      </BaseDialog>

      <ResultEvidenceDetails
        evidenceView={result.evidenceView}
        artifactStatus={result.traceabilityArtifact?.status ?? null}
        artifactHash={result.traceabilityArtifact?.contentHash ?? null}
      />
    </Paper>
  );
}
