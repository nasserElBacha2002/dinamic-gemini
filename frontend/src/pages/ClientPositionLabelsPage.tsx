/**
 * Client-scoped positioning labels — create / list / preview / download / invalidate.
 * No inventory or aisle selection.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useParams } from 'react-router-dom';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
import { pathToClient, ROUTE_CLIENTS } from '../constants/appRoutes';
import {
  createClientPositionLabel,
  downloadClientPositionLabelFile,
  fetchClientPositionLabelPreviewBlob,
  invalidateClientPositionLabel,
  listClientPositionLabels,
  type ClientPositionLabel,
} from '../api/clientPositionLabelsApi';
import { getPositionLabelUiCapabilities } from '../features/positionLabels/positionLabelCapabilities';
import { useClient } from '../hooks';

const PRESET = 'MM_100x100';

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
  const [resultLabel, setResultLabel] = useState<ClientPositionLabel | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [invalidateTarget, setInvalidateTarget] = useState<ClientPositionLabel | null>(null);
  const [invalidateReason, setInvalidateReason] = useState('');
  const [search, setSearch] = useState('');

  const clientQuery = useClient(safeClientId || undefined, { enabled: Boolean(safeClientId) });

  const listQuery = useQuery({
    queryKey: ['clients', safeClientId, 'position-labels', search],
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
    mutationFn: () =>
      createClientPositionLabel(safeClientId, {
        name: name.trim(),
        description: description.trim() || null,
      }),
    onSuccess: async (label) => {
      setCreateOpen(false);
      setName('');
      setDescription('');
      setResultLabel(label);
      await queryClient.invalidateQueries({
        queryKey: ['clients', safeClientId, 'position-labels'],
      });
      showSnackbar(t('position_labels.created_snackbar'), 'success');
      if (caps.renderEnabled) {
        await loadPreview(label);
      }
    },
    onError: () => showSnackbar(t('position_labels.create_error'), 'error'),
  });

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
        queryKey: ['clients', safeClientId, 'position-labels'],
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
          <Table size="small" data-testid="position-labels-table">
            <TableHead>
              <TableRow>
                <TableCell>{t('position_labels.col_name')}</TableCell>
                <TableCell>{t('position_labels.col_description')}</TableCell>
                <TableCell>{t('position_labels.col_id')}</TableCell>
                <TableCell>{t('position_labels.col_status')}</TableCell>
                <TableCell>{t('position_labels.col_created')}</TableCell>
                <TableCell align="right">{t('position_labels.col_actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((label) => (
                <TableRow key={label.id}>
                  <TableCell>{label.name}</TableCell>
                  <TableCell>{label.description || t('common.em_dash')}</TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                      {label.public_identifier}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      label={
                        label.status === 'ACTIVE'
                          ? t('position_labels.status_active')
                          : t('position_labels.status_invalidated')
                      }
                      semantic={statusSemantic(label.status)}
                    />
                  </TableCell>
                  <TableCell>{new Date(label.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right">
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
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
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
            required
            label={t('position_labels.field_name')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            inputProps={{ 'data-testid': 'position-label-name-input' }}
          />
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
            disabled={!name.trim() || createMutation.isPending}
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
