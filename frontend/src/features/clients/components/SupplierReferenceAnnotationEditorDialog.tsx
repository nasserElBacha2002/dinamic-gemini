import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
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
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useTranslation } from 'react-i18next';
import type { ReferenceAnnotationPayload } from '../../../api/types';
import { fetchSupplierReferenceImageDisplay } from '../../../api/client';
import { ErrorAlert, LoadingBlock } from '../../../components/ui';
import { useReplaceSupplierReferenceAnnotations, useSupplierReferenceAnnotations } from '../../../hooks';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { SPATIAL_RELATIONS } from '../utils/defaultExtractionProfileConfiguration';
import {
  polygonToText,
  textToPolygon,
  validateNormalizedPolygon,
} from '../utils/annotationPolygonUtils';
import ReferenceAnnotationCanvas, { type AnnotationDrawMode } from './ReferenceAnnotationCanvas';

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

function toPayload(items: EditableAnnotation[]): ReferenceAnnotationPayload[] {
  return items.map((item) => {
    const { _key, ...rest } = item;
    void _key;
    return {
      ...rest,
      anchor_texts: item.anchor_texts.filter(Boolean),
    };
  });
}

function validationMessageKey(code: ReturnType<typeof validateNormalizedPolygon>): string | null {
  if (!code) return null;
  if (code === 'min_points') return 'clients.extraction_profile.annotations.validation_min_points';
  if (code === 'out_of_range') return 'clients.extraction_profile.annotations.validation_out_of_range';
  return 'clients.extraction_profile.annotations.invalid_polygon';
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
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [drawMode, setDrawMode] = useState<AnnotationDrawMode>('select');
  const [zoom, setZoom] = useState(1);
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [imageLoadError, setImageLoadError] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState(false);

  const annotationsQuery = useSupplierReferenceAnnotations(clientId, supplierId, imageId, {
    enabled: open && Boolean(clientId && supplierId && imageId),
  });
  const replaceMutation = useReplaceSupplierReferenceAnnotations(clientId, supplierId, imageId);

  useEffect(() => {
    if (!open) return;
    if (!annotationsQuery.data) return;
    const nextItems = toEditable(
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
    );
    setItems(nextItems);
    setSelectedKey(nextItems[0]?._key ?? null);
    setPolygonErrors({});
    setSaveError(null);
    setDrawMode('select');
    setZoom(1);
  }, [annotationsQuery.data, open]);

  useEffect(() => {
    if (!open) return;
    let revoke: (() => void) | undefined;
    let cancelled = false;
    setImageLoading(true);
    setImageLoadError(null);
    void fetchSupplierReferenceImageDisplay(clientId, supplierId, imageId)
      .then((result) => {
        if (cancelled) {
          if (result.ok) {
            result.revoke?.();
          }
          return;
        }
        if (!result.ok) {
          setImageSrc(null);
          setImageLoadError(result.detail ?? t('clients.extraction_profile.annotations.image_load_error'));
          return;
        }
        revoke = result.revoke;
        setImageSrc(result.imageSrc);
      })
      .catch(() => {
        if (!cancelled) {
          setImageSrc(null);
          setImageLoadError(t('clients.extraction_profile.annotations.image_load_error'));
        }
      })
      .finally(() => {
        if (!cancelled) setImageLoading(false);
      });
    return () => {
      cancelled = true;
      revoke?.();
    };
  }, [clientId, imageId, open, supplierId, t]);

  const handleClose = useCallback(() => {
    replaceMutation.reset();
    onClose();
  }, [onClose, replaceMutation]);

  const handleSave = useCallback(async () => {
    const nextPolygonErrors: Record<string, string> = {};
    const normalizedItems = items.map((item) => {
      const polygon = item.normalized_polygon ?? null;
      if (!polygon || polygon.length === 0) {
        return { ...item, normalized_polygon: null };
      }
      const validationCode = validateNormalizedPolygon(polygon);
      if (validationCode) {
        const key = validationMessageKey(validationCode);
        nextPolygonErrors[item._key] = t(key ?? 'clients.extraction_profile.annotations.invalid_polygon');
        return item;
      }
      return item;
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
    const key = `new-${Date.now()}`;
    setItems((prev) => [
      ...prev,
      {
        _key: key,
        field_key: '',
        anchor_texts: [],
        spatial_relation: 'RIGHT_OF',
        normalized_polygon: null,
        priority: prev.length + 1,
        required: false,
        max_distance_ratio: null,
      },
    ]);
    setSelectedKey(key);
    setDrawMode('rectangle');
  };

  const canvasItems = useMemo(
    () =>
      items.map((item) => ({
        key: item._key,
        field_key: item.field_key,
        anchor_texts: item.anchor_texts,
        normalized_polygon: item.normalized_polygon ?? null,
      })),
    [items]
  );

  const selectedValidationError = selectedKey ? polygonErrors[selectedKey] : null;

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="lg">
      <DialogTitle>{t('clients.extraction_profile.annotations.title')}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            {t('clients.extraction_profile.annotations.subtitle', { name: imageLabel })}
          </Typography>

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

          {imageLoading ? (
            <LoadingBlock
              message={t('clients.extraction_profile.annotations.image_loading')}
              py={1}
              sx={{ justifyContent: 'flex-start' }}
            />
          ) : null}

          {imageLoadError ? <Alert severity="warning">{imageLoadError}</Alert> : null}

          <Box
            sx={{
              display: 'grid',
              gap: 2,
              gridTemplateColumns: { xs: '1fr', md: '1.1fr 0.9fr' },
              alignItems: 'start',
            }}
          >
            <ReferenceAnnotationCanvas
              imageSrc={imageSrc}
              imageAlt={imageLabel}
              items={canvasItems}
              selectedKey={selectedKey}
              onSelect={setSelectedKey}
              onPolygonChange={(key, polygon) => {
                setPolygonErrors((prev) => {
                  const next = { ...prev };
                  delete next[key];
                  return next;
                });
                setItems((prev) =>
                  prev.map((row) => (row._key === key ? { ...row, normalized_polygon: polygon } : row))
                );
              }}
              drawMode={drawMode}
              onDrawModeChange={setDrawMode}
              zoom={zoom}
              onZoomChange={setZoom}
            />

            <Stack spacing={1.5}>
              {selectedValidationError ? <Alert severity="error">{selectedValidationError}</Alert> : null}
              {items.length === 0 ? (
                <Alert severity="info">{t('clients.extraction_profile.annotations.empty_rows')}</Alert>
              ) : null}

              {items.map((item) => {
                const selected = item._key === selectedKey;
                return (
                  <Box
                    key={item._key}
                    sx={{
                      display: 'grid',
                      gap: 1.5,
                      p: 1.5,
                      border: 2,
                      borderColor: selected ? 'primary.main' : 'divider',
                      borderRadius: 1,
                      bgcolor: selected ? 'action.hover' : 'background.paper',
                      cursor: 'pointer',
                    }}
                    onClick={() => setSelectedKey(item._key)}
                  >
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                      <Typography variant="subtitle2">
                        {t('clients.extraction_profile.annotations.row_title')}
                      </Typography>
                      <IconButton
                        size="small"
                        color="error"
                        aria-label={t('common.delete')}
                        onClick={(event) => {
                          event.stopPropagation();
                          setItems((prev) => prev.filter((row) => row._key !== item._key));
                          if (selectedKey === item._key) {
                            const remaining = items.filter((row) => row._key !== item._key);
                            setSelectedKey(remaining[0]?._key ?? null);
                          }
                        }}
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </Box>
                    <TextField
                      label={t('clients.extraction_profile.annotations.field_key')}
                      size="small"
                      fullWidth
                      value={item.field_key}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(e) =>
                        setItems((prev) =>
                          prev.map((row) =>
                            row._key === item._key ? { ...row, field_key: e.target.value } : row
                          )
                        )
                      }
                    />
                    <TextField
                      label={t('clients.extraction_profile.annotations.anchor_texts')}
                      size="small"
                      fullWidth
                      value={item.anchor_texts.join(', ')}
                      onClick={(event) => event.stopPropagation()}
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
                      onClick={(event) => event.stopPropagation()}
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

                    <Accordion
                      disableGutters
                      elevation={0}
                      sx={{ border: 1, borderColor: 'divider', '&:before': { display: 'none' } }}
                      onClick={(event) => event.stopPropagation()}
                    >
                      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Typography variant="body2">
                          {t('clients.extraction_profile.annotations.advanced_polygon_json')}
                        </Typography>
                      </AccordionSummary>
                      <AccordionDetails>
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
                            polygonErrors[item._key] ??
                            t('clients.extraction_profile.annotations.polygon_hint')
                          }
                          InputProps={{ sx: { fontFamily: 'monospace', fontSize: '0.85rem' } }}
                        />
                      </AccordionDetails>
                    </Accordion>

                    <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' } }}>
                      <TextField
                        label={t('clients.extraction_profile.annotations.priority')}
                        type="number"
                        size="small"
                        value={item.priority ?? 1}
                        onClick={(event) => event.stopPropagation()}
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
                        onClick={(event) => event.stopPropagation()}
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
                );
              })}

              <Button size="small" startIcon={<AddIcon />} onClick={addRow} sx={{ alignSelf: 'flex-start' }}>
                {t('clients.extraction_profile.annotations.add_row')}
              </Button>
            </Stack>
          </Box>

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
