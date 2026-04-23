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
  Typography,
} from '@mui/material';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { formatDate } from '../../../utils/formatDate';
import type {
  CaptureSessionGroupSummaryResponse,
  CaptureSessionResponse,
} from '../../../types/captureSession';
import {
  useAssignCaptureSessionGroupToExistingAisle,
  useAisleOptions,
  useCaptureSessionGroups,
  useComputeCaptureSessionGroups,
  useCreateAisleFromCaptureSessionGroup,
} from '../hooks/useCaptureSessions';

export interface ImportSessionGroupingPanelProps {
  inventoryId: string;
  sessionId: string;
  session: CaptureSessionResponse;
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
  const [assignGroupId, setAssignGroupId] = useState<string | null>(null);
  const [createGroupId, setCreateGroupId] = useState<string | null>(null);
  const [selectedAisleId, setSelectedAisleId] = useState('');
  const [newAisleCode, setNewAisleCode] = useState('');
  const [recomputeConfirmOpen, setRecomputeConfirmOpen] = useState(false);

  const aisleCodeById = useMemo(
    () => buildAisleCodeById(aislesQuery.data?.items),
    [aislesQuery.data?.items]
  );

  const groupingError = useMemo(() => {
    const err =
      groupsQuery.error ||
      computeGroups.error ||
      assignGroup.error ||
      createAisleForGroup.error;
    if (!err) return null;
    return resolveApiErrorMessage(err, 'errors.request_failed');
  }, [assignGroup.error, computeGroups.error, createAisleForGroup.error, groupsQuery.error]);

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
            disabled={computeGroups.isPending || assignGroup.isPending || createAisleForGroup.isPending}
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
    </Box>
  );
}
