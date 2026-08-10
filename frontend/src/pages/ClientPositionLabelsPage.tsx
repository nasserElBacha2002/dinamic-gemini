/**
 * Client-scoped positioning labels — create / list / preview / download / invalidate.
 * No inventory or aisle selection.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { PageHeader } from '../components/shell';
import {
  BaseDialog,
  DataTable,
  EmptyState,
  ErrorAlert,
  LoadingBlock,
  SectionCard,
  StatusBadge,
  useAppSnackbar,
} from '../components/ui';
import { pathToClient, ROUTE_CLIENTS } from '../constants/appRoutes';
import {
  createClientPositionLabel,
  createClientPositionMarkerSet,
  downloadClientPositionLabelFile,
  fetchClientPositionLabelPreviewBlob,
  invalidateClientPositionLabel,
  listClientPositionLabels,
  type ClientPositionLabel,
} from '../api/clientPositionLabelsApi';
import { queryKeys } from '../api/queryKeys';
import { getPositionLabelUiCapabilities } from '../features/positionLabels/positionLabelCapabilities';
import { useClient } from '../hooks';
import { resolveApiErrorMessage } from '../utils/apiErrors';

const PRESET = 'MM_100x100';

function newIdempotencyKey(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function statusSemantic(status: string): 'success' | 'warning' | 'neutral' {
  if (status === 'ACTIVE') return 'success';
  if (status === 'INVALIDATED') return 'warning';
  return 'neutral';
}

export default function ClientPositionLabelsPage() {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const queryClient = useQueryClient();
  const { clientId } = useParams<{ clientId: string }>();
  const safeClientId = (clientId ?? '').trim();
  const caps = useMemo(() => getPositionLabelUiCapabilities(), []);

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [pallet, setPallet] = useState('');
  const [side, setSide] = useState<'LEFT' | 'RIGHT'>('LEFT');
  const [level, setLevel] = useState('1');
  const [markerTotal, setMarkerTotal] = useState('1');
  const [createMode, setCreateMode] = useState<'legacy' | 'hierarchy'>('hierarchy');
  const [resultLabel, setResultLabel] = useState<ClientPositionLabel | null>(null);
  const [resultSet, setResultSet] = useState<ClientPositionLabel[] | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [invalidateTarget, setInvalidateTarget] = useState<ClientPositionLabel | null>(null);
  const [invalidateReason, setInvalidateReason] = useState('');
  const [search, setSearch] = useState('');
  const createIdempotencyKeyRef = useRef(newIdempotencyKey('pos-marker-set'));

  const clientQuery = useClient(safeClientId || undefined, { enabled: Boolean(safeClientId) });

  const listQuery = useQuery({
    queryKey: queryKeys.clients.positionLabels.list(safeClientId, search),
    queryFn: () =>
      listClientPositionLabels(safeClientId, {
        page: 1,
        page_size: 100,
        search: search.trim() || null,
      }),
    enabled: Boolean(safeClientId) && caps.labelsEnabled,
  });

  const revokePreview = useCallback(() => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
  }, [previewUrl]);

  useEffect(() => () => revokePreview(), [revokePreview]);

  const loadPreview = useCallback(
    async (label: ClientPositionLabel) => {
      revokePreview();
      try {
        const blob = await fetchClientPositionLabelPreviewBlob(safeClientId, label.id, {
          format: 'PNG',
          preset: PRESET,
        });
        setPreviewUrl(URL.createObjectURL(blob));
      } catch {
        showSnackbar(t('position_labels.preview_error'), 'error');
      }
    },
    [revokePreview, safeClientId, showSnackbar, t]
  );

  const createMutation = useMutation({
    mutationFn: async () => {
      if (createMode === 'hierarchy') {
        const levelNum = Number.parseInt(level, 10);
        const totalNum = Number.parseInt(markerTotal, 10);
        return createClientPositionMarkerSet(
          safeClientId,
          {
            pallet: pallet.trim(),
            side,
            level: levelNum,
            marker_total: totalNum,
            description: description.trim() || null,
          },
          { idempotencyKey: createIdempotencyKeyRef.current }
        );
      }
      const label = await createClientPositionLabel(
        safeClientId,
        {
          name: name.trim(),
          description: description.trim() || null,
        },
        { idempotencyKey: createIdempotencyKeyRef.current }
      );
      return { items: [label] };
    },
    onSuccess: async (payload) => {
      setCreateOpen(false);
      setName('');
      setDescription('');
      setPallet('');
      setLevel('1');
      setMarkerTotal('1');
      setSide('LEFT');
      createIdempotencyKeyRef.current = newIdempotencyKey('pos-marker-set');
      const itemsCreated = payload.items ?? [];
      setResultSet(itemsCreated.length > 1 ? itemsCreated : null);
      setResultLabel(itemsCreated[0] ?? null);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.clients.positionLabels.all(safeClientId),
      });
      showSnackbar(t('position_labels.created_snackbar'), 'success');
      if (caps.renderEnabled && itemsCreated[0]) {
        await loadPreview(itemsCreated[0]);
      }
    },
    onError: (error) =>
      showSnackbar(resolveApiErrorMessage(error, 'position_labels.create_error'), 'error'),
  });

  const canSubmitCreate =
    createMode === 'hierarchy'
      ? Boolean(pallet.trim()) &&
        Number.parseInt(level, 10) >= 1 &&
        Number.parseInt(markerTotal, 10) >= 1 &&
        Number.parseInt(markerTotal, 10) <= 99
      : Boolean(name.trim());

  const invalidateMutation = useMutation({
    mutationFn: () =>
      invalidateClientPositionLabel(
        safeClientId,
        invalidateTarget!.id,
        invalidateReason.trim() || null
      ),
    onSuccess: async () => {
      setInvalidateTarget(null);
      setInvalidateReason('');
      await queryClient.invalidateQueries({
        queryKey: queryKeys.clients.positionLabels.all(safeClientId),
      });
      showSnackbar(t('position_labels.invalidated_snackbar'), 'success');
    },
    onError: () => showSnackbar(t('position_labels.invalidate_error'), 'error'),
  });

  const download = async (label: ClientPositionLabel, format: 'PDF' | 'PNG') => {
    try {
      await downloadClientPositionLabelFile(safeClientId, label.id, { format, preset: PRESET });
      showSnackbar(t('position_labels.download_ok'), 'success');
    } catch {
      showSnackbar(t('position_labels.download_error'), 'error');
    }
  };

  const reprint = async (label: ClientPositionLabel) => {
    try {
      await loadPreview(label);
      showSnackbar(t('position_labels.reprint_ok'), 'success');
    } catch {
      showSnackbar(t('position_labels.reprint_error'), 'error');
    }
  };

  if (!safeClientId) {
    return <ErrorAlert message={t('clients.detail.invalid')} />;
  }

  if (!caps.labelsEnabled) {
    return (
      <EmptyState
        title={t('position_labels.disabled_title')}
        message={t('position_labels.disabled_message')}
      />
    );
  }

  const items = listQuery.data?.items ?? [];

  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: t('clients.breadcrumb_list'), to: ROUTE_CLIENTS },
          {
            label: clientQuery.data?.name ?? t('common.em_dash'),
            to: pathToClient(safeClientId),
          },
          { label: t('position_labels.title') },
        ]}
        title={t('position_labels.title')}
        subtitle={t('position_labels.subtitle')}
        actions={
          <Button
            variant="contained"
            size="small"
            onClick={() => setCreateOpen(true)}
            data-testid="position-label-new"
          >
            {t('position_labels.new')}
          </Button>
        }
      />

      <SectionCard title={t('position_labels.list_title')}>
        <TextField
          size="small"
          label={t('position_labels.search')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ mb: 2, maxWidth: 360 }}
          data-testid="position-label-search"
        />
        {listQuery.isLoading ? <LoadingBlock /> : null}
        {listQuery.isError ? (
          <ErrorAlert
            message={t('position_labels.list_error')}
            onRetry={() => listQuery.refetch()}
          />
        ) : null}
        {!listQuery.isLoading && items.length === 0 ? (
          <EmptyState
            title={t('position_labels.empty_title')}
            message={t('position_labels.empty_message')}
            action={
              <Button variant="contained" onClick={() => setCreateOpen(true)}>
                {t('position_labels.create_first')}
              </Button>
            }
          />
        ) : null}
        {items.length > 0 ? (
          <DataTable<ClientPositionLabel>
            rows={items}
            rowKey={(label) => label.id}
            testId="position-labels-table"
            columns={[
              {
                id: 'name',
                label: t('position_labels.col_name'),
                cell: (label) => label.name,
              },
              {
                id: 'description',
                label: t('position_labels.col_description'),
                cell: (label) => label.description || t('common.em_dash'),
              },
              {
                id: 'public_identifier',
                label: t('position_labels.col_id'),
                cell: (label) => (
                    <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                      {label.public_identifier}
                    </Typography>
                ),
              },
              {
                id: 'status',
                label: t('position_labels.col_status'),
                cell: (label) => (
                    <StatusBadge
                      label={
                        label.status === 'ACTIVE'
                          ? t('position_labels.status_active')
                          : t('position_labels.status_invalidated')
                      }
                      semantic={statusSemantic(label.status)}
                    />
                ),
              },
              {
                id: 'created_at',
                label: t('position_labels.col_created'),
                cell: (label) => new Date(label.created_at).toLocaleString(),
              },
              {
                id: 'actions',
                label: t('position_labels.col_actions'),
                align: 'right',
                cell: (label) => (
                    <Stack direction="row" spacing={0.5} justifyContent="flex-end" flexWrap="wrap">
                      {caps.renderEnabled && label.status === 'ACTIVE' ? (
                        <>
                          <Button size="small" onClick={() => loadPreview(label).then(() => setResultLabel(label))}>
                            {t('position_labels.preview')}
                          </Button>
                          <Button size="small" onClick={() => download(label, 'PDF')}>
                            {t('position_labels.download_pdf')}
                          </Button>
                          <Button size="small" onClick={() => download(label, 'PNG')}>
                            {t('position_labels.download_png')}
                          </Button>
                          <Button size="small" onClick={() => reprint(label)}>
                            {t('position_labels.reprint')}
                          </Button>
                        </>
                      ) : null}
                      {label.status === 'ACTIVE' ? (
                        <Button size="small" color="warning" onClick={() => setInvalidateTarget(label)}>
                          {t('position_labels.invalidate')}
                        </Button>
                      ) : null}
                    </Stack>
                ),
              },
            ]}
            mobile={{
              mode: 'horizontal-scroll',
              reason: 'Position label actions require the complete operational row.',
            }}
          />
        ) : null}
      </SectionCard>

      <BaseDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t('position_labels.create_title')}
        maxWidth="sm"
      >
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            select
            size="small"
            label={t('position_labels.create_mode', { defaultValue: 'Modo' })}
            value={createMode}
            onChange={(e) => setCreateMode(e.target.value as 'legacy' | 'hierarchy')}
            data-testid="position-label-create-mode"
          >
            <MenuItem value="hierarchy">
              {t('position_labels.mode_hierarchy', { defaultValue: 'Pallet / Lado / Nivel / Marbete' })}
            </MenuItem>
            <MenuItem value="legacy">
              {t('position_labels.mode_legacy', { defaultValue: 'Nombre libre (legacy)' })}
            </MenuItem>
          </TextField>

          {createMode === 'hierarchy' ? (
            <>
              <TextField
                required
                label={t('position_labels.field_pallet', { defaultValue: 'Pallet' })}
                value={pallet}
                onChange={(e) => setPallet(e.target.value)}
                inputProps={{ 'data-testid': 'position-label-pallet-input' }}
              />
              <TextField
                select
                required
                label={t('position_labels.field_side', { defaultValue: 'Lado' })}
                value={side}
                onChange={(e) => setSide(e.target.value as 'LEFT' | 'RIGHT')}
                inputProps={{ 'data-testid': 'position-label-side-input' }}
              >
                <MenuItem value="LEFT">{t('position_labels.side_left', { defaultValue: 'Izquierda' })}</MenuItem>
                <MenuItem value="RIGHT">{t('position_labels.side_right', { defaultValue: 'Derecha' })}</MenuItem>
              </TextField>
              <TextField
                required
                type="number"
                label={t('position_labels.field_level', { defaultValue: 'Nivel' })}
                value={level}
                onChange={(e) => setLevel(e.target.value)}
                inputProps={{ min: 1, 'data-testid': 'position-label-level-input' }}
              />
              <TextField
                required
                type="number"
                label={t('position_labels.field_marker_total', { defaultValue: 'Cantidad de marbetes' })}
                value={markerTotal}
                onChange={(e) => setMarkerTotal(e.target.value)}
                helperText={t('position_labels.marker_total_help', {
                  defaultValue: 'Genera 01/N … N/N con un label_id único cada uno',
                })}
                inputProps={{ min: 1, max: 99, 'data-testid': 'position-label-marker-total-input' }}
              />
            </>
          ) : (
            <TextField
              required
              label={t('position_labels.field_name')}
              value={name}
              onChange={(e) => setName(e.target.value)}
              inputProps={{ 'data-testid': 'position-label-name-input' }}
            />
          )}
          <TextField
            label={t('position_labels.field_description')}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            multiline
            minRows={2}
          />
        </Stack>
        <DialogActions sx={{ px: 0, pt: 2 }}>
          <Button onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!canSubmitCreate || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            data-testid="position-label-create-submit"
          >
            {t('position_labels.create_submit')}
          </Button>
        </DialogActions>
      </BaseDialog>

      <Dialog
        open={Boolean(resultLabel)}
        onClose={() => {
          setResultLabel(null);
          revokePreview();
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('position_labels.result_title')}</DialogTitle>
        <DialogContent>
          {resultLabel ? (
            <Stack spacing={1.5}>
              <Typography>
                {t('position_labels.result_location')}: <strong>{resultLabel.name}</strong>
              </Typography>
              {resultLabel.marker ? (
                <Typography data-testid="position-label-result-marker">
                  {t('position_labels.result_marker', { defaultValue: 'Marbete' })}:{' '}
                  <strong>{resultLabel.marker}</strong>
                </Typography>
              ) : null}
              {resultSet && resultSet.length > 1 ? (
                <Stack spacing={0.5} data-testid="position-label-result-set">
                  <Typography variant="body2" color="text.secondary">
                    {t('position_labels.result_set_count', {
                      defaultValue: '{{count}} marbetes generados',
                      count: resultSet.length,
                    })}
                  </Typography>
                  {resultSet.map((item) => (
                    <Typography
                      key={item.id}
                      variant="body2"
                      data-testid="position-label-result-set-marker"
                      sx={{
                        fontFamily:
                          'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                      }}
                    >
                      {item.marker ??
                        (item.marker_index != null && item.marker_total != null
                          ? `${String(item.marker_index).padStart(2, '0')}/${String(item.marker_total).padStart(2, '0')}`
                          : item.name)}
                      {item.public_identifier ? ` — ${item.id}` : ''}
                    </Typography>
                  ))}
                </Stack>
              ) : null}
              <Typography>
                {t('position_labels.result_client')}:{' '}
                <strong>{clientQuery.data?.name ?? safeClientId}</strong>
              </Typography>
              <Typography>
                {t('position_labels.result_status')}: <strong>{resultLabel.status}</strong>
              </Typography>
              {previewUrl ? (
                <Box
                  component="img"
                  src={previewUrl}
                  alt={t('position_labels.preview')}
                  sx={{ maxWidth: '100%', border: 1, borderColor: 'divider' }}
                  data-testid="position-label-preview-img"
                />
              ) : null}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          {resultLabel && caps.renderEnabled ? (
            <>
              <Button onClick={() => download(resultLabel, 'PDF')}>
                {t('position_labels.download_pdf')}
              </Button>
              <Button onClick={() => download(resultLabel, 'PNG')}>
                {t('position_labels.download_png')}
              </Button>
            </>
          ) : null}
          <Button
            onClick={() => {
              setResultLabel(null);
              revokePreview();
            }}
          >
            {t('common.close')}
          </Button>
        </DialogActions>
      </Dialog>

      <BaseDialog
        open={Boolean(invalidateTarget)}
        onClose={() => setInvalidateTarget(null)}
        title={t('position_labels.invalidate_title')}
        maxWidth="sm"
      >
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('position_labels.invalidate_body')}
        </Typography>
        <TextField
          select
          fullWidth
          label={t('position_labels.invalidate_reason')}
          value={invalidateReason}
          onChange={(e) => setInvalidateReason(e.target.value)}
        >
          <MenuItem value="">{t('position_labels.reason_none')}</MenuItem>
          <MenuItem value="damaged">{t('position_labels.reason_damaged')}</MenuItem>
          <MenuItem value="removed">{t('position_labels.reason_removed')}</MenuItem>
          <MenuItem value="wrong_code">{t('position_labels.reason_wrong_code')}</MenuItem>
          <MenuItem value="other">{t('position_labels.reason_other')}</MenuItem>
        </TextField>
        <DialogActions sx={{ px: 0, pt: 2 }}>
          <Button onClick={() => setInvalidateTarget(null)}>{t('common.cancel')}</Button>
          <Button
            color="warning"
            variant="contained"
            disabled={invalidateMutation.isPending}
            onClick={() => invalidateMutation.mutate()}
          >
            {t('position_labels.invalidate')}
          </Button>
        </DialogActions>
      </BaseDialog>
    </>
  );
}
