import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Collapse,
  Divider,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import AddIcon from '@mui/icons-material/Add';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { useTranslation } from 'react-i18next';
import type {
  AdditionalFieldRule,
  ExtractionProfileConfiguration,
  InternalCodeSourceRule,
  SupplierExtractionProfile,
} from '../../../api/types';
import { ApiError } from '../../../api/types';
import { ErrorAlert, LoadingBlock, SectionCard, useAppSnackbar } from '../../../components/ui';
import {
  useActivateSupplierExtractionProfileVersion,
  useActiveSupplierExtractionProfile,
  useCloneSupplierExtractionProfile,
  useCreateSupplierExtractionProfileVersion,
  useSupplierExtractionProfiles,
} from '../../../hooks';
import { resolveApiErrorMessage } from '../../../utils/apiErrors';
import { formatDate } from '../../../utils/formatDate';
import {
  defaultExtractionProfileConfiguration,
  EXTRACTION_PROFILE_TEMPLATES,
  INTERNAL_CODE_SOURCE_KEYS,
  INTERNAL_CODE_SOURCE_LABELS,
  SUPPORTED_BARCODE_FORMATS,
} from '../utils/defaultExtractionProfileConfiguration';
import { useExtractionProfileCapabilities } from '../hooks/useExtractionProfileCapabilities';
import SupplierExtractionProfileVersionList from './SupplierExtractionProfileVersionList';

export interface SupplierExtractionProfilesModuleProps {
  clientId: string;
  supplierId: string;
  supplierName: string;
}

type FormState = {
  configuration: ExtractionProfileConfiguration;
  visualNotes: string;
};

function cloneConfiguration(config: ExtractionProfileConfiguration): ExtractionProfileConfiguration {
  return JSON.parse(JSON.stringify(config)) as ExtractionProfileConfiguration;
}

function profileToFormState(profile: SupplierExtractionProfile | null | undefined): FormState {
  if (!profile) {
    return {
      configuration: defaultExtractionProfileConfiguration(),
      visualNotes: '',
    };
  }
  return {
    configuration: cloneConfiguration(profile.configuration),
    visualNotes: profile.visual_notes ?? '',
  };
}

