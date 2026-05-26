import { useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { postAdminStorageCleanup, type AdminStorageCleanupResponse } from '../api/adminStorageApi';
import { ApiError } from '../api/types';
import PageHeader from '../components/shell/PageHeader';
import { useAppSnackbar } from '../components/ui';

const CONFIRM_TOKEN = 'DELETE_INVENTORY_ARTIFACTS';

function formatBytes(bytes: number, locale: string): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString(locale, { maximumFractionDigits: 1 })} ${units[unit]}`;
}

function RemoteSummaryCard({
  section,
  locale,
}: {
  section: AdminStorageCleanupResponse['remote'];
  locale: string;
}) {
  const { t } = useTranslation();
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="subtitle1" gutterBottom>
          {t('admin_storage_cleanup.remote_section')}
        </Typography>
        {section.skipped ? (
          <Alert severity="info">{section.skip_reason ?? t('admin_storage_cleanup.skipped')}</Alert>
        ) : null}
        <Stack spacing={0.5}>
          <Typography variant="body2">
            {t('admin_storage_cleanup.provider')}: {section.provider}
          </Typography>
          <Typography variant="body2">
            {t('admin_storage_cleanup.bucket')}: {section.bucket ?? '—'}
          </Typography>
          <Typography variant="body2">
            {t('admin_storage_cleanup.prefix')}: {section.prefix ?? '—'}
          </Typography>
          <Typography variant="body2">
            {t('admin_storage_cleanup.objects_found')}: {section.objects_found}
          </Typography>
          <Typography variant="body2">
            {t('admin_storage_cleanup.objects_skipped_protected')}:{' '}
            {section.objects_skipped_protected ?? 0}
          </Typography>
          <Typography variant="body2">
            {t('admin_storage_cleanup.bytes_found')}: {formatBytes(section.bytes_found, locale)}
          </Typography>
        </Stack>
        {section.errors.length > 0 ? (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {section.errors.join('; ')}
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

function LocalSummaryCard({
  section,
  locale,
}: {
  section: AdminStorageCleanupResponse['local'];
  locale: string;
}) {
  const { t } = useTranslation();
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="subtitle1" gutterBottom>
          {t('admin_storage_cleanup.local_section')}
        </Typography>
        {section.skipped ? (
          <Alert severity="info">{section.skip_reason ?? t('admin_storage_cleanup.skipped')}</Alert>
        ) : null}
        <Stack spacing={0.5}>
          <Typography variant="body2">
            {t('admin_storage_cleanup.output_dir')}: {section.output_dir}
          </Typography>
          <Typography variant="body2" component="div">
            {t('admin_storage_cleanup.safe_roots')}:
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {section.safe_roots.map((root) => (
                <li key={root}>
                  <Typography variant="body2" component="span">
                    {root}
                  </Typography>
                </li>
              ))}
            </ul>
          </Typography>
          <Typography variant="body2">
            {t('admin_storage_cleanup.files_found')}: {section.files_found}
          </Typography>
          <Typography variant="body2">
            {t('admin_storage_cleanup.files_skipped_protected')}:{' '}
            {section.files_skipped_protected ?? 0}
          </Typography>
          <Typography variant="body2">
            {t('admin_storage_cleanup.bytes_found')}: {formatBytes(section.bytes_found, locale)}
          </Typography>
        </Stack>
        {section.errors.length > 0 ? (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {section.errors.join('; ')}
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

export default function AdminStorageMaintenancePage() {
  const { t, i18n } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [includePipelineTemp, setIncludePipelineTemp] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [summary, setSummary] = useState<AdminStorageCleanupResponse | null>(null);
  const [dryRunDone, setDryRunDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canDelete = useMemo(
    () => dryRunDone && confirmText.trim() === CONFIRM_TOKEN && !loading,
    [confirmText, dryRunDone, loading]
  );

  const runCleanup = async (mode: 'dry_run' | 'delete') => {
    setLoading(true);
    setError(null);
    try {
      const result = await postAdminStorageCleanup({
        target: 'both',
        mode,
        confirm: mode === 'delete' ? CONFIRM_TOKEN : undefined,
        include_legacy_local: true,
        include_pipeline_temp: includePipelineTemp,
      });
      setSummary(result);
      if (mode === 'dry_run') {
        setDryRunDone(true);
        showSnackbar(t('admin_storage_cleanup.dry_run_success'), 'info');
      } else {
        showSnackbar(t('admin_storage_cleanup.delete_success'), 'success');
        setDryRunDone(false);
        setConfirmText('');
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : t('admin_storage_cleanup.error_generic');
      setError(msg);
      showSnackbar(msg, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 960 }}>
      <PageHeader
        title={t('routes.admin_storage_maintenance.title')}
        subtitle={t('routes.admin_storage_maintenance.subtitle')}
      />
      <Alert severity="error" sx={{ mb: 2 }}>
        {t('admin_storage_cleanup.irreversible_warning')}
      </Alert>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t('admin_storage_cleanup.scope_hint')}
      </Typography>
      <FormControlLabel
        control={
          <Checkbox
            checked={includePipelineTemp}
            onChange={(e) => setIncludePipelineTemp(e.target.checked)}
          />
        }
        label={t('admin_storage_cleanup.include_pipeline_temp')}
      />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <Button variant="outlined" disabled={loading} onClick={() => runCleanup('dry_run')}>
          {t('admin_storage_cleanup.simulate')}
        </Button>
        <TextField
          size="small"
          label={t('admin_storage_cleanup.confirm_label')}
          placeholder={CONFIRM_TOKEN}
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          disabled={!dryRunDone || loading}
          sx={{ flex: 1, minWidth: 220 }}
        />
        <Button
          variant="contained"
          color="error"
          disabled={!canDelete}
          onClick={() => runCleanup('delete')}
        >
          {t('admin_storage_cleanup.delete_button')}
        </Button>
      </Stack>
      {error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      ) : null}
      {summary ? (
        <Stack spacing={2}>
          <Typography variant="body2">
            {t('admin_storage_cleanup.mode_label')}: {summary.mode}
          </Typography>
          <RemoteSummaryCard section={summary.remote} locale={i18n.language} />
          <LocalSummaryCard section={summary.local} locale={i18n.language} />
        </Stack>
      ) : null}
    </Box>
  );
}
