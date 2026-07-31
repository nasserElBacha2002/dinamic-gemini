/**
 * Physical aisle locations + positioning labels (Phase 1 / Phase 2).
 * Not CV positions — shelf/rack/slot labels with DINAMIC_POSITION payload.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { PageHeader } from '../components/shell';
import {
  BaseDialog,
  EmptyState,
  ErrorAlert,
  LoadingBlock,
  SectionCard,
  StatusBadge,
  useAppSnackbar,
} from '../components/ui';
import {
  pathToAislePositions,
  pathToClient,
  pathToClientPhysicalLocations,
  pathToInventory,
  pathToInventoryPhysicalLocations,
  ROUTE_HOME,
} from '../constants/appRoutes';
import {
  useAisleLocationLabels,
  useAisleLocations,
  useAislesList,
  useCreateAisleLocation,
  useInvalidateAisleLocationLabel,
  useInventoryDetail,
  useIssueAisleLocationLabel,
  useRenderAisleLocationLabel,
  useReplaceAisleLocationLabel,
  useUpdateAisleLocation,
} from '../hooks';
import type { AisleLocation, AisleLocationLabel } from '../api/types';
import {
  downloadAisleLocationLabelFile,
  downloadAisleLocationLabelsBatch,
  fetchAisleLocationLabelPreviewBlob,
} from '../api/client';
import { resolveApiErrorMessage } from '../utils/apiErrors';
import { getAisleLocationUiCapabilities } from '../features/aisleLocations/aisleLocationCapabilities';
import { trackPositioningEvent } from '../features/aisleLocations/trackPositioningEvent';

const PRESETS = [
  { code: 'MM_100x100', labelKey: 'aisle_locations.preset_100x100' },
  { code: 'MM_100x150', labelKey: 'aisle_locations.preset_100x150' },
  { code: 'A6', labelKey: 'aisle_locations.preset_a6' },
  { code: 'A4_GRID', labelKey: 'aisle_locations.preset_a4_grid' },
  { code: 'THERMAL', labelKey: 'aisle_locations.preset_thermal' },
] as const;

const DEFAULT_PRESET = 'MM_100x100';

function signatureSemantic(status: string): 'success' | 'warning' | 'error' | 'neutral' {
  const s = status.toUpperCase();
  if (s === 'VALID' || s === 'SIGNED' || s === 'OK') return 'success';
  if (s === 'INVALID' || s === 'FAILED') return 'error';
  if (s === 'UNSIGNED' || s === 'MISSING' || s === 'NONE') return 'warning';
  return 'neutral';
}

function signatureLabel(status: string, t: (k: string) => string): string {
  const s = status.toUpperCase();
  if (s === 'VALID' || s === 'SIGNED' || s === 'OK') return t('aisle_locations.signature_valid');
  if (s === 'INVALID' || s === 'FAILED') return t('aisle_locations.signature_invalid');
  if (s === 'UNSIGNED' || s === 'MISSING' || s === 'NONE') return t('aisle_locations.signature_none');
  return status || t('common.em_dash');
}

export default function AisleLocationsPage() {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const caps = useMemo(() => getAisleLocationUiCapabilities(), []);
  const { inventoryId, aisleId } = useParams<{ inventoryId: string; aisleId: string }>();
  const safeInv = (inventoryId ?? '').trim();
  const safeAisle = (aisleId ?? '').trim();

  const [createOpen, setCreateOpen] = useState(false);
  const [editLocation, setEditLocation] = useState<AisleLocation | null>(null);
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const [generateBusy, setGenerateBusy] = useState(false);
  const [generateStatus, setGenerateStatus] = useState<string | null>(null);
  const [resultOpen, setResultOpen] = useState(false);
  const [resultLabel, setResultLabel] = useState<AisleLocationLabel | null>(null);
  const [resultLocation, setResultLocation] = useState<AisleLocation | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [preset, setPreset] = useState(DEFAULT_PRESET);

  const [replaceTarget, setReplaceTarget] = useState<AisleLocationLabel | null>(null);
  const [invalidateTarget, setInvalidateTarget] = useState<AisleLocationLabel | null>(null);
  const [invalidateReason, setInvalidateReason] = useState('');

  const [batchOpen, setBatchOpen] = useState(false);
  const [batchSelected, setBatchSelected] = useState<Set<string>>(new Set());
  const [batchPreset, setBatchPreset] = useState('A4_GRID');
  const [batchEmitMissing, setBatchEmitMissing] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);

  const inventoryQuery = useInventoryDetail(safeInv || undefined);
  const aislesQuery = useAislesList(safeInv || undefined, { enabled: Boolean(safeInv) });
  const aisle = useMemo(
    () => (aislesQuery.data?.items ?? []).find((a) => a.id === safeAisle) ?? null,
    [aislesQuery.data?.items, safeAisle]
  );
  const clientId = (inventoryQuery.data?.client_id ?? '').trim();

  const locationsQuery = useAisleLocations(safeInv || undefined, safeAisle || undefined);
  const locations = locationsQuery.data?.items ?? [];
  const selected =
    locations.find((loc) => loc.id === selectedLocationId) ?? locations[0] ?? null;
  const effectiveSelectedId = selected?.id ?? null;

  const labelsQuery = useAisleLocationLabels(safeInv || undefined, effectiveSelectedId ?? undefined, {
    enabled: Boolean(effectiveSelectedId) && caps.labelsEnabled,
  });
  const labels = labelsQuery.data?.items ?? [];
  const activeLabel = labels.find((l) => String(l.status).toUpperCase() === 'ACTIVE') ?? null;

  const createMutation = useCreateAisleLocation(safeInv, safeAisle);
  const updateMutation = useUpdateAisleLocation(safeInv, safeAisle);
  const issueMutation = useIssueAisleLocationLabel(safeInv, safeAisle);
  const invalidateMutation = useInvalidateAisleLocationLabel(safeInv, safeAisle);
  const renderMutation = useRenderAisleLocationLabel(safeInv, safeAisle);
  const replaceMutation = useReplaceAisleLocationLabel(safeInv, safeAisle);

  useEffect(() => {
    if (!safeInv || !safeAisle) return;
    trackPositioningEvent('physical_locations_opened', {
      inventory_id: safeInv,
      aisle_id: safeAisle,
    });
  }, [safeInv, safeAisle]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const breadcrumbs = useMemo(() => {
    const items: { label: string; to?: string }[] = [
      { label: t('aisle.breadcrumb_inventories'), to: ROUTE_HOME },
    ];
    if (clientId) {
      items.push({
        label: t('aisle_locations.breadcrumb_client'),
        to: pathToClient(clientId),
      });
    }
    items.push({
      label: inventoryQuery.data?.name ?? t('common.em_dash'),
      to: pathToInventory(safeInv),
    });
    items.push({
      label: aisle?.code ?? t('common.em_dash'),
      to: pathToAislePositions(safeInv, safeAisle),
    });
    items.push({ label: t('aisle_locations.page_title') });
    return items;
  }, [aisle?.code, clientId, inventoryQuery.data?.name, safeAisle, safeInv, t]);

  const resetForm = () => {
    setCode('');
    setDisplayName('');
    setDescription('');
    setFormError(null);
  };

  const openCreate = () => {
    resetForm();
    setCreateOpen(true);
  };

  const openEdit = (loc: AisleLocation) => {
    setEditLocation(loc);
    setDisplayName(loc.display_name ?? '');
    setDescription(loc.description ?? '');
    setFormError(null);
  };

  const clearPreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
  };

  const loadPreview = async (labelId: string, selectedPreset: string) => {
    if (!caps.renderEnabled) return;
    const blob = await fetchAisleLocationLabelPreviewBlob(safeInv, labelId, {
      format: 'PNG',
      preset: selectedPreset,
    });
    clearPreview();
    const objectUrl = URL.createObjectURL(blob);
    setPreviewUrl(objectUrl);
    trackPositioningEvent('position_label_preview_opened', { label_id: labelId });
  };

  const openResult = async (loc: AisleLocation, label: AisleLocationLabel) => {
    setResultLocation(loc);
    setResultLabel(label);
    setResultOpen(true);
    setSelectedLocationId(loc.id);
    try {
      if (caps.renderEnabled) {
        setGenerateStatus(t('aisle_locations.status_rendering_preview'));
        await loadPreview(label.id, preset);
      }
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisle_locations.preview_error'), 'error');
    } finally {
      setGenerateStatus(null);
    }
  };

  const handleCreate = async () => {
    const trimmed = code.trim();
    if (!trimmed) {
      setFormError(t('aisle_locations.validation_code_required'));
      return;
    }
    setFormError(null);
    try {
      const created = await createMutation.mutateAsync({
        code: trimmed,
        display_name: displayName.trim() || null,
        description: description.trim() || null,
      });
      showSnackbar(t('aisle_locations.created_snackbar'), 'success');
      trackPositioningEvent('physical_location_created', { location_id: created.id });
      setCreateOpen(false);
      resetForm();
      setSelectedLocationId(created.id);
    } catch (e) {
      setFormError(resolveApiErrorMessage(e, 'aisle_locations.create_error'));
    }
  };

  const handleUpdate = async () => {
    if (!editLocation) return;
    setFormError(null);
    try {
      await updateMutation.mutateAsync({
        locationId: editLocation.id,
        body: {
          display_name: displayName.trim() || null,
          description: description.trim() || null,
        },
      });
      showSnackbar(t('aisle_locations.updated_snackbar'), 'success');
      setEditLocation(null);
    } catch (e) {
      setFormError(resolveApiErrorMessage(e, 'aisle_locations.update_error'));
    }
  };

  const toggleStatus = async (loc: AisleLocation) => {
    const next = loc.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE';
    try {
      await updateMutation.mutateAsync({
        locationId: loc.id,
        body: { status: next },
      });
      showSnackbar(
        next === 'ACTIVE'
          ? t('aisle_locations.activated_snackbar')
          : t('aisle_locations.deactivated_snackbar'),
        'success'
      );
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisle_locations.update_error'), 'error');
    }
  };

  /** Unified generate: issue if needed → render → preview modal. */
  const handleGeneratePositioningLabel = async (loc: AisleLocation) => {
    if (!caps.labelsEnabled) {
      showSnackbar(t('aisle_locations.labels_disabled'), 'warning');
      return;
    }
    setGenerateBusy(true);
    setGenerateStatus(t('aisle_locations.status_generating'));
    trackPositioningEvent('position_label_generation_requested', { location_id: loc.id });
    try {
      setSelectedLocationId(loc.id);
      const issued = await issueMutation.mutateAsync({ locationId: loc.id });
      showSnackbar(t('aisle_locations.label_issued_snackbar'), 'success');
      if (caps.renderEnabled) {
        setGenerateStatus(t('aisle_locations.status_rendering_preview'));
        await renderMutation.mutateAsync({
          labelId: issued.id,
          format: 'PNG',
          preset,
        });
      }
      await openResult(loc, issued);
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisle_locations.generate_error'), 'error');
    } finally {
      setGenerateBusy(false);
      setGenerateStatus(null);
    }
  };

  const handleViewActiveLabel = async (loc: AisleLocation, label: AisleLocationLabel) => {
    setGenerateBusy(true);
    try {
      await openResult(loc, label);
    } finally {
      setGenerateBusy(false);
    }
  };

  const handleDownload = async (format: 'PDF' | 'PNG') => {
    if (!resultLabel || !caps.renderEnabled) return;
    try {
      setGenerateStatus(
        format === 'PDF'
          ? t('aisle_locations.status_preparing_pdf')
          : t('aisle_locations.status_rendering_preview')
      );
      await renderMutation.mutateAsync({
        labelId: resultLabel.id,
        format,
        preset,
      });
      await downloadAisleLocationLabelFile(safeInv, resultLabel.id, { format, preset });
      trackPositioningEvent('position_label_download_requested', {
        label_id: resultLabel.id,
        format,
      });
      showSnackbar(t('aisle_locations.download_ok'), 'success');
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisle_locations.download_error'), 'error');
    } finally {
      setGenerateStatus(null);
    }
  };

  const handleReprint = async () => {
    if (!resultLabel || !caps.renderEnabled) return;
    trackPositioningEvent('position_label_reprint_requested', { label_id: resultLabel.id });
    try {
      setGenerateStatus(t('aisle_locations.status_rendering_preview'));
      await renderMutation.mutateAsync({
        labelId: resultLabel.id,
        format: 'PNG',
        preset,
      });
      await loadPreview(resultLabel.id, preset);
      showSnackbar(t('aisle_locations.reprint_ok'), 'success');
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisle_locations.reprint_error'), 'error');
    } finally {
      setGenerateStatus(null);
    }
  };

  const handleConfirmReplace = async () => {
    if (!replaceTarget) return;
    trackPositioningEvent('position_label_replace_requested', { label_id: replaceTarget.id });
    try {
      const next = await replaceMutation.mutateAsync({ labelId: replaceTarget.id });
      showSnackbar(t('aisle_locations.replace_ok'), 'success');
      setReplaceTarget(null);
      if (resultLocation) {
        if (caps.renderEnabled) {
          await renderMutation.mutateAsync({
            labelId: next.id,
            format: 'PNG',
            preset,
          });
        }
        await openResult(resultLocation, next);
      }
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisle_locations.replace_error'), 'error');
    }
  };

  const handleConfirmInvalidate = async () => {
    if (!invalidateTarget) return;
    try {
      await invalidateMutation.mutateAsync({
        locationId: invalidateTarget.location_id,
        labelId: invalidateTarget.id,
        body: { reason: invalidateReason.trim() || null },
      });
      trackPositioningEvent('position_label_invalidated', { label_id: invalidateTarget.id });
      showSnackbar(t('aisle_locations.label_invalidated_snackbar'), 'success');
      setInvalidateTarget(null);
      setInvalidateReason('');
      clearPreview();
      setResultOpen(false);
      setResultLabel(null);
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisle_locations.label_invalidate_error'), 'error');
    }
  };

  const openBatch = () => {
    setBatchSelected(new Set(locations.filter((l) => l.status === 'ACTIVE').map((l) => l.id)));
    setBatchEmitMissing(false);
    setBatchPreset('A4_GRID');
    setBatchOpen(true);
  };

  const handleBatchGenerate = async () => {
    if (!caps.batchEnabled || !caps.renderEnabled) {
      showSnackbar(t('aisle_locations.batch_disabled'), 'warning');
      return;
    }
    const ids = Array.from(batchSelected);
    if (ids.length === 0) {
      showSnackbar(t('aisle_locations.batch_none_selected'), 'warning');
      return;
    }
    setBatchBusy(true);
    trackPositioningEvent('position_label_batch_requested', {
      count: ids.length,
      emit_missing: batchEmitMissing,
    });
    try {
      setGenerateStatus(t('aisle_locations.status_batch'));
      await downloadAisleLocationLabelsBatch(safeInv, safeAisle, {
        preset: batchPreset,
        format: 'PDF',
        location_ids: ids,
        emit_missing: batchEmitMissing,
      });
      showSnackbar(t('aisle_locations.batch_ok'), 'success');
      setBatchOpen(false);
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisle_locations.batch_error'), 'error');
    } finally {
      setBatchBusy(false);
      setGenerateStatus(null);
    }
  };

  const payloadTypeOk =
    resultLabel &&
    String((resultLabel.payload as { type?: string })?.type ?? '').toUpperCase() ===
      'DINAMIC_POSITION';
  const payloadHasProductFields = Boolean(
    resultLabel &&
      Object.keys(resultLabel.payload ?? {}).some((k) =>
        /sku|product|item|ean|gtin/i.test(k)
      )
  );

  if (!safeInv || !safeAisle) {
    return <ErrorAlert message={t('aisle_locations.missing_route_params')} />;
  }

  if (!caps.domainEnabled) {
    return (
      <Alert severity="warning" data-testid="physical-locations-domain-disabled">
        {t('aisle_locations.domain_disabled')}
      </Alert>
    );
  }

  if (inventoryQuery.isLoading || aislesQuery.isLoading) {
    return <LoadingBlock />;
  }

  const rowPrimaryAction = (loc: AisleLocation) => {
    const isSelected = loc.id === effectiveSelectedId;
    const hasActive = isSelected && Boolean(activeLabel);
    if (!caps.labelsEnabled) return null;
    if (hasActive && activeLabel) {
      return (
        <Button
          size="small"
          variant="contained"
          disabled={generateBusy}
          data-testid={`aisle-location-view-label-${loc.id}`}
          onClick={() => void handleViewActiveLabel(loc, activeLabel)}
        >
          {t('aisle_locations.view_label')}
        </Button>
      );
    }
    return (
      <Button
        size="small"
        variant="contained"
        disabled={loc.status !== 'ACTIVE' || generateBusy || issueMutation.isPending}
        data-testid={`aisle-location-generate-${loc.id}`}
        onClick={() => void handleGeneratePositioningLabel(loc)}
      >
        {t('aisle_locations.generate_label')}
      </Button>
    );
  };

  return (
    <>
      <PageHeader
        breadcrumbs={breadcrumbs}
        title={t('aisle_locations.page_title')}
        subtitle={t('aisle_locations.page_subtitle', { aisle: aisle?.code ?? safeAisle })}
        actions={
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {caps.batchEnabled && caps.renderEnabled ? (
              <Button
                variant="outlined"
                size="small"
                disabled={locations.length === 0 || batchBusy}
                data-testid="physical-locations-batch"
                onClick={openBatch}
              >
                {t('aisle_locations.batch_action')}
              </Button>
            ) : null}
            <Button
              variant="contained"
              size="small"
              data-testid="physical-locations-create"
              onClick={openCreate}
            >
              {t('aisle_locations.create')}
            </Button>
          </Stack>
        }
      />

      <Box sx={{ display: 'grid', gap: 2 }}>
        {generateStatus ? (
          <Alert severity="info" data-testid="physical-locations-status">
            {generateStatus}
          </Alert>
        ) : null}

        {locationsQuery.isError ? (
          <ErrorAlert
            error={locationsQuery.error}
            context="aisle"
            onRetry={() => void locationsQuery.refetch()}
          />
        ) : null}

        <SectionCard title={t('aisle_locations.list_title')}>
          {locationsQuery.isLoading ? (
            <LoadingBlock />
          ) : locations.length === 0 ? (
            <EmptyState
              title={t('aisle_locations.empty_title')}
              message={t('aisle_locations.empty_message')}
              action={
                <Button variant="contained" onClick={openCreate}>
                  {t('aisle_locations.create')}
                </Button>
              }
            />
          ) : (
            <Stack spacing={1.5}>
              {locations.map((loc) => {
                const isSelected = loc.id === effectiveSelectedId;
                return (
                  <Box
                    key={loc.id}
                    data-testid={`aisle-location-row-${loc.id}`}
                    sx={{
                      border: 1,
                      borderColor: isSelected ? 'primary.main' : 'divider',
                      borderRadius: 1,
                      p: 1.5,
                      display: 'grid',
                      gap: 1,
                    }}
                  >
                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1,
                        flexWrap: 'wrap',
                        justifyContent: 'space-between',
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                        <Typography fontWeight={650}>{loc.code}</Typography>
                        {loc.display_name ? (
                          <Typography color="text.secondary">{loc.display_name}</Typography>
                        ) : null}
                        <StatusBadge
                          label={
                            loc.status === 'ACTIVE'
                              ? t('aisle_locations.status_active')
                              : t('aisle_locations.status_inactive')
                          }
                          semantic={loc.status === 'ACTIVE' ? 'success' : 'neutral'}
                        />
                        {isSelected && activeLabel ? (
                          <Chip size="small" color="success" label={t('aisle_locations.has_active_label')} />
                        ) : null}
                      </Box>
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => setSelectedLocationId(loc.id)}
                        >
                          {t('aisle_locations.view_detail')}
                        </Button>
                        <Button size="small" onClick={() => openEdit(loc)}>
                          {t('aisle_locations.edit')}
                        </Button>
                        <Button size="small" onClick={() => void toggleStatus(loc)}>
                          {loc.status === 'ACTIVE'
                            ? t('aisle_locations.deactivate')
                            : t('aisle_locations.activate')}
                        </Button>
                        {rowPrimaryAction(loc)}
                      </Stack>
                    </Box>
                    {loc.description ? (
                      <Typography variant="body2" color="text.secondary">
                        {loc.description}
                      </Typography>
                    ) : null}
                  </Box>
                );
              })}
            </Stack>
          )}
        </SectionCard>

        <SectionCard
          title={t('aisle_locations.labels_title')}
          subtitle={
            selected
              ? t('aisle_locations.labels_subtitle', { code: selected.code })
              : t('aisle_locations.labels_subtitle_none')
          }
        >
          {!selected ? (
            <Typography color="text.secondary">{t('aisle_locations.select_location_hint')}</Typography>
          ) : !caps.labelsEnabled ? (
            <Alert severity="info">{t('aisle_locations.labels_disabled')}</Alert>
          ) : labelsQuery.isLoading ? (
            <LoadingBlock />
          ) : labelsQuery.isError ? (
            <ErrorAlert
              error={labelsQuery.error}
              context="aisle"
              onRetry={() => void labelsQuery.refetch()}
            />
          ) : labels.length === 0 ? (
            <EmptyState
              title={t('aisle_locations.labels_empty_title')}
              message={t('aisle_locations.labels_empty_message')}
              action={
                selected.status === 'ACTIVE' ? (
                  <Button
                    variant="contained"
                    disabled={generateBusy}
                    onClick={() => void handleGeneratePositioningLabel(selected)}
                  >
                    {t('aisle_locations.generate_label')}
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <Stack spacing={1.5}>
              {labels.map((label) => (
                <Box
                  key={label.id}
                  data-testid={`aisle-location-label-${label.id}`}
                  sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 1.5 }}
                >
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                      flexWrap: 'wrap',
                      justifyContent: 'space-between',
                      mb: 1,
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                      <Chip size="small" label={t('aisle_locations.label_kind')} />
                      <Typography variant="body2">{label.public_identifier}</Typography>
                      <StatusBadge label={String(label.status)} semantic="neutral" />
                      <StatusBadge
                        label={signatureLabel(String(label.signature_status ?? ''), t)}
                        semantic={signatureSemantic(String(label.signature_status ?? ''))}
                      />
                    </Box>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      {String(label.status).toUpperCase() === 'ACTIVE' && selected ? (
                        <Button
                          size="small"
                          variant="contained"
                          onClick={() => void handleViewActiveLabel(selected, label)}
                        >
                          {t('aisle_locations.view_label')}
                        </Button>
                      ) : null}
                      {String(label.status).toUpperCase() === 'ACTIVE' ? (
                        <Button size="small" onClick={() => setReplaceTarget(label)}>
                          {t('aisle_locations.replace_label')}
                        </Button>
                      ) : null}
                      {String(label.status).toUpperCase() === 'ACTIVE' ? (
                        <Button
                          size="small"
                          color="warning"
                          onClick={() => {
                            setInvalidateTarget(label);
                            setInvalidateReason('');
                          }}
                        >
                          {t('aisle_locations.invalidate_label')}
                        </Button>
                      ) : null}
                    </Stack>
                  </Box>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                    {t('aisle_locations.payload_heading')}
                  </Typography>
                  <Box
                    component="pre"
                    sx={{
                      m: 0,
                      p: 1,
                      bgcolor: 'action.hover',
                      borderRadius: 1,
                      overflow: 'auto',
                      fontSize: 12,
                    }}
                  >
                    {JSON.stringify(label.payload, null, 2)}
                  </Box>
                  {label.invalidation_reason ? (
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                      {t('aisle_locations.invalidation_reason')}: {label.invalidation_reason}
                    </Typography>
                  ) : null}
                  {label.replaced_by_label_id ? (
                    <Typography variant="caption" color="text.secondary" display="block">
                      {t('aisle_locations.replaced_by')}: {label.replaced_by_label_id}
                    </Typography>
                  ) : null}
                </Box>
              ))}
            </Stack>
          )}
        </SectionCard>

        <Alert severity="info">{t('aisle_locations.cv_positions_note')}</Alert>
        <Alert severity="info">{t('aisle_locations.label_scope_help')}</Alert>

        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button component={RouterLink} to={pathToInventoryPhysicalLocations(safeInv)} size="small">
            {t('aisle_locations.hub_open_inventory_hub')}
          </Button>
          {clientId ? (
            <Button component={RouterLink} to={pathToClientPhysicalLocations(clientId)} size="small">
              {t('aisle_locations.hub_from_client')}
            </Button>
          ) : null}
        </Stack>
      </Box>

      {/* Create */}
      <BaseDialog
        open={createOpen}
        onClose={() => !createMutation.isPending && setCreateOpen(false)}
        disableClose={createMutation.isPending}
        title={t('aisle_locations.create_title')}
        description={t('aisle_locations.create_subtitle')}
        error={formError || undefined}
        actions={
          <>
            <Button onClick={() => setCreateOpen(false)} disabled={createMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="contained"
              onClick={() => void handleCreate()}
              disabled={createMutation.isPending}
            >
              {t('aisle_locations.create')}
            </Button>
          </>
        }
      >
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label={t('aisle_locations.field_code')}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
            fullWidth
            autoFocus
            data-testid="physical-location-code"
          />
          <TextField
            label={t('aisle_locations.field_display_name')}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            fullWidth
          />
          <TextField
            label={t('aisle_locations.field_description')}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            fullWidth
            multiline
            minRows={2}
          />
        </Stack>
      </BaseDialog>

      {/* Edit */}
      <BaseDialog
        open={Boolean(editLocation)}
        onClose={() => !updateMutation.isPending && setEditLocation(null)}
        disableClose={updateMutation.isPending}
        title={t('aisle_locations.edit_title')}
        description={
          editLocation ? t('aisle_locations.edit_subtitle', { code: editLocation.code }) : undefined
        }
        error={formError || undefined}
        actions={
          <>
            <Button onClick={() => setEditLocation(null)} disabled={updateMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="contained"
              onClick={() => void handleUpdate()}
              disabled={updateMutation.isPending}
            >
              {t('common.save')}
            </Button>
          </>
        }
      >
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label={t('aisle_locations.field_display_name')}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            fullWidth
            autoFocus
          />
          <TextField
            label={t('aisle_locations.field_description')}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            fullWidth
            multiline
            minRows={2}
          />
        </Stack>
      </BaseDialog>

      {/* Generated label result */}
      <BaseDialog
        open={resultOpen}
        onClose={() => {
          if (generateBusy) return;
          setResultOpen(false);
          clearPreview();
        }}
        disableClose={generateBusy}
        title={t('aisle_locations.result_title')}
        description={t('aisle_locations.label_scope_help')}
        maxWidth="md"
        actions={
          <>
            <Button onClick={() => { setResultOpen(false); clearPreview(); }}>
              {t('common.close')}
            </Button>
            {caps.renderEnabled ? (
              <>
                <Button onClick={() => void handleReprint()} disabled={generateBusy}>
                  {t('aisle_locations.reprint')}
                </Button>
                <Button onClick={() => void handleDownload('PNG')} disabled={generateBusy}>
                  {t('aisle_locations.download_png')}
                </Button>
                <Button
                  variant="contained"
                  onClick={() => void handleDownload('PDF')}
                  disabled={generateBusy}
                >
                  {t('aisle_locations.download_pdf')}
                </Button>
              </>
            ) : null}
          </>
        }
      >
        {resultLabel && resultLocation ? (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography>
              <strong>{t('aisle_locations.field_code')}:</strong> {resultLocation.code}
            </Typography>
            <Typography>
              <strong>{t('aisle_locations.column_status')}:</strong> {String(resultLabel.status)}
            </Typography>
            <Typography>
              <strong>{t('aisle_locations.public_id')}:</strong> {resultLabel.public_identifier}
            </Typography>
            <Typography>
              <strong>{t('aisle_locations.issued_at')}:</strong> {resultLabel.generated_at}
            </Typography>
            <StatusBadge
              label={signatureLabel(String(resultLabel.signature_status ?? ''), t)}
              semantic={signatureSemantic(String(resultLabel.signature_status ?? ''))}
            />
            <FormControl size="small" sx={{ maxWidth: 280 }}>
              <InputLabel id="label-preset">{t('aisle_locations.preset')}</InputLabel>
              <Select
                labelId="label-preset"
                label={t('aisle_locations.preset')}
                value={preset}
                onChange={(e) => setPreset(String(e.target.value))}
              >
                {PRESETS.map((p) => (
                  <MenuItem key={p.code} value={p.code}>
                    {t(p.labelKey)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            {!caps.renderEnabled ? (
              <Alert severity="warning">{t('aisle_locations.render_disabled')}</Alert>
            ) : previewUrl ? (
              <Box
                component="img"
                src={previewUrl}
                alt={t('aisle_locations.preview')}
                data-testid="position-label-preview"
                sx={{ maxWidth: '100%', border: 1, borderColor: 'divider', borderRadius: 1 }}
              />
            ) : (
              <Typography color="text.secondary">{t('aisle_locations.preview_pending')}</Typography>
            )}
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {t('aisle_locations.phase_checklist_title')}
              </Typography>
              <Stack component="ul" sx={{ m: 0, pl: 2 }} spacing={0.5}>
                <Typography component="li" variant="body2">
                  ✓ {t('aisle_locations.check_location')}
                </Typography>
                <Typography component="li" variant="body2">
                  ✓ {t('aisle_locations.check_issued')}
                </Typography>
                <Typography component="li" variant="body2">
                  {payloadTypeOk ? '✓' : '✗'} {t('aisle_locations.check_payload')}
                </Typography>
                <Typography component="li" variant="body2">
                  {!payloadHasProductFields ? '✓' : '✗'} {t('aisle_locations.check_no_product')}
                </Typography>
                <Typography component="li" variant="body2">
                  {previewUrl ? '✓' : '○'} {t('aisle_locations.check_png')}
                </Typography>
              </Stack>
            </Box>
            {String(resultLabel.status).toUpperCase() === 'ACTIVE' ? (
              <Stack direction="row" spacing={1}>
                <Button size="small" onClick={() => setReplaceTarget(resultLabel)}>
                  {t('aisle_locations.replace_label')}
                </Button>
                <Button
                  size="small"
                  color="warning"
                  onClick={() => {
                    setInvalidateTarget(resultLabel);
                    setInvalidateReason('');
                  }}
                >
                  {t('aisle_locations.invalidate_label')}
                </Button>
              </Stack>
            ) : null}
          </Stack>
        ) : null}
      </BaseDialog>

      {/* Replace confirm */}
      <BaseDialog
        open={Boolean(replaceTarget)}
        onClose={() => !replaceMutation.isPending && setReplaceTarget(null)}
        disableClose={replaceMutation.isPending}
        title={t('aisle_locations.replace_confirm_title')}
        description={t('aisle_locations.replace_confirm_body')}
        actions={
          <>
            <Button onClick={() => setReplaceTarget(null)} disabled={replaceMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="contained"
              color="warning"
              disabled={replaceMutation.isPending}
              onClick={() => void handleConfirmReplace()}
            >
              {t('aisle_locations.replace_label')}
            </Button>
          </>
        }
      >
        <Typography variant="body2" color="text.secondary">
          {replaceTarget?.public_identifier}
        </Typography>
      </BaseDialog>
      {/* Invalidate confirm */}
      <BaseDialog
        open={Boolean(invalidateTarget)}
        onClose={() => !invalidateMutation.isPending && setInvalidateTarget(null)}
        disableClose={invalidateMutation.isPending}
        title={t('aisle_locations.invalidate_confirm_title')}
        description={t('aisle_locations.invalidate_confirm_body')}
        actions={
          <>
            <Button onClick={() => setInvalidateTarget(null)} disabled={invalidateMutation.isPending}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="contained"
              color="warning"
              disabled={invalidateMutation.isPending}
              onClick={() => void handleConfirmInvalidate()}
            >
              {t('aisle_locations.invalidate_label')}
            </Button>
          </>
        }
      >
        <TextField
          label={t('aisle_locations.invalidation_reason')}
          value={invalidateReason}
          onChange={(e) => setInvalidateReason(e.target.value)}
          fullWidth
          multiline
          minRows={2}
          sx={{ mt: 1 }}
        />
      </BaseDialog>

      {/* Batch */}
      <BaseDialog
        open={batchOpen}
        onClose={() => !batchBusy && setBatchOpen(false)}
        disableClose={batchBusy}
        title={t('aisle_locations.batch_title')}
        description={t('aisle_locations.batch_help')}
        maxWidth="sm"
        actions={
          <>
            <Button onClick={() => setBatchOpen(false)} disabled={batchBusy}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="contained"
              disabled={batchBusy}
              data-testid="physical-locations-batch-confirm"
              onClick={() => void handleBatchGenerate()}
            >
              {t('aisle_locations.batch_confirm')}
            </Button>
          </>
        }
      >
        <Stack spacing={2} sx={{ mt: 1 }}>
          <FormControl size="small" fullWidth>
            <InputLabel id="batch-preset">{t('aisle_locations.preset')}</InputLabel>
            <Select
              labelId="batch-preset"
              label={t('aisle_locations.preset')}
              value={batchPreset}
              onChange={(e) => setBatchPreset(String(e.target.value))}
            >
              {PRESETS.map((p) => (
                <MenuItem key={p.code} value={p.code}>
                  {t(p.labelKey)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControlLabel
            control={
              <Checkbox
                checked={batchEmitMissing}
                onChange={(e) => setBatchEmitMissing(e.target.checked)}
              />
            }
            label={t('aisle_locations.batch_emit_missing')}
          />
          <Alert severity="info">
            {t('aisle_locations.batch_summary', {
              selected: batchSelected.size,
              emit: batchEmitMissing
                ? t('aisle_locations.batch_will_emit')
                : t('aisle_locations.batch_use_existing'),
            })}
          </Alert>
          <Stack spacing={0.5} sx={{ maxHeight: 240, overflow: 'auto' }}>
            {locations.map((loc) => (
              <FormControlLabel
                key={loc.id}
                control={
                  <Checkbox
                    checked={batchSelected.has(loc.id)}
                    onChange={(e) => {
                      setBatchSelected((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(loc.id);
                        else next.delete(loc.id);
                        return next;
                      });
                    }}
                  />
                }
                label={`${loc.code}${loc.display_name ? ` — ${loc.display_name}` : ''}`}
              />
            ))}
          </Stack>
        </Stack>
      </BaseDialog>
    </>
  );
}