function reorderInternalCodeSources(
  sources: InternalCodeSourceRule[],
  index: number,
  direction: 'up' | 'down'
): InternalCodeSourceRule[] {
  const targetIndex = direction === 'up' ? index - 1 : index + 1;
  if (targetIndex < 0 || targetIndex >= sources.length) return sources;
  const next = [...sources];
  [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
  return next.map((item, idx) => ({ ...item, priority: idx + 1 }));
}

function aliasesToText(aliases: string[]): string {
  return aliases.join(', ');
}

function textToAliases(value: string): string[] {
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

export default function SupplierExtractionProfilesModule({
  clientId,
  supplierId,
  supplierName,
}: SupplierExtractionProfilesModuleProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [showHistory, setShowHistory] = useState(false);
  const [formState, setFormState] = useState<FormState>(() => profileToFormState(null));
  const [initializedFrom, setInitializedFrom] = useState<string | null>(null);

  const versionsQuery = useSupplierExtractionProfiles(clientId, supplierId, {
    enabled: Boolean(clientId && supplierId),
  });
  const activeQuery = useActiveSupplierExtractionProfile(clientId, supplierId, {
    enabled: Boolean(clientId && supplierId),
  });
  const createMutation = useCreateSupplierExtractionProfileVersion(clientId, supplierId);
  const activateMutation = useActivateSupplierExtractionProfileVersion(clientId, supplierId);
  const cloneMutation = useCloneSupplierExtractionProfile(clientId, supplierId);
  const capabilities = useExtractionProfileCapabilities({
    enabled: Boolean(clientId && supplierId),
  });

  const activeProfile = useMemo(() => {
    if (activeQuery.data) return activeQuery.data;
    if (
      activeQuery.isError &&
      activeQuery.error instanceof ApiError &&
      activeQuery.error.status === 404
    ) {
      return null;
    }
    return undefined;
  }, [activeQuery.data, activeQuery.error, activeQuery.isError]);

  useEffect(() => {
    const seedId = activeProfile?.id ?? '__default__';
    if (activeProfile === undefined) return;
    if (initializedFrom === seedId) return;
    setFormState(profileToFormState(activeProfile));
    setInitializedFrom(seedId);
  }, [activeProfile, initializedFrom]);

  const loadingError =
    versionsQuery.isError && versionsQuery.error
      ? resolveApiErrorMessage(versionsQuery.error, 'clients.extraction_profile.load_error')
      : null;

  const createError =
    createMutation.isError && createMutation.error
      ? resolveApiErrorMessage(createMutation.error, 'clients.extraction_profile.create_error')
      : null;

  const cloneError =
    cloneMutation.isError && cloneMutation.error
      ? resolveApiErrorMessage(cloneMutation.error, 'clients.extraction_profile.clone_error')
      : null;

  const handleSave = useCallback(
    (activate: boolean) => {
      void createMutation
        .mutateAsync({
          configuration: formState.configuration as unknown as Record<string, unknown>,
          visual_notes: formState.visualNotes.trim() || null,
          activate,
        })
        .then(() => {
          showSnackbar(
            t(
              activate
                ? 'clients.extraction_profile.created_and_activated_success'
                : 'clients.extraction_profile.created_success'
            ),
            'success'
          );
          setInitializedFrom(null);
        })
        .catch(() => {
          /* surfaced below */
        });
    },
    [createMutation, formState.configuration, formState.visualNotes, showSnackbar, t]
  );

  const handleClone = useCallback(() => {
    const sourceId = activeProfile?.id ?? versionsQuery.data?.items?.[0]?.id;
    if (!sourceId) {
      showSnackbar(t('clients.extraction_profile.clone_no_source'), 'warning');
      return;
    }
    void cloneMutation
      .mutateAsync(sourceId)
      .then((cloned) => {
        showSnackbar(t('clients.extraction_profile.clone_success'), 'success');
        setFormState(profileToFormState(cloned));
        setInitializedFrom(cloned.id);
      })
      .catch(() => {
        /* surfaced below */
      });
  }, [activeProfile?.id, cloneMutation, showSnackbar, t, versionsQuery.data?.items]);

  const handleActivateVersion = useCallback(
    async (profileId: string, expectedRowVersion: number) => {
      try {
        await activateMutation.mutateAsync({ profileId, expectedRowVersion });
        showSnackbar(t('clients.extraction_profile.activated_success'), 'success');
        setInitializedFrom(null);
      } catch {
        /* surfaced in history section */
      }
    },
    [activateMutation, showSnackbar, t]
  );

  const updateConfiguration = useCallback(
    (updater: (prev: ExtractionProfileConfiguration) => ExtractionProfileConfiguration) => {
      setFormState((prev) => ({
        ...prev,
        configuration: updater(prev.configuration),
      }));
    },
    []
  );

  const availableInternalCodeKeys = useMemo(() => {
    const used = new Set(formState.configuration.internal_code_sources.map((s) => s.field_key));
    return INTERNAL_CODE_SOURCE_KEYS.filter((key) => !used.has(key));
  }, [formState.configuration.internal_code_sources]);

  const addInternalCodeSource = useCallback(() => {
    const nextKey = availableInternalCodeKeys[0];
    if (!nextKey) return;
    updateConfiguration((prev) => ({
      ...prev,
      internal_code_sources: [
        ...prev.internal_code_sources,
        {
          field_key: nextKey,
          priority: prev.internal_code_sources.length + 1,
          enabled: true,
        },
      ],
    }));
  }, [availableInternalCodeKeys, updateConfiguration]);

  const addAdditionalField = useCallback(() => {
    updateConfiguration((prev) => ({
      ...prev,
      additional_fields: [
        ...prev.additional_fields,
        {
          field_key: `field_${prev.additional_fields.length + 1}`,
          display_name: '',
          aliases: [],
          data_type: 'TEXT',
          required: false,
          priority: 100 + prev.additional_fields.length,
        },
      ],
    }));
  }, [updateConfiguration]);

  const isLoading = versionsQuery.isLoading || activeQuery.isLoading;
  const isSaving = createMutation.isPending;
  const headerProfile = activeProfile ?? null;

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        bgcolor: 'background.paper',
        overflow: 'hidden',
      }}
    >
      <Box sx={{ px: 2.5, pt: 2, pb: 1.5, borderBottom: 1, borderColor: 'divider' }}>
        <Typography variant="caption" color="text.secondary">
          {supplierName}
        </Typography>
        <Typography variant="h6" sx={{ mt: 0.5 }}>
          {t('clients.extraction_profile.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {t('clients.extraction_profile.description')}
        </Typography>
      </Box>

      <Stack spacing={2} sx={{ p: 2.5 }}>
        <Alert severity="info">{t('clients.extraction_profile.processing_flag_hint')}</Alert>

        {!capabilities.profile_aware_validation_enabled ? (
          <Alert severity="warning" role="status">
            {t('clients.extraction_profile.profile_aware_disabled_warning')}
          </Alert>
        ) : null}

        {isLoading ? (
          <LoadingBlock message={t('common.loading')} py={1} sx={{ justifyContent: 'flex-start' }} />
        ) : null}

        {loadingError ? (
          <ErrorAlert
            message={loadingError}
            onRetry={() => {
              void versionsQuery.refetch();
              void activeQuery.refetch();
            }}
            retryLabel={t('common.retry')}
          />
        ) : null}

        {!isLoading && !headerProfile ? (
          <Alert severity="warning">{t('clients.extraction_profile.no_active_description')}</Alert>
        ) : null}

        <SectionCard title={t('clients.extraction_profile.active_version')} variant="outlined">
          {activeQuery.isLoading ? (
            <LoadingBlock message={t('common.loading')} py={1} sx={{ justifyContent: 'flex-start' }} />
          ) : headerProfile ? (
            <Stack spacing={0.5}>
              <Typography variant="body2">
                <strong>{t('clients.extraction_profile.version_label', { version: headerProfile.version })}</strong>{' '}
                · {t(`clients.extraction_profile.status.${String(headerProfile.status).toLowerCase()}`, {
                  defaultValue: String(headerProfile.status),
                })}
                {capabilities.profile_aware_validation_enabled
                  ? ` · ${t('clients.extraction_profile.processing_active_label')}`
                  : ` · ${t('clients.extraction_profile.processing_inactive_label')}`}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {t('clients.extraction_profile.header_dates', {
                  created: formatDate(headerProfile.created_at),
                  activated: headerProfile.activated_at
                    ? formatDate(headerProfile.activated_at)
                    : t('clients.common.no_information'),
                })}
              </Typography>
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              {t('clients.extraction_profile.no_active_title')}
            </Typography>
          )}
        </SectionCard>

        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Button variant="contained" size="small" disabled={isSaving} onClick={() => handleSave(true)}>
            {t('clients.extraction_profile.save_and_activate')}
          </Button>
          <Button variant="outlined" size="small" disabled={isSaving} onClick={() => handleSave(false)}>
            {t('clients.extraction_profile.save_without_activating')}
          </Button>
          <Button variant="outlined" size="small" onClick={() => setShowHistory((prev) => !prev)}>
            {showHistory
              ? t('clients.extraction_profile.hide_history')
              : t('clients.extraction_profile.show_history')}
          </Button>
          <Button variant="outlined" size="small" disabled={cloneMutation.isPending} onClick={handleClone}>
            {t('clients.extraction_profile.clone')}
          </Button>
        </Box>

        {createError ? <Alert severity="error">{createError}</Alert> : null}
        {cloneError ? <Alert severity="error">{cloneError}</Alert> : null}

        <Collapse in={showHistory}>
          <Stack spacing={1}>
            <Typography variant="subtitle1">{t('clients.extraction_profile.version_history')}</Typography>
            <SupplierExtractionProfileVersionList
              items={versionsQuery.data?.items ?? []}
              onActivate={handleActivateVersion}
              isActivating={activateMutation.isPending}
            />
            {activateMutation.isError && activateMutation.error ? (
              <Alert severity="error">
                {resolveApiErrorMessage(activateMutation.error, 'clients.extraction_profile.activate_error')}
              </Alert>
            ) : null}
          </Stack>
          <Divider sx={{ my: 2 }} />
        </Collapse>

        <SectionCard title={t('clients.extraction_profile.templates_gallery')} variant="outlined">
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} flexWrap="wrap" useFlexGap>
            {EXTRACTION_PROFILE_TEMPLATES.map((tpl) => (
              <Button
                key={tpl.id}
                size="small"
                variant="outlined"
                onClick={() =>
                  updateConfiguration(() => cloneConfiguration(tpl.build()))
                }
              >
                {t(tpl.labelKey)}
              </Button>
            ))}
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            {t('clients.extraction_profile.apply_template')} — {t('clients.extraction_profile.label_detection_help')}
          </Typography>
        </SectionCard>

        <SectionCard title={t('clients.extraction_profile.section_label_detection')} variant="outlined">
          <Stack spacing={1.5}>
            <Alert severity="info">{t('clients.extraction_profile.label_detection_help')}</Alert>
            <TextField
              select
              size="small"
              label={t('clients.extraction_profile.label_background')}
              value={formState.configuration.label_detection_rules?.expected_background ?? 'LIGHT'}
              onChange={(e) =>
                updateConfiguration((prev) => ({
                  ...prev,
                  label_detection_rules: {
                    ...(prev.label_detection_rules ?? {}),
                    expected_background: e.target.value,
                  },
                }))
              }
            >
              <MenuItem value="LIGHT">{t('clients.extraction_profile.bg_light')}</MenuItem>
              <MenuItem value="DARK">{t('clients.extraction_profile.bg_dark')}</MenuItem>
              <MenuItem value="VARIABLE">{t('clients.extraction_profile.bg_variable')}</MenuItem>
              <MenuItem value="DISABLED">{t('clients.extraction_profile.bg_disabled')}</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              label={t('clients.extraction_profile.label_shape')}
              value={formState.configuration.label_detection_rules?.expected_shape ?? 'APPROXIMATELY_RECTANGULAR'}
              onChange={(e) =>
                updateConfiguration((prev) => ({
                  ...prev,
                  label_detection_rules: {
                    ...(prev.label_detection_rules ?? {}),
                    expected_shape: e.target.value,
                  },
                }))
              }
            >
              <MenuItem value="RECTANGULAR">{t('clients.extraction_profile.shape_rectangular')}</MenuItem>
              <MenuItem value="APPROXIMATELY_RECTANGULAR">{t('clients.extraction_profile.shape_approx')}</MenuItem>
              <MenuItem value="VARIABLE">{t('clients.extraction_profile.shape_variable')}</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              label={t('clients.extraction_profile.label_orientation')}
              value={formState.configuration.label_detection_rules?.expected_orientation ?? 'ANY'}
              onChange={(e) =>
                updateConfiguration((prev) => ({
                  ...prev,
                  label_detection_rules: {
                    ...(prev.label_detection_rules ?? {}),
                    expected_orientation: e.target.value,
                  },
                }))
              }
            >
              <MenuItem value="ANY">{t('clients.extraction_profile.orient_any')}</MenuItem>
              <MenuItem value="HORIZONTAL">{t('clients.extraction_profile.orient_horizontal')}</MenuItem>
              <MenuItem value="VERTICAL">{t('clients.extraction_profile.orient_vertical')}</MenuItem>
              <MenuItem value="SQUARE_OR_VERTICAL">{t('clients.extraction_profile.orient_square')}</MenuItem>
            </TextField>
            <TextField
              size="small"
              label={t('clients.extraction_profile.label_primary_anchors')}
              helperText={t('clients.extraction_profile.comma_separated_hint')}
              value={aliasesToText(formState.configuration.label_detection_rules?.primary_anchors ?? [])}
              onChange={(e) =>
                updateConfiguration((prev) => ({
                  ...prev,
                  label_detection_rules: {
                    ...(prev.label_detection_rules ?? {}),
                    primary_anchors: textToAliases(e.target.value),
                  },
                }))
              }
            />
            <TextField
              size="small"
              label={t('clients.extraction_profile.label_secondary_anchors')}
              helperText={t('clients.extraction_profile.comma_separated_hint')}
              value={aliasesToText(formState.configuration.label_detection_rules?.secondary_anchors ?? [])}
              onChange={(e) =>
                updateConfiguration((prev) => ({
                  ...prev,
                  label_detection_rules: {
                    ...(prev.label_detection_rules ?? {}),
                    secondary_anchors: textToAliases(e.target.value),
                  },
                }))
              }
            />
            <TextField
              size="small"
              type="number"
              label={t('clients.extraction_profile.label_min_anchor_matches')}
              value={formState.configuration.label_detection_rules?.minimum_anchor_matches ?? 1}
              onChange={(e) =>
                updateConfiguration((prev) => ({
                  ...prev,
                  label_detection_rules: {
                    ...(prev.label_detection_rules ?? {}),
                    minimum_anchor_matches: Number(e.target.value) || 0,
                  },
                }))
              }
            />
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={formState.configuration.label_detection_rules?.allow_rotation ?? true}
                  onChange={(e) =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      label_detection_rules: {
                        ...(prev.label_detection_rules ?? {}),
                        allow_rotation: e.target.checked,
                      },
                    }))
                  }
                />
              }
              label={t('clients.extraction_profile.label_allow_rotation')}
            />
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={
                    formState.configuration.label_detection_rules?.allow_perspective_correction ?? true
                  }
                  onChange={(e) =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      label_detection_rules: {
                        ...(prev.label_detection_rules ?? {}),
                        allow_perspective_correction: e.target.checked,
                      },
                    }))
                  }
                />
              }
              label={t('clients.extraction_profile.label_allow_deskew')}
            />
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={
                    formState.configuration.label_detection_rules?.allow_full_image_fallback ?? true
                  }
                  onChange={(e) =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      label_detection_rules: {
                        ...(prev.label_detection_rules ?? {}),
                        allow_full_image_fallback: e.target.checked,
                      },
                    }))
                  }
                />
              }
              label={t('clients.extraction_profile.label_allow_full_image_fallback')}
            />
          </Stack>
        </SectionCard>

        <SectionCard title={t('clients.extraction_profile.section_internal_code')} variant="outlined">
          <Stack spacing={1}>
            {formState.configuration.internal_code_sources.map((source, index) => (
              <Box
                key={`${source.field_key}-${index}`}
                sx={{
                  display: 'grid',
                  gap: 1,
                  gridTemplateColumns: { xs: '1fr', sm: 'auto 1fr auto auto' },
                  alignItems: 'center',
                  p: 1,
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1,
                }}
              >
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {INTERNAL_CODE_SOURCE_LABELS[source.field_key] ?? source.field_key}
                </Typography>
                <FormControlLabel
                  control={
                    <Switch
                      size="small"
                      checked={source.enabled}
                      onChange={(e) =>
                        updateConfiguration((prev) => ({
                          ...prev,
                          internal_code_sources: prev.internal_code_sources.map((item, idx) =>
                            idx === index ? { ...item, enabled: e.target.checked } : item
                          ),
                        }))
                      }
                    />
                  }
                  label={t('clients.extraction_profile.enabled')}
                />
                <Box sx={{ display: 'flex', gap: 0.5 }}>
                  <IconButton
                    size="small"
                    aria-label={t('clients.extraction_profile.move_up')}
                    disabled={index === 0}
                    onClick={() =>
                      updateConfiguration((prev) => ({
                        ...prev,
                        internal_code_sources: reorderInternalCodeSources(prev.internal_code_sources, index, 'up'),
                      }))
                    }
                  >
                    <ArrowUpwardIcon fontSize="small" />
                  </IconButton>
                  <IconButton
                    size="small"
                    aria-label={t('clients.extraction_profile.move_down')}
                    disabled={index === formState.configuration.internal_code_sources.length - 1}
                    onClick={() =>
                      updateConfiguration((prev) => ({
                        ...prev,
                        internal_code_sources: reorderInternalCodeSources(prev.internal_code_sources, index, 'down'),
                      }))
                    }
                  >
                    <ArrowDownwardIcon fontSize="small" />
                  </IconButton>
                </Box>
                <Typography variant="caption" color="text.secondary">
                  {t('clients.extraction_profile.priority_label', { priority: source.priority })}
                </Typography>
              </Box>
            ))}
            <Button
              size="small"
              startIcon={<AddIcon />}
              disabled={availableInternalCodeKeys.length === 0}
              onClick={addInternalCodeSource}
              sx={{ alignSelf: 'flex-start' }}
            >
              {t('clients.extraction_profile.add_internal_code_source')}
            </Button>
            <TextField
              size="small"
              type="number"
              label={t('clients.extraction_profile.code_exact_length')}
              helperText={t('clients.extraction_profile.code_exact_length_hint')}
              value={formState.configuration.validation_rules.code.exact_length ?? ''}
              onChange={(e) =>
                updateConfiguration((prev) => ({
                  ...prev,
                  validation_rules: {
                    ...prev.validation_rules,
                    code: {
                      ...prev.validation_rules.code,
                      exact_length: e.target.value === '' ? null : Number(e.target.value),
                    },
                  },
                }))
              }
            />
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={formState.configuration.validation_rules.code.allow_digits}
                  onChange={(e) =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      validation_rules: {
                        ...prev.validation_rules,
                        code: { ...prev.validation_rules.code, allow_digits: e.target.checked },
                      },
                    }))
                  }
                />
              }
              label={t('clients.extraction_profile.code_allow_digits')}
            />
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={formState.configuration.validation_rules.code.allow_letters}
                  onChange={(e) =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      validation_rules: {
                        ...prev.validation_rules,
                        code: { ...prev.validation_rules.code, allow_letters: e.target.checked },
                      },
                    }))
                  }
                />
              }
              label={t('clients.extraction_profile.code_allow_letters')}
            />
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={formState.configuration.validation_rules.code.preserve_leading_zeros}
                  onChange={(e) =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      validation_rules: {
                        ...prev.validation_rules,
                        code: {
                          ...prev.validation_rules.code,
                          preserve_leading_zeros: e.target.checked,
                        },
                      },
                    }))
                  }
                />
              }
              label={t('clients.extraction_profile.code_preserve_zeros')}
            />
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={
                    formState.configuration.validation_rules.code.reject_measurement_patterns ?? true
                  }
                  onChange={(e) =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      validation_rules: {
                        ...prev.validation_rules,
                        code: {
                          ...prev.validation_rules.code,
                          reject_measurement_patterns: e.target.checked,
                        },
                      },
                    }))
                  }
                />
              }
              label={t('clients.extraction_profile.code_reject_measurements')}
            />
          </Stack>
        </SectionCard>
        <SectionCard title={t('clients.extraction_profile.section_quantity')} variant="outlined">
          <Stack spacing={1.5}>
            <Alert severity="warning">{t('clients.extraction_profile.quantity_no_default_warning')}</Alert>
            <TextField
              select
              size="small"
              label={t('clients.extraction_profile.quantity_expected_presence')}
              value={formState.configuration.quantity_rules.expected_presence ?? 'ALWAYS'}
              onChange={(e) =>
                updateConfiguration((prev) => ({
                  ...prev,
                  quantity_rules: {
                    ...prev.quantity_rules,
                    expected_presence: e.target.value,
                  },
                }))
              }
            >
              <MenuItem value="ALWAYS">{t('clients.extraction_profile.presence_always')}</MenuItem>
              <MenuItem value="OPTIONAL">{t('clients.extraction_profile.presence_optional')}</MenuItem>
              <MenuItem value="UNKNOWN">{t('clients.extraction_profile.presence_unknown')}</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              label={t('clients.extraction_profile.quantity_missing_action')}
              value={
                formState.configuration.quantity_rules.missing_quantity_action ??
                'PENDING_MANUAL_REVIEW'
              }
              onChange={(e) =>
                updateConfiguration((prev) => ({
                  ...prev,
                  quantity_rules: {
                    ...prev.quantity_rules,
                    missing_quantity_action: e.target.value,
                  },
                }))
              }
            >
              <MenuItem value="PENDING_MANUAL_REVIEW">
                {t('clients.extraction_profile.missing_action_manual')}
              </MenuItem>
              <MenuItem value="EXTERNAL_FALLBACK">
                {t('clients.extraction_profile.missing_action_external')}
              </MenuItem>
              <MenuItem value="UNRECOGNIZED">
                {t('clients.extraction_profile.missing_action_unrecognized')}
              </MenuItem>
            </TextField>
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={formState.configuration.quantity_rules.required}
                  onChange={(e) =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      quantity_rules: {
                        ...prev.quantity_rules,
                        required: e.target.checked,
                      },
                    }))
                  }
                />
              }
              label={t('clients.extraction_profile.quantity_required_auto')}
            />
            <TextField
              label={t('clients.extraction_profile.quantity_aliases')}
              value={aliasesToText(formState.configuration.quantity_rules.aliases)}
              onChange={(e) =>
                updateConfiguration((prev) => ({
                  ...prev,
                  quantity_rules: {
                    ...prev.quantity_rules,
                    aliases: textToAliases(e.target.value),
                  },
                }))
              }
              size="small"
              fullWidth
              helperText={t('clients.extraction_profile.comma_separated_hint')}
            />
            <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' } }}>
              <TextField
                label={t('clients.extraction_profile.quantity_minimum')}
                type="number"
                size="small"
                value={formState.configuration.quantity_rules.minimum}
                onChange={(e) =>
                  updateConfiguration((prev) => ({
                    ...prev,
                    quantity_rules: {
                      ...prev.quantity_rules,
                      minimum: Number(e.target.value),
                    },
                  }))
                }
              />
              <TextField
                label={t('clients.extraction_profile.quantity_maximum')}
                type="number"
                size="small"
                value={formState.configuration.quantity_rules.maximum}
                onChange={(e) =>
                  updateConfiguration((prev) => ({
                    ...prev,
                    quantity_rules: {
                      ...prev.quantity_rules,
                      maximum: Number(e.target.value),
                    },
                  }))
                }
              />
            </Box>
            <FormControlLabel
              control={
                <Switch
                  checked={formState.configuration.quantity_rules.allow_decimals}
                  onChange={(e) =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      quantity_rules: {
                        ...prev.quantity_rules,
                        allow_decimals: e.target.checked,
                      },
                    }))
                  }
                />
              }
              label={t('clients.extraction_profile.quantity_allow_decimals')}
            />
          </Stack>
        </SectionCard>

        <SectionCard title={t('clients.extraction_profile.section_additional_fields')} variant="outlined">
          <Stack spacing={1.5}>
            {formState.configuration.additional_fields.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {t('clients.extraction_profile.additional_fields_empty')}
              </Typography>
            ) : (
              formState.configuration.additional_fields.map((field, index) => (
                <AdditionalFieldEditor
                  key={`${field.field_key}-${index}`}
                  field={field}
                  onChange={(next) =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      additional_fields: prev.additional_fields.map((item, idx) =>
                        idx === index ? next : item
                      ),
                    }))
                  }
                  onRemove={() =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      additional_fields: prev.additional_fields.filter((_, idx) => idx !== index),
                    }))
                  }
                />
              ))
            )}
            <Button size="small" startIcon={<AddIcon />} onClick={addAdditionalField} sx={{ alignSelf: 'flex-start' }}>
              {t('clients.extraction_profile.add_additional_field')}
            </Button>
          </Stack>
        </SectionCard>

        <SectionCard title={t('clients.extraction_profile.section_formats')} variant="outlined">
          <Stack spacing={1.5}>
            <Typography variant="body2" color="text.secondary">
              {t('clients.extraction_profile.barcode_formats_hint')}
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {SUPPORTED_BARCODE_FORMATS.map((format) => {
                const checked = formState.configuration.accepted_barcode_formats.includes(format);
                return (
                  <FormControlLabel
                    key={format}
                    control={
                      <Checkbox
                        size="small"
                        checked={checked}
                        onChange={(e) =>
                          updateConfiguration((prev) => ({
                            ...prev,
                            accepted_barcode_formats: e.target.checked
                              ? [...prev.accepted_barcode_formats, format]
                              : prev.accepted_barcode_formats.filter((item) => item !== format),
                          }))
                        }
                      />
                    }
                    label={format}
                  />
                );
              })}
            </Box>
            <FormControlLabel
              control={
                <Switch
                  checked={formState.configuration.validation_rules.ean.validate_checksum}
                  onChange={(e) =>
                    updateConfiguration((prev) => ({
                      ...prev,
                      validation_rules: {
                        ...prev.validation_rules,
                        ean: {
                          ...prev.validation_rules.ean,
                          validate_checksum: e.target.checked,
                        },
                      },
                    }))
                  }
                />
              }
              label={t('clients.extraction_profile.ean_validate_checksum')}
            />
          </Stack>
        </SectionCard>

        <SectionCard title={t('clients.extraction_profile.section_visual_notes')} variant="outlined">
          <Stack spacing={1.5}>
            <Alert severity="info">{t('clients.extraction_profile.visual_notes_disclaimer')}</Alert>
            <TextField
              label={t('clients.extraction_profile.visual_notes_label')}
              value={formState.visualNotes}
              onChange={(e) => setFormState((prev) => ({ ...prev, visualNotes: e.target.value }))}
              multiline
              minRows={3}
              fullWidth
            />
          </Stack>
        </SectionCard>
      </Stack>
    </Box>
  );
}

