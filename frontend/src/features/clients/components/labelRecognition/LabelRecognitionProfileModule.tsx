import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Box, Button, MenuItem, Stack, Tab, Tabs, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { ExtractionProfileConfiguration, LabelKind, SupplierExtractionProfile } from '../../../../api/types';
import { ErrorAlert, LoadingBlock, SectionCard, useAppSnackbar } from '../../../../components/ui';
import { useCreateSupplierExtractionProfileVersion, useSupplierExtractionProfiles } from '../../../../hooks';
import { resolveApiErrorMessage } from '../../../../utils/apiErrors';
import { useExtractionProfileCapabilities } from '../../hooks/useExtractionProfileCapabilities';
import {
  defaultExtractionProfileConfiguration,
  LABEL_RECOGNITION_TEMPLATES,
} from '../../utils/defaultExtractionProfileConfiguration';
import BarcodeRulesSection from './BarcodeRulesSection';
import ExamplesEditor from './ExamplesEditor';
import LabelRecognitionTester from './LabelRecognitionTester';
import PayloadStructureSection from './PayloadStructureSection';
import QuantityRulesSection from './QuantityRulesSection';
import ReferenceImagesSection from './ReferenceImagesSection';
import VisualHintsSection from './VisualHintsSection';

export interface LabelRecognitionProfileModuleProps {
  clientId: string;
  supplierId: string;
  supplierName: string;
}

type ProfileSource = 'DINAMIC' | 'SUPPLIER';
type Draft = {
  configuration: ExtractionProfileConfiguration;
  visualNotes: string;
  source: ProfileSource;
  dirty: boolean;
  initialized: boolean;
};

function cloneConfiguration(configuration: ExtractionProfileConfiguration): ExtractionProfileConfiguration {
  return JSON.parse(JSON.stringify(configuration)) as ExtractionProfileConfiguration;
}

function emptyDraft(kind: LabelKind): Draft {
  const configuration = defaultExtractionProfileConfiguration();
  if (kind === 'POSITION' && configuration.deterministic) {
    configuration.semantic_type = 'LOCATION';
    configuration.deterministic.field_mappings = [{ target: 'position_id', source: 'WHOLE' }];
  }
  return { configuration, visualNotes: '', source: 'SUPPLIER', dirty: false, initialized: false };
}

function draftFromProfile(profile: SupplierExtractionProfile | undefined, kind: LabelKind): Draft {
  if (!profile) return { ...emptyDraft(kind), initialized: true };
  const configuration = cloneConfiguration(profile.configuration);
  const fallback = defaultExtractionProfileConfiguration().deterministic!;
  configuration.configuration_schema_version = 2;
  configuration.deterministic = { ...fallback, ...(configuration.deterministic ?? {}) };
  configuration.valid_examples ??= [];
  configuration.invalid_examples ??= [];
  return { configuration, visualNotes: profile.visual_notes ?? '', source: 'SUPPLIER', dirty: false, initialized: true };
}

