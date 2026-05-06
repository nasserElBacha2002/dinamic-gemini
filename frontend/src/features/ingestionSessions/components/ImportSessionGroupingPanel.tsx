import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormHelperText,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getVisibleErrorMessage, resolveApiErrorMessage } from '../../../utils/apiErrors';
import { formatDate } from '../../../utils/formatDate';
import type {
  CaptureSessionGroupSummaryResponse,
  CaptureSessionItemResponse,
  CaptureSessionResponse,
  MaterializedCaptureSessionGroupPreviewResponse,
} from '../../../types/captureSession';
import {
  useAssignCaptureSessionGroupToExistingAisle,
  useAisleOptions,
  useCaptureSessionGroups,
  useComputeCaptureSessionGroups,
  useCreateAisleFromCaptureSessionGroup,
  useMaterializeCaptureSessionGroup,
  usePreviewMaterializedCaptureSessionGroup,
} from '../hooks/useCaptureSessions';
import { heuristicGroupPreviewCtaBlockedReasonKey } from '../utils/groupingPreviewGate';

export interface ImportSessionGroupingPanelProps {
  inventoryId: string;
  sessionId: string;
  session: CaptureSessionResponse;
  items: CaptureSessionItemResponse[];
  ungroupedCount: number;
  onRefresh: () => void;
}

function captureSessionAllowsTemporalGrouping(session: CaptureSessionResponse): boolean {
  if (!session.closed_at) return false;
  return !['cancelled', 'failed', 'confirmed'].includes(session.status);
}

function groupAssignmentChip(
  g: CaptureSessionGroupSummaryResponse,
  t: (key: string) => string
): { label: string; color: 'default' | 'success' | 'warning' } {
  const st = g.assignment_status ?? 'unassigned';
  if (st === 'assigned_existing') {
    return { label: t('ingestion_sessions.detail.grouping_assignment_existing'), color: 'success' };
  }
  if (st === 'assigned_new') {
    return { label: t('ingestion_sessions.detail.grouping_assignment_new'), color: 'success' };
  }
  return { label: t('ingestion_sessions.detail.grouping_assignment_unassigned'), color: 'warning' };
}

function hasAnyAssignedGroup(groups: CaptureSessionGroupSummaryResponse[] | undefined): boolean {
  return (groups ?? []).some((g) => (g.assignment_status ?? 'unassigned') !== 'unassigned');
}

function buildAisleCodeById(
  items: { id: string; code: string }[] | undefined
): Map<string, string> {
  const m = new Map<string, string>();
  for (const a of items ?? []) {
    m.set(a.id, a.code);
  }
  return m;
}

