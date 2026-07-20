import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { useTranslation } from 'react-i18next';
import type { ReferenceAnnotationPayload } from '../../../api/types';
import { ErrorAlert, LoadingBlock } from '../../../components/ui';
import { useReplaceSupplierReferenceAnnotations, useSupplierReferenceAnnotations } from '../../../hooks';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { SPATIAL_RELATIONS } from '../utils/defaultExtractionProfileConfiguration';

export interface SupplierReferenceAnnotationEditorDialogProps {
  open: boolean;
  onClose: () => void;
  clientId: string;
  supplierId: string;
  imageId: string;
  imageLabel: string;
  activeProfileId?: string | null;
}

type EditableAnnotation = ReferenceAnnotationPayload & { _key: string };

function toEditable(items: ReferenceAnnotationPayload[]): EditableAnnotation[] {
  return items.map((item, index) => ({
    ...item,
    _key: item.id ?? `new-${index}`,
  }));
}

function polygonToText(polygon: number[][] | null | undefined): string {
  if (!polygon || polygon.length === 0) return '';
  try {
    return JSON.stringify(polygon, null, 2);
  } catch {
    return '';
  }
}

function textToPolygon(value: string): number[][] | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = JSON.parse(trimmed) as unknown;
  if (!Array.isArray(parsed)) throw new Error('invalid polygon');
  return parsed as number[][];
}

function toPayload(items: EditableAnnotation[]): ReferenceAnnotationPayload[] {
  return items.map(({ _key: _unused, ...item }) => ({
    ...item,
    anchor_texts: item.anchor_texts.filter(Boolean),
  }));
}

