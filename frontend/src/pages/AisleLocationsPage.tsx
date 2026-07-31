/**
 * Minimal Phase 1 UI for physical aisle locations + positioning labels.
 * Not CV positions — shelf/rack/slot labels with DINAMIC_POSITION payload.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Chip,
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
import { pathToAislePositions, pathToInventory, ROUTE_HOME } from '../constants/appRoutes';
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
  fetchAisleLocationLabelPreviewBlob,
} from '../api/client';
import { resolveApiErrorMessage } from '../utils/apiErrors';

export default function AisleLocationsPage() {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
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

  const inventoryQuery = useInventoryDetail(safeInv || undefined);
  const aislesQuery = useAislesList(safeInv || undefined, { enabled: Boolean(safeInv) });
  const aisle = useMemo(
    () => (aislesQuery.data?.items ?? []).find((a) => a.id === safeAisle) ?? null,
    [aislesQuery.data?.items, safeAisle]
  );

  const locationsQuery = useAisleLocations(safeInv || undefined, safeAisle || undefined);
  const locations = locationsQuery.data?.items ?? [];
  const selected =
    locations.find((loc) => loc.id === selectedLocationId) ?? locations[0] ?? null;
  const effectiveSelectedId = selected?.id ?? null;

  const labelsQuery = useAisleLocationLabels(safeInv || undefined, effectiveSelectedId ?? undefined, {
    enabled: Boolean(effectiveSelectedId),
  });
  const labels = labelsQuery.data?.items ?? [];

  const createMutation = useCreateAisleLocation(safeInv, safeAisle);
  const updateMutation = useUpdateAisleLocation(safeInv, safeAisle);
  const issueMutation = useIssueAisleLocationLabel(safeInv, safeAisle);
  const invalidateMutation = useInvalidateAisleLocationLabel(safeInv, safeAisle);
  const renderMutation = useRenderAisleLocationLabel(safeInv, safeAisle);
  const replaceMutation = useReplaceAisleLocationLabel(safeInv, safeAisle);

  const breadcrumbs = [
    { label: t('aisle.breadcrumb_inventories'), to: ROUTE_HOME },
    {
      label: inventoryQuery.data?.name ?? t('common.em_dash'),
      to: pathToInventory(safeInv),
    },
    {
      label: aisle?.code ?? t('common.em_dash'),
      to: pathToAislePositions(safeInv, safeAisle),
    },
    { label: t('aisle_locations.page_title') },
  ];

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

  const handleIssueLabel = async (locationId: string) => {
    try {
      await issueMutation.mutateAsync({ locationId });
      showSnackbar(t('aisle_locations.label_issued_snackbar'), 'success');
      setSelectedLocationId(locationId);
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisle_locations.label_issue_error'), 'error');
    }
  };

  const handleInvalidateLabel = async (label: AisleLocationLabel) => {
    try {
      await invalidateMutation.mutateAsync({
        locationId: label.location_id,
        labelId: label.id,
      });
      showSnackbar(t('aisle_locations.label_invalidated_snackbar'), 'success');
    } catch (e) {
      showSnackbar(resolveApiErrorMessage(e, 'aisle_locations.label_invalidate_error'), 'error');
    }
  };

  if (!safeInv || !safeAisle) {
    return <ErrorAlert message={t('aisle_locations.missing_route_params')} />;
  }

  if (inventoryQuery.isLoading || aislesQuery.isLoading) {
    return <LoadingBlock />;
  }

  return (
    <>
      <PageHeader
        breadcrumbs={breadcrumbs}
        title={t('aisle_locations.page_title')}
        subtitle={t('aisle_locations.page_subtitle', { aisle: aisle?.code ?? safeAisle })}
        actions={
          <Button variant="contained" size="small" onClick={openCreate}>
            {t('aisle_locations.create')}
          </Button>
        }
      />

      <Box sx={{ display: 'grid', gap: 2 }}>
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
                      </Box>
                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Button size="small" variant="outlined" onClick={() => setSelectedLocationId(loc.id)}>
                          {t('aisle_locations.view_labels')}
                        </Button>
                        <Button size="small" onClick={() => openEdit(loc)}>
                          {t('aisle_locations.edit')}
                        </Button>
                        <Button size="small" onClick={() => void toggleStatus(loc)}>
                          {loc.status === 'ACTIVE'
                            ? t('aisle_locations.deactivate')
                            : t('aisle_locations.activate')}
                        </Button>
                        <Button
                          size="small"
                          variant="contained"
                          disabled={loc.status !== 'ACTIVE' || issueMutation.isPending}
                          onClick={() => void handleIssueLabel(loc.id)}
                        >
                          {t('aisle_locations.issue_label')}
                        </Button>
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
                    </Box>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      <Button
                        size="small"
                        disabled={renderMutation.isPending}
                        onClick={() => {
                          void renderMutation
                            .mutateAsync({
                              labelId: label.id,
                              format: 'PNG',
                              preset: 'MM_100x100',
                            })
                            .then(async () => {
                              showSnackbar(t('aisle_locations.render_ok'), 'success');
                              const blob = await fetchAisleLocationLabelPreviewBlob(
                                safeInv,
                                label.id,
                                { format: 'PNG', preset: 'MM_100x100' }
                              );
                              const objectUrl = URL.createObjectURL(blob);
                              window.open(objectUrl, '_blank', 'noopener,noreferrer');
                              window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
                            })
                            .catch((err: unknown) => {
                              showSnackbar(
                                resolveApiErrorMessage(err, 'aisle_locations.label_issue_error'),
                                'error'
                              );
                            });
                        }}
                      >
                        {t('aisle_locations.preview')}
                      </Button>
                      <Button
                        size="small"
                        disabled={renderMutation.isPending}
                        onClick={() => {
                          void renderMutation
                            .mutateAsync({
                              labelId: label.id,
                              format: 'PDF',
                              preset: 'MM_100x100',
                            })
                            .then(async () => {
                              showSnackbar(t('aisle_locations.render_ok'), 'success');
                              await downloadAisleLocationLabelFile(safeInv, label.id, {
                                format: 'PDF',
                                preset: 'MM_100x100',
                              });
                            })
                            .catch((err: unknown) => {
                              showSnackbar(
                                resolveApiErrorMessage(err, 'aisle_locations.label_issue_error'),
                                'error'
                              );
                            });
                        }}
                      >
                        {t('aisle_locations.download_pdf')}
                      </Button>
                      {label.status === 'ACTIVE' ? (
                        <Button
                          size="small"
                          disabled={replaceMutation.isPending}
                          onClick={() => {
                            void replaceMutation
                              .mutateAsync({ labelId: label.id })
                              .then(() => showSnackbar(t('aisle_locations.replace_ok'), 'success'))
                              .catch((err: unknown) =>
                                showSnackbar(
                                  resolveApiErrorMessage(err, 'aisle_locations.label_issue_error'),
                                  'error'
                                )
                              );
                          }}
                        >
                          {t('aisle_locations.replace_label')}
                        </Button>
                      ) : null}
                      {label.status === 'ACTIVE' ? (
                        <Button
                          size="small"
                          color="warning"
                          disabled={invalidateMutation.isPending}
                          onClick={() => void handleInvalidateLabel(label)}
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
                </Box>
              ))}
            </Stack>
          )}
        </SectionCard>

        <Alert severity="info">{t('aisle_locations.cv_positions_note')}</Alert>
      </Box>

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

      <BaseDialog
        open={Boolean(editLocation)}
        onClose={() => !updateMutation.isPending && setEditLocation(null)}
        disableClose={updateMutation.isPending}
        title={t('aisle_locations.edit_title')}
        description={editLocation ? t('aisle_locations.edit_subtitle', { code: editLocation.code }) : undefined}
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
    </>
  );
}