function AdditionalFieldEditor({
  field,
  onChange,
  onRemove,
}: {
  field: AdditionalFieldRule;
  onChange: (next: AdditionalFieldRule) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Box
      sx={{
        display: 'grid',
        gap: 1,
        gridTemplateColumns: { xs: '1fr', md: '1fr 1fr auto' },
        alignItems: 'start',
        p: 1.5,
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
      }}
    >
      <TextField
        label={t('clients.extraction_profile.field_key')}
        size="small"
        value={field.field_key}
        onChange={(e) => onChange({ ...field, field_key: e.target.value })}
      />
      <TextField
        label={t('clients.extraction_profile.display_name')}
        size="small"
        value={field.display_name}
        onChange={(e) => onChange({ ...field, display_name: e.target.value })}
      />
      <IconButton size="small" color="error" aria-label={t('common.delete')} onClick={onRemove}>
        <DeleteOutlineIcon fontSize="small" />
      </IconButton>
      <TextField
        label={t('clients.extraction_profile.field_aliases')}
        size="small"
        value={aliasesToText(field.aliases)}
        onChange={(e) => onChange({ ...field, aliases: textToAliases(e.target.value) })}
        helperText={t('clients.extraction_profile.comma_separated_hint')}
        sx={{ gridColumn: { xs: '1', md: '1 / -1' } }}
      />
      <TextField
        select
        label={t('clients.extraction_profile.data_type')}
        size="small"
        value={field.data_type}
        onChange={(e) => onChange({ ...field, data_type: e.target.value })}
      >
        {['TEXT', 'INTEGER', 'DECIMAL', 'DATE', 'CODE', 'BOOLEAN'].map((type) => (
          <MenuItem key={type} value={type}>
            {type}
          </MenuItem>
        ))}
      </TextField>
      <FormControlLabel
        control={
          <Switch
            size="small"
            checked={field.required}
            onChange={(e) => onChange({ ...field, required: e.target.checked })}
          />
        }
        label={t('clients.extraction_profile.required')}
      />
    </Box>
  );
}