export default function SupplierReferenceAnnotationEditorDialog({
  open,
  onClose,
  clientId,
  supplierId,
  imageId,
  imageLabel,
  activeProfileId,
}: SupplierReferenceAnnotationEditorDialogProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<EditableAnnotation[]>([]);
  const [polygonErrors, setPolygonErrors] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string | null>(null);

  const annotationsQuery = useSupplierReferenceAnnotations(clientId, supplierId, imageId, {
    enabled: open && Boolean(clientId && supplierId && imageId),
  });
  const replaceMutation = useReplaceSupplierReferenceAnnotations(clientId, supplierId, imageId);

  useEffect(() => {
    if (!open) return;
    if (!annotationsQuery.data) return;
    setItems(
      toEditable(
        annotationsQuery.data.items.map((item) => ({
          id: item.id,
          field_key: item.field_key,
          anchor_texts: item.anchor_texts,
          spatial_relation: item.spatial_relation,
          normalized_polygon: item.normalized_polygon,
          priority: item.priority,
          required: item.required,
          max_distance_ratio: item.max_distance_ratio,
        }))
      )
    );
    setPolygonErrors({});
    setSaveError(null);
  }, [annotationsQuery.data, open]);

  const handleClose = useCallback(() => {
    replaceMutation.reset();
    onClose();
  }, [onClose, replaceMutation]);

  const handleSave = useCallback(async () => {
    const nextPolygonErrors: Record<string, string> = {};
    const normalizedItems = items.map((item) => {
      const polygonText = polygonToText(item.normalized_polygon ?? null);
      if (!polygonText.trim()) {
        return { ...item, normalized_polygon: null };
      }
      try {
        return { ...item, normalized_polygon: textToPolygon(polygonText) };
      } catch {
        nextPolygonErrors[item._key] = t('clients.extraction_profile.annotations.invalid_polygon');
        return item;
      }
    });
    if (Object.keys(nextPolygonErrors).length > 0) {
      setPolygonErrors(nextPolygonErrors);
      return;
    }
    setPolygonErrors({});
    setSaveError(null);
    try {
      await replaceMutation.mutateAsync({
        profile_id: activeProfileId ?? null,
        annotations: toPayload(normalizedItems),
      });
      handleClose();
    } catch (error) {
      setSaveError(resolveApiErrorMessage(error, 'clients.extraction_profile.annotations.save_error'));
    }
  }, [activeProfileId, handleClose, items, replaceMutation, t]);

  const addRow = () => {
    setItems((prev) => [
      ...prev,
      {
        _key: `new-${Date.now()}`,
        field_key: '',
        anchor_texts: [],
        spatial_relation: 'RIGHT_OF',
        normalized_polygon: null,
        priority: prev.length + 1,
        required: false,
        max_distance_ratio: null,
      },
    ]);
  };

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="md">
      <DialogTitle>{t('clients.extraction_profile.annotations.title')}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            {t('clients.extraction_profile.annotations.subtitle', { name: imageLabel })}
          </Typography>
          <Alert severity="info">{t('clients.extraction_profile.annotations.desktop_preferred')}</Alert>

          {annotationsQuery.isLoading ? (
            <LoadingBlock message={t('common.loading')} py={1} sx={{ justifyContent: 'flex-start' }} />
          ) : null}

          {annotationsQuery.isError && annotationsQuery.error ? (
            <ErrorAlert
              message={resolveApiErrorMessage(
                annotationsQuery.error,
                'clients.extraction_profile.annotations.load_error'
              )}
              onRetry={() => annotationsQuery.refetch()}
              retryLabel={t('common.retry')}
            />
          ) : null}

          {items.map((item) => (
            <Box
              key={item._key}
              sx={{
                display: 'grid',
                gap: 1.5,
                p: 1.5,
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
              }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                <Typography variant="subtitle2">{t('clients.extraction_profile.annotations.row_title')}</Typography>
                <IconButton
                  size="small"
                  color="error"
                  aria-label={t('common.delete')}
                  onClick={() => setItems((prev) => prev.filter((row) => row._key !== item._key))}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Box>
              <TextField
                label={t('clients.extraction_profile.annotations.field_key')}
                size="small"
                fullWidth
                value={item.field_key}
                onChange={(e) =>
                  setItems((prev) =>
                    prev.map((row) => (row._key === item._key ? { ...row, field_key: e.target.value } : row))
                  )
                }
              />
              <TextField
                label={t('clients.extraction_profile.annotations.anchor_texts')}
                size="small"
                fullWidth
                value={item.anchor_texts.join(', ')}
                onChange={(e) =>
                  setItems((prev) =>
                    prev.map((row) =>
                      row._key === item._key
                        ? {
                            ...row,
                            anchor_texts: e.target.value
                              .split(',')
                              .map((part) => part.trim())
                              .filter(Boolean),
                          }
                        : row
                    )
                  )
                }
                helperText={t('clients.extraction_profile.comma_separated_hint')}
              />
              <TextField
                select
                label={t('clients.extraction_profile.annotations.spatial_relation')}
                size="small"
                fullWidth
                value={item.spatial_relation}
                onChange={(e) =>
                  setItems((prev) =>
                    prev.map((row) =>
                      row._key === item._key ? { ...row, spatial_relation: e.target.value } : row
                    )
                  )
                }
              >
                {SPATIAL_RELATIONS.map((relation) => (
                  <MenuItem key={relation} value={relation}>
                    {relation}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label={t('clients.extraction_profile.annotations.normalized_polygon')}
                size="small"
                fullWidth
                multiline
                minRows={3}
                value={polygonToText(item.normalized_polygon ?? null)}
                onChange={(e) => {
                  const raw = e.target.value;
                  setPolygonErrors((prev) => {
                    const next = { ...prev };
                    delete next[item._key];
                    return next;
                  });
                  setItems((prev) =>
                    prev.map((row) => {
                      if (row._key !== item._key) return row;
                      if (!raw.trim()) return { ...row, normalized_polygon: null };
                      try {
                        return { ...row, normalized_polygon: textToPolygon(raw) };
                      } catch {
                        return { ...row, normalized_polygon: row.normalized_polygon ?? null };
                      }
                    })
                  );
                }}
                error={Boolean(polygonErrors[item._key])}
                helperText={
                  polygonErrors[item._key] ?? t('clients.extraction_profile.annotations.polygon_hint')
                }
                InputProps={{ sx: { fontFamily: 'monospace', fontSize: '0.85rem' } }}
              />
              <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' } }}>
                <TextField
                  label={t('clients.extraction_profile.annotations.priority')}
                  type="number"
                  size="small"
                  value={item.priority ?? 1}
                  onChange={(e) =>
                    setItems((prev) =>
                      prev.map((row) =>
                        row._key === item._key ? { ...row, priority: Number(e.target.value) } : row
                      )
                    )
                  }
                />
                <TextField
                  label={t('clients.extraction_profile.annotations.max_distance_ratio')}
                  type="number"
                  size="small"
                  value={item.max_distance_ratio ?? ''}
                  onChange={(e) =>
                    setItems((prev) =>
                      prev.map((row) =>
                        row._key === item._key
                          ? {
                              ...row,
                              max_distance_ratio: e.target.value === '' ? null : Number(e.target.value),
                            }
                          : row
                      )
                    )
                  }
                />
              </Box>
              <FormControlLabel
                control={
                  <Switch
                    size="small"
                    checked={Boolean(item.required)}
                    onChange={(e) =>
                      setItems((prev) =>
                        prev.map((row) =>
                          row._key === item._key ? { ...row, required: e.target.checked } : row
                        )
                      )
                    }
                  />
                }
                label={t('clients.extraction_profile.required')}
              />
            </Box>
          ))}

          <Button size="small" startIcon={<AddIcon />} onClick={addRow} sx={{ alignSelf: 'flex-start' }}>
            {t('clients.extraction_profile.annotations.add_row')}
          </Button>

          {saveError ? <Alert severity="error">{saveError}</Alert> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={replaceMutation.isPending} onClick={() => void handleSave()}>
          {replaceMutation.isPending ? t('common.submitting') : t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
