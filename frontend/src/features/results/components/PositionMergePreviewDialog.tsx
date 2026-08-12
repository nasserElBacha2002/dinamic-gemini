/**
 * Compact ANTES → DESPUÉS dialog for operator position merge preview.
 */

import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Divider,
  Stack,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { BaseDialog } from '../../../components/ui';
import type { PositionMergePreviewResponse } from '../../../api/types';

export interface PositionMergePreviewDialogProps {
  open: boolean;
  preview: PositionMergePreviewResponse | null;
  loading: boolean;
  confirming: boolean;
  errorMessage: string | null;
  onClose: () => void;
  onConfirm: () => void;
}

function SourceCard({
  sku,
  quantity,
  positionCode,
  filename,
  internalCode,
}: {
  sku: string | null | undefined;
  quantity: number;
  positionCode: string | null | undefined;
  filename: string | null | undefined;
  internalCode: string | null | undefined;
}) {
  const { t } = useTranslation();
  const dash = t('common.em_dash');
  return (
    <Box
      sx={{
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        px: 1.25,
        py: 1,
      }}
      data-testid="position-merge-source-card"
    >
      <Typography variant="subtitle2" sx={{ fontFamily: 'ui-monospace, monospace' }}>
        {sku?.trim() || dash}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {t('positions.merge_preview_qty', { count: quantity })}
      </Typography>
      {positionCode ? (
        <Typography variant="body2" color="text.secondary">
          {t('positions.merge_preview_position', { code: positionCode })}
        </Typography>
      ) : null}
      {internalCode && internalCode !== sku ? (
        <Typography variant="caption" color="text.secondary" display="block">
          {t('positions.merge_preview_internal', { code: internalCode })}
        </Typography>
      ) : null}
      {filename ? (
        <Typography variant="caption" color="text.secondary" display="block">
          {t('positions.merge_preview_photo', { name: filename })}
        </Typography>
      ) : null}
    </Box>
  );
}

export default function PositionMergePreviewDialog({
  open,
  preview,
  loading,
  confirming,
  errorMessage,
  onClose,
  onConfirm,
}: PositionMergePreviewDialogProps) {
  const { t } = useTranslation();
  const canMerge = Boolean(preview?.can_merge);
  const sourceCount = preview?.sources.length ?? 0;

  return (
    <BaseDialog
      open={open}
      onClose={onClose}
      disableClose={confirming}
      title={t('positions.merge_preview_title')}
      maxWidth="sm"
      fullWidth
      error={errorMessage}
      actions={
        <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ width: '100%' }}>
          <Button onClick={onClose} disabled={confirming} data-testid="position-merge-cancel">
            {canMerge ? t('common.cancel') : t('common.close')}
          </Button>
          {canMerge ? (
            <Button
              variant="contained"
              onClick={onConfirm}
              disabled={loading || confirming || !preview}
              data-testid="position-merge-confirm"
            >
              {confirming ? (
                <CircularProgress size={18} color="inherit" />
              ) : (
                t('positions.merge_confirm_n', { count: sourceCount })
              )}
            </Button>
          ) : null}
        </Stack>
      }
    >
      <Box data-testid="position-merge-preview-dialog">
      {loading && !preview ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress size={28} data-testid="position-merge-preview-loading" />
        </Box>
      ) : null}

      {preview ? (
        <Stack spacing={2}>
          {preview.conflicts.length > 0 ? (
            <Alert severity="error" data-testid="position-merge-conflicts">
              <Stack spacing={0.5}>
                {preview.conflicts.map((c) => (
                  <Box key={c.code}>
                    <Typography variant="body2">{c.message}</Typography>
                    {c.values.length > 0 ? (
                      <Typography variant="caption" component="div">
                        {c.values.map((v) => (
                          <div key={v}>- {v}</div>
                        ))}
                      </Typography>
                    ) : null}
                  </Box>
                ))}
              </Stack>
            </Alert>
          ) : null}

          {preview.warnings.length > 0 ? (
            <Alert severity="warning" data-testid="position-merge-warnings">
              <Stack spacing={0.5}>
                {preview.warnings.map((w) => (
                  <Box key={w.code}>
                    <Typography variant="body2">{w.message}</Typography>
                    {w.values.length > 0 && w.values.length <= 6 ? (
                      <Typography variant="caption" component="div" color="text.secondary">
                        {w.values.map((v) => (
                          <div key={v}>- {v}</div>
                        ))}
                      </Typography>
                    ) : null}
                  </Box>
                ))}
              </Stack>
            </Alert>
          ) : null}

          <Box>
            <Typography variant="overline" color="text.secondary">
              {t('positions.merge_preview_before')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {t('positions.merge_preview_before_count', { count: preview.sources.length })}
            </Typography>
            <Stack spacing={1}>
              {preview.sources.map((s) => (
                <SourceCard
                  key={s.position_id}
                  sku={s.sku}
                  quantity={s.quantity}
                  positionCode={s.position_code}
                  filename={s.source_image_filename}
                  internalCode={s.internal_code}
                />
              ))}
            </Stack>
          </Box>

          <Divider>
            <Typography variant="caption" color="text.secondary">
              {t('positions.merge_preview_arrow')}
            </Typography>
          </Divider>

          <Box data-testid="position-merge-after">
            <Typography variant="overline" color="text.secondary">
              {t('positions.merge_preview_after')}
            </Typography>
            <Box
              sx={{
                border: 1,
                borderColor: 'primary.main',
                borderRadius: 1,
                px: 1.5,
                py: 1.25,
                mt: 0.5,
              }}
            >
              <Typography variant="subtitle1" sx={{ fontFamily: 'ui-monospace, monospace' }}>
                {preview.merged_result.sku?.trim() || t('common.em_dash')}
              </Typography>
              <Typography variant="body2">
                {t('positions.merge_preview_qty', {
                  count: preview.merged_result.quantity ?? 0,
                })}
              </Typography>
              {preview.merged_result.position_code ? (
                <Typography variant="body2" color="text.secondary">
                  {t('positions.merge_preview_position', {
                    code: preview.merged_result.position_code,
                  })}
                </Typography>
              ) : null}
              <Typography variant="body2" color="text.secondary">
                {t('positions.merge_preview_detections', {
                  count: preview.merged_result.source_count,
                })}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('positions.merge_preview_images', {
                  count: preview.merged_result.image_count,
                })}
              </Typography>
            </Box>
          </Box>
        </Stack>
      ) : null}
      </Box>
    </BaseDialog>
  );
}