export default function LabelRecognitionProfileModule({ clientId, supplierId, supplierName }: LabelRecognitionProfileModuleProps) {
  const { t } = useTranslation();
  const { showSnackbar } = useAppSnackbar();
  const [labelKind, setLabelKind] = useState<LabelKind>('ITEM');
  const [drafts, setDrafts] = useState<Record<LabelKind, Draft>>({ ITEM: emptyDraft('ITEM'), POSITION: emptyDraft('POSITION') });
  const profilesQuery = useSupplierExtractionProfiles(clientId, supplierId, { enabled: Boolean(clientId && supplierId) });
  const createMutation = useCreateSupplierExtractionProfileVersion(clientId, supplierId);
  const capabilities = useExtractionProfileCapabilities({ enabled: Boolean(clientId && supplierId) });

  const profilesByKind = useMemo(() => {
    const items = profilesQuery.data?.items ?? [];
    return {
      ITEM: items.filter((profile) => !profile.label_kind || profile.label_kind === 'ITEM'),
      POSITION: items.filter((profile) => profile.label_kind === 'POSITION'),
    };
  }, [profilesQuery.data?.items]);

  useEffect(() => {
    if (!profilesQuery.data) return;
    setDrafts((current) => {
      const next = { ...current };
      (['ITEM', 'POSITION'] as const).forEach((kind) => {
        if (!current[kind].initialized && !current[kind].dirty) {
          const active = profilesByKind[kind].find((profile) => profile.status === 'ACTIVE') ?? profilesByKind[kind][0];
          next[kind] = draftFromProfile(active, kind);
        }
      });
      return next;
    });
  }, [profilesByKind, profilesQuery.data]);

  const draft = drafts[labelKind];
  const updateDraft = useCallback((patch: Partial<Draft>) => {
    setDrafts((current) => ({ ...current, [labelKind]: { ...current[labelKind], ...patch, dirty: true } }));
  }, [labelKind]);

  const handleKindChange = (_: unknown, value: LabelKind) => {
    if (!value || value === labelKind) return;
    if (draft.dirty && !window.confirm(t('clients.extraction_profile.switch_dirty_warning'))) return;
    setLabelKind(value);
  };

  const handleSave = async (activate: boolean) => {
    try {
      await createMutation.mutateAsync({
        configuration: draft.configuration as unknown as Record<string, unknown>,
        visual_notes: draft.visualNotes.trim() || null,
        activate,
        label_kind: labelKind,
      });
      setDrafts((current) => ({ ...current, [labelKind]: { ...current[labelKind], dirty: false, initialized: false } }));
      showSnackbar(t(activate ? 'clients.extraction_profile.created_and_activated_success' : 'clients.extraction_profile.created_success'), 'success');
    } catch {
      // Mutation state renders the localized error.
    }
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', border: 1, borderColor: 'divider', borderRadius: 1, bgcolor: 'background.paper', overflow: 'hidden' }}>
      <Box sx={{ px: 2.5, pt: 2, pb: 1.5, borderBottom: 1, borderColor: 'divider' }}>
        <Typography variant="caption" color="text.secondary">{supplierName}</Typography>
        <Typography variant="h6">{t('clients.extraction_profile.title')}</Typography>
        <Typography variant="body2" color="text.secondary">{t('clients.extraction_profile.description')}</Typography>
      </Box>
      <Tabs value={labelKind} onChange={handleKindChange} sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tab value="ITEM" label={t('clients.extraction_profile.item_labels')} />
        <Tab value="POSITION" label={t('clients.extraction_profile.position_labels')} />
      </Tabs>
      <Stack spacing={2} sx={{ p: 2.5 }}>
        {!capabilities.profile_aware_validation_enabled ? (
          <Alert severity="warning" role="status">
            {t('clients.extraction_profile.profile_aware_disabled_warning')}
          </Alert>
        ) : (
          <Alert severity="success" role="status">
            {t('clients.extraction_profile.processing_active_label')}
          </Alert>
        )}
        {profilesQuery.isLoading ? <LoadingBlock message={t('common.loading')} py={1} /> : null}
        {profilesQuery.isError ? <ErrorAlert message={resolveApiErrorMessage(profilesQuery.error, 'clients.extraction_profile.load_error')} onRetry={() => void profilesQuery.refetch()} /> : null}

        <SectionCard title={t('clients.extraction_profile.profile_source')} variant="outlined">
          <Stack spacing={1}>
            <ToggleButtonGroup exclusive size="small" value={draft.source} onChange={(_, value: ProfileSource | null) => value && updateDraft({ source: value })}>
              <ToggleButton value="DINAMIC">DINAMIC</ToggleButton>
              <ToggleButton value="SUPPLIER">{t('clients.extraction_profile.source_supplier')}</ToggleButton>
            </ToggleButtonGroup>
            {draft.source === 'DINAMIC' ? <Alert severity="info">{t('clients.extraction_profile.dinamic_source_draft_kept')}</Alert> : null}
          </Stack>
        </SectionCard>

        {draft.source === 'SUPPLIER' ? (
          <>
            <SectionCard title={t('clients.extraction_profile.section_identity')} variant="outlined">
              <TextField
                select
                size="small"
                fullWidth
                label={t('clients.extraction_profile.semantic_type')}
                value={draft.configuration.semantic_type ?? 'CUSTOM'}
                onChange={(e) => updateDraft({ configuration: { ...draft.configuration, semantic_type: e.target.value } })}
              >
                {(labelKind === 'ITEM'
                  ? ['PRODUCT_SKU', 'LOGISTIC_UNIT', 'PALLET', 'BOX', 'LPN', 'SSCC', 'CONTAINER', 'CUSTOM']
                  : ['LOCATION', 'AISLE_POSITION', 'PALLET_POSITION', 'RACK_POSITION', 'CUSTOM']
                ).map((value) => (
                  <MenuItem key={value} value={value}>
                    {t(`clients.extraction_profile.semantic_${value.toLowerCase()}`, { defaultValue: value })}
                  </MenuItem>
                ))}
              </TextField>
              <Alert severity="info" sx={{ mt: 1 }}>
                {t('clients.extraction_profile.prompt_kind_hint', { kind: labelKind })}
              </Alert>
            </SectionCard>
            {labelKind === 'ITEM' ? (
              <SectionCard title={t('clients.extraction_profile.templates_gallery')} variant="outlined">
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                  {LABEL_RECOGNITION_TEMPLATES.map((template) => (
                    <Button
                      key={template.id}
                      variant="outlined"
                      size="small"
                      onClick={() => updateDraft({ configuration: template.build() })}
                    >
                      {t(template.labelKey)}
                    </Button>
                  ))}
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  {t('clients.extraction_profile.templates_no_autosave')}
                </Typography>
              </SectionCard>
            ) : null}
            <BarcodeRulesSection configuration={draft.configuration} onChange={(configuration) => updateDraft({ configuration })} />
            <PayloadStructureSection configuration={draft.configuration} labelKind={labelKind} onChange={(configuration) => updateDraft({ configuration })} />
            <QuantityRulesSection configuration={draft.configuration} onChange={(configuration) => updateDraft({ configuration })} />
            <VisualHintsSection
              configuration={draft.configuration}
              visualNotes={draft.visualNotes}
              onConfigurationChange={(configuration) => updateDraft({ configuration })}
              onVisualNotesChange={(visualNotes) => updateDraft({ visualNotes })}
            />
            <ReferenceImagesSection
              clientId={clientId}
              supplierId={supplierId}
              supplierName={supplierName}
              labelKind={labelKind}
            />
            <ExamplesEditor
              validExamples={draft.configuration.valid_examples ?? []}
              invalidExamples={draft.configuration.invalid_examples ?? []}
              onChange={(valid_examples, invalid_examples) =>
                updateDraft({ configuration: { ...draft.configuration, valid_examples, invalid_examples } })
              }
            />
            <LabelRecognitionTester
              clientId={clientId}
              supplierId={supplierId}
              labelKind={labelKind}
              configuration={draft.configuration}
            />
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <Button variant="contained" disabled={createMutation.isPending} onClick={() => void handleSave(true)}>
                {t('clients.extraction_profile.save_and_activate')}
              </Button>
              <Button variant="outlined" disabled={createMutation.isPending} onClick={() => void handleSave(false)}>
                {t('clients.extraction_profile.save_without_activating')}
              </Button>
            </Box>
            {createMutation.isError ? (
              <Alert severity="error">
                {resolveApiErrorMessage(createMutation.error, 'clients.extraction_profile.create_error')}
              </Alert>
            ) : null}
          </>
        ) : null}
      </Stack>
    </Box>
  );
}