export default function ImportSessionGroupingPanel({
  inventoryId,
  sessionId,
  session,
  items,
  ungroupedCount,
  onRefresh,
}: ImportSessionGroupingPanelProps) {
  const { t } = useTranslation();
  const groupingEnabled = captureSessionAllowsTemporalGrouping(session);
  const groupsQuery = useCaptureSessionGroups(inventoryId, sessionId, { enabled: groupingEnabled });
  const aislesQuery = useAisleOptions(inventoryId, { enabled: groupingEnabled });
  const computeGroups = useComputeCaptureSessionGroups();
  const assignGroup = useAssignCaptureSessionGroupToExistingAisle();
  const createAisleForGroup = useCreateAisleFromCaptureSessionGroup();
  const materializeGroup = useMaterializeCaptureSessionGroup();
  const previewGroup = usePreviewMaterializedCaptureSessionGroup();
  const [assignGroupId, setAssignGroupId] = useState<string | null>(null);
  const [createGroupId, setCreateGroupId] = useState<string | null>(null);
  const [selectedAisleId, setSelectedAisleId] = useState('');
  const [newAisleCode, setNewAisleCode] = useState('');
  const [recomputeConfirmOpen, setRecomputeConfirmOpen] = useState(false);
  const [previewGroupId, setPreviewGroupId] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<MaterializedCaptureSessionGroupPreviewResponse | null>(null);
  /** Surfaces ``mutateAsync`` rejections even when test mocks omit TanStack ``mutation.error`` updates. */
  const [previewActionError, setPreviewActionError] = useState<string | null>(null);

  const aisleCodeById = useMemo(
    () => buildAisleCodeById(aislesQuery.data?.items),
    [aislesQuery.data?.items]
  );

  const groupingError = useMemo(() => {
    const err =
      groupsQuery.error ||
      computeGroups.error ||
      assignGroup.error ||
      createAisleForGroup.error ||
      materializeGroup.error ||
      previewGroup.error;
    const fromQuery = err ? resolveApiErrorMessage(err, 'errors.request_failed') : null;
    return fromQuery || previewActionError;
  }, [
    assignGroup.error,
    computeGroups.error,
    createAisleForGroup.error,
    groupsQuery.error,
    materializeGroup.error,
    previewGroup.error,
    previewActionError,
  ]);

  const aisleItems = aislesQuery.data?.items ?? [];
  const assignBlockedNoAisles = assignGroupId != null && aisleItems.length === 0;

  const runCompute = () => {
    void computeGroups.mutateAsync({ inventoryId, sessionId }).then(() => {
      onRefresh();
    });
  };

  const requestCompute = () => {
    const groups = groupsQuery.data?.groups ?? [];
    if (hasAnyAssignedGroup(groups)) {
      setRecomputeConfirmOpen(true);
      return;
    }
    runCompute();
  };

  const confirmRecompute = () => {
    setRecomputeConfirmOpen(false);
    runCompute();
  };

  const assignedAisleLabel = (g: CaptureSessionGroupSummaryResponse): string | null => {
    const id = g.assigned_aisle_id;
    if (!id) return null;
    const code = aisleCodeById.get(id);
    if (code) {
      return t('ingestion_sessions.detail.grouping_assigned_aisle_code', { code });
    }
    return t('ingestion_sessions.detail.grouping_assigned_aisle_id_only', { id });
  };

  return (
    <Box>
      <Typography variant="subtitle1" gutterBottom>
        {t('ingestion_sessions.detail.grouping_title')}
      </Typography>
      {!groupingEnabled ? (
        <Typography variant="body2" color="text.secondary">
          {['cancelled', 'failed', 'confirmed'].includes(session.status)
            ? t('ingestion_sessions.detail.grouping_hint_blocked')
            : t('ingestion_sessions.detail.grouping_hint_close')}
        </Typography>
      ) : (
        <Stack spacing={1}>
          <Button
            variant="outlined"
            disabled={
              computeGroups.isPending ||
              assignGroup.isPending ||
              createAisleForGroup.isPending ||
              materializeGroup.isPending ||
              previewGroup.isPending
            }
            onClick={requestCompute}
          >
            {t('ingestion_sessions.detail.grouping_compute')}
          </Button>
          {groupingError ? <Alert severity="error">{groupingError}</Alert> : null}
          {groupsQuery.isLoading ? (
            <Typography variant="body2" color="text.secondary">
              {t('ingestion_sessions.detail.grouping_loading')}
            </Typography>
          ) : null}
          {!groupsQuery.isLoading && (groupsQuery.data?.groups.length ?? 0) === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t('ingestion_sessions.detail.grouping_empty')}
            </Typography>
          ) : null}
          {(groupsQuery.data?.groups ?? []).map((g) => {
            const chip = groupAssignmentChip(g, t);
            const unassigned = (g.assignment_status ?? 'unassigned') === 'unassigned';
            const aisleLine = !unassigned ? assignedAisleLabel(g) : null;
            const previewBlockReason = heuristicGroupPreviewCtaBlockedReasonKey(g, items);
            const previewDisabled =
              !!previewBlockReason || previewGroup.isPending || materializeGroup.isPending;
            return (
              <Box
                key={g.group_id}
                sx={{
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1,
                  p: 1,
                }}
              >
                <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" sx={{ mb: 0.5 }}>
                  <Chip size="small" label={chip.label} color={chip.color} variant="outlined" />
                  {unassigned ? (
                    <>
                      <Button
                        size="small"
                        variant="text"
                        onClick={() => {
                          setSelectedAisleId('');
                          setAssignGroupId(g.group_id);
                        }}
                      >
                        {t('ingestion_sessions.detail.grouping_assign_existing')}
                      </Button>
                      <Button
                        size="small"
                        variant="text"
                        onClick={() => {
                          setNewAisleCode('');
                          setCreateGroupId(g.group_id);
                        }}
                      >
                        {t('ingestion_sessions.detail.grouping_create_aisle')}
                      </Button>
                    </>
                  ) : null}
                </Stack>
                {aisleLine ? (
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                    {aisleLine}
                  </Typography>
                ) : null}
                <Typography variant="body2">
                  {t('ingestion_sessions.detail.grouping_row', {
                    index: g.group_index,
                    count: g.item_count,
                    start: formatDate(g.start_time),
                    end: formatDate(g.end_time),
                  })}
                </Typography>
                {!unassigned ? (
                  <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 0.5 }} alignItems="center">
                    <Tooltip title={previewBlockReason ? t(previewBlockReason) : ''}>
                      <span>
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={previewDisabled}
                          onClick={() => {
                            setPreviewActionError(null);
                            void previewGroup
                              .mutateAsync({
                                inventoryId,
                                sessionId,
                                groupId: g.group_id,
                              })
                              .then((data) => {
                                setPreviewActionError(null);
                                setPreviewData(data);
                                setPreviewGroupId(g.group_id);
                              })
                              .catch((e: unknown) => {
                                setPreviewActionError(getVisibleErrorMessage(e, 'ingestionSession'));
                              });
                          }}
                        >
                          {t('ingestion_sessions.detail.grouping_preview')}
                        </Button>
                      </span>
                    </Tooltip>
                    <Button
                      size="small"
                      variant="text"
                      disabled={materializeGroup.isPending || previewGroup.isPending}
                      onClick={() =>
                        void materializeGroup
                          .mutateAsync({
                            inventoryId,
                            sessionId,
                            groupId: g.group_id,
                          })
                          .then(() => {
                            onRefresh();
                          })
                      }
                    >
                      {t('ingestion_sessions.detail.grouping_materialize')}
                    </Button>
                  </Stack>
                ) : null}
              </Box>
            );
          })}
          {ungroupedCount > 0 ? (
            <Typography variant="caption" color="text.secondary" display="block">
              {t('ingestion_sessions.detail.grouping_ungrouped', { count: ungroupedCount })}
            </Typography>
          ) : null}
        </Stack>
      )}

      <Dialog open={recomputeConfirmOpen} onClose={() => setRecomputeConfirmOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('ingestion_sessions.detail.grouping_recompute_confirm_title')}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mt: 1 }}>
            {t('ingestion_sessions.detail.grouping_recompute_confirm_body')}
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRecomputeConfirmOpen(false)}>
            {t('ingestion_sessions.detail.grouping_recompute_confirm_cancel')}
          </Button>
          <Button color="warning" variant="contained" onClick={confirmRecompute}>
            {t('ingestion_sessions.detail.grouping_recompute_confirm_proceed')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={assignGroupId != null} onClose={() => setAssignGroupId(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('ingestion_sessions.detail.grouping_assign_dialog_title')}</DialogTitle>
        <DialogContent>
          <FormControl fullWidth margin="normal" size="small" error={assignBlockedNoAisles}>
            <InputLabel id="assign-aisle-label">{t('ingestion_sessions.detail.grouping_assign_select_aisle')}</InputLabel>
            <Select
              labelId="assign-aisle-label"
              label={t('ingestion_sessions.detail.grouping_assign_select_aisle')}
              value={selectedAisleId}
              onChange={(e) => setSelectedAisleId(e.target.value)}
              disabled={assignBlockedNoAisles}
            >
              {aisleItems.map((a) => (
                <MenuItem key={a.id} value={a.id}>
                  {a.code}
                </MenuItem>
              ))}
            </Select>
            {assignBlockedNoAisles ? (
              <FormHelperText>{t('ingestion_sessions.detail.grouping_assign_no_aisles_helper')}</FormHelperText>
            ) : null}
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAssignGroupId(null)}>{t('ingestion_sessions.detail.grouping_assign_dialog_cancel')}</Button>
          <Button
            variant="contained"
            disabled={
              !selectedAisleId.trim() || assignGroup.isPending || !assignGroupId || assignBlockedNoAisles
            }
            onClick={() => {
              const aisleId = selectedAisleId.trim();
              if (!assignGroupId || !aisleId || assignBlockedNoAisles) return;
              void assignGroup
                .mutateAsync({
                  inventoryId,
                  sessionId,
                  groupId: assignGroupId,
                  aisleId,
                })
                .then(() => {
                  setAssignGroupId(null);
                  onRefresh();
                });
            }}
          >
            {t('ingestion_sessions.detail.grouping_assign_dialog_confirm')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={createGroupId != null} onClose={() => setCreateGroupId(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t('ingestion_sessions.detail.grouping_create_dialog_title')}</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            margin="normal"
            size="small"
            label={t('ingestion_sessions.detail.grouping_create_dialog_code_label')}
            value={newAisleCode}
            onChange={(e) => setNewAisleCode(e.target.value)}
            helperText={t('ingestion_sessions.detail.grouping_create_code_helper')}
            inputProps={{ maxLength: 64 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateGroupId(null)}>{t('ingestion_sessions.detail.grouping_assign_dialog_cancel')}</Button>
          <Button
            variant="contained"
            disabled={
              !newAisleCode.trim() ||
              newAisleCode.trim().length > 64 ||
              createAisleForGroup.isPending ||
              !createGroupId
            }
            onClick={() => {
              if (!createGroupId) return;
              const code = newAisleCode.trim();
              if (code.length < 1 || code.length > 64) return;
              void createAisleForGroup
                .mutateAsync({
                  inventoryId,
                  sessionId,
                  groupId: createGroupId,
                  code,
                })
                .then(() => {
                  setCreateGroupId(null);
                  onRefresh();
                });
            }}
          >
            {t('ingestion_sessions.detail.grouping_create_dialog_confirm')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={previewGroupId != null}
        onClose={() => {
          setPreviewGroupId(null);
          setPreviewData(null);
          setPreviewActionError(null);
        }}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>{t('ingestion_sessions.detail.grouping_preview_dialog_title')}</DialogTitle>
        <DialogContent>
          {previewData ? (
            <Stack spacing={1.5} sx={{ mt: 0.5 }}>
              <Typography variant="body2" color="text.secondary">
                {t('ingestion_sessions.detail.grouping_preview_trace_session', {
                  id: previewData.capture_session_id,
                })}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('ingestion_sessions.detail.grouping_preview_meta', {
                  aisle: previewData.aisle_id,
                  assets: previewData.source_asset_count,
                  status: previewData.preview_status,
                })}
              </Typography>
              {previewData.preview_status === 'empty' ? (
                <Alert severity="info">{t('ingestion_sessions.detail.grouping_preview_empty_hint')}</Alert>
              ) : null}
              <Typography variant="subtitle2">
                {t('ingestion_sessions.detail.grouping_preview_summary', {
                  proposed: previewData.summary.proposed_count,
                  conflicts: previewData.summary.conflict_count,
                  unassigned: previewData.summary.unassigned_count,
                  items: previewData.summary.previewed_item_count,
                })}
              </Typography>
              {previewData.items.map((row) => (
                <Box
                  key={`${row.source_asset_id}-${row.capture_session_item_id}`}
                  sx={{
                    borderLeft: 2,
                    borderColor: 'divider',
                    pl: 1,
                  }}
                >
                  <Typography variant="body2" component="div">
                    {t('ingestion_sessions.detail.grouping_preview_row_status', { status: row.assignment_status })}
                  </Typography>
                  <Typography variant="body2" component="div" sx={{ wordBreak: 'break-all' }}>
                    {t('ingestion_sessions.detail.grouping_preview_row_reason', { reason: row.assignment_reason })}
                  </Typography>
                  <Typography variant="body2" component="div" sx={{ wordBreak: 'break-all' }}>
                    {t('ingestion_sessions.detail.grouping_preview_row_item', { id: row.capture_session_item_id })}
                  </Typography>
                  <Typography variant="body2" component="div" sx={{ wordBreak: 'break-all' }}>
                    {t('ingestion_sessions.detail.grouping_preview_row_asset', { id: row.source_asset_id })}
                  </Typography>
                  {row.preview_target_position_id ? (
                    <Typography variant="body2" component="div" sx={{ wordBreak: 'break-all' }}>
                      {t('ingestion_sessions.detail.grouping_preview_row_position', {
                        id: row.preview_target_position_id,
                      })}
                    </Typography>
                  ) : null}
                  {row.adjusted_capture_time ? (
                    <Typography variant="body2" component="div">
                      {t('ingestion_sessions.detail.grouping_preview_row_time', {
                        time: formatDate(row.adjusted_capture_time),
                      })}
                    </Typography>
                  ) : null}
                </Box>
              ))}
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setPreviewGroupId(null);
              setPreviewData(null);
              setPreviewActionError(null);
            }}
          >
            {t('ingestion_sessions.detail.grouping_assign_dialog_cancel')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
