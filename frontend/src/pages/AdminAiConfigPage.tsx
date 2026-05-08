import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  Stack,
  Tab,
  Tabs,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { getAdminAiComposedPrompt, getAdminAiConfig } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import {
  ApiError,
  type AdminAiConfigPromptVariantSummary,
  type AdminAiConfigProviderDetail,
} from '../api/types';
import {
  BulletList,
  CopyableMonospaceBlock,
  EmptyInspectorState,
  KeyValueSummary,
  SelectableOutlineCard,
} from '../components/adminAiInspector/InspectorPrimitives';
import PageHeader from '../components/shell/PageHeader';

const INSPECTOR_TAB_KEYS = ['overview', 'instructions', 'response_contract', 'prompts', 'composition'] as const;
type InspectorTabKey = (typeof INSPECTOR_TAB_KEYS)[number];

const TAB_LABEL_KEYS: Record<InspectorTabKey, string> = {
  overview: 'admin_ai_config.tab_overview',
  instructions: 'admin_ai_config.tab_instructions',
  response_contract: 'admin_ai_config.tab_response_contract',
  prompts: 'admin_ai_config.tab_prompts',
  composition: 'admin_ai_config.tab_composition',
};

function formatGeneratedAtDisplay(iso: string, locale: string): string {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return iso;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(ms);
}

function TabPanel({
  children,
  value,
  id,
}: {
  children: React.ReactNode;
  value: InspectorTabKey;
  id: InspectorTabKey;
}) {
  if (value !== id) return null;
  return (
    <Box
      role="tabpanel"
      id={`admin-ai-tabpanel-${id}`}
      aria-labelledby={`admin-ai-tab-${id}`}
      sx={{ pt: 2 }}
    >
      {children}
    </Box>
  );
}

export default function AdminAiConfigPage() {
  const { t, i18n } = useTranslation();
  const q = useQuery({
    queryKey: queryKeys.admin.aiConfig(),
    queryFn: getAdminAiConfig,
  });

  const [selectedProviderKey, setSelectedProviderKey] = useState<string | null>(null);
  const [selectedPromptKey, setSelectedPromptKey] = useState<string | null>(null);
  const [tab, setTab] = useState<InspectorTabKey>('overview');
  const [composeTarget, setComposeTarget] = useState<{
    prompt_key: string;
    prompt_parity_mode: boolean;
  } | null>(null);

  const data = q.data;

  const effectiveProviderKey = useMemo(() => {
    if (selectedProviderKey) return selectedProviderKey;
    if (!data) return null;
    const def = data.server_defaults.llm_provider;
    const match = data.providers.find((p) => p.key === def);
    return match?.key ?? data.providers[0]?.key ?? null;
  }, [data, selectedProviderKey]);

  const effectivePromptKey = useMemo(() => {
    if (selectedPromptKey) return selectedPromptKey;
    return data?.server_defaults.hybrid_prompt_key ?? null;
  }, [data, selectedPromptKey]);

  const provider: AdminAiConfigProviderDetail | undefined = useMemo(() => {
    if (!data || !effectiveProviderKey) return undefined;
    return data.providers.find((p) => p.key === effectiveProviderKey);
  }, [data, effectiveProviderKey]);

  const composedQ = useQuery({
    queryKey: queryKeys.admin.aiComposedPrompt(
      provider?.key ?? '',
      composeTarget?.prompt_key ?? '',
      composeTarget?.prompt_parity_mode ?? false
    ),
    queryFn: () =>
      getAdminAiComposedPrompt({
        pipeline_provider_key: provider!.key,
        prompt_key: composeTarget!.prompt_key,
        prompt_parity_mode: composeTarget!.prompt_parity_mode,
      }),
    enabled: Boolean(provider && composeTarget && composeTarget.prompt_key === effectivePromptKey && tab === 'prompts'),
  });

  const onRefresh = useCallback(() => {
    void q.refetch();
  }, [q]);

  const filteredSummaries: AdminAiConfigPromptVariantSummary[] = useMemo(() => {
    if (!provider || !effectivePromptKey) return [];
    return provider.prompt_variant_summaries.filter((v) => v.prompt_key === effectivePromptKey);
  }, [provider, effectivePromptKey]);

  const generatedDisplay = data ? formatGeneratedAtDisplay(data.generated_at, i18n.language) : '';

  if (q.isLoading) {
    return (
      <Box sx={{ p: 2 }}>
        <PageHeader title={t('routes.admin_ai_config.title')} />
        <Typography color="text.secondary">{t('common.loading')}</Typography>
      </Box>
    );
  }

  if (q.isError) {
    const status = q.error instanceof ApiError ? q.error.status : undefined;
    const isForbidden = status === 403;
    return (
      <Box sx={{ p: 2 }}>
        <PageHeader title={t('routes.admin_ai_config.title')} />
        <Alert severity={isForbidden ? 'warning' : 'error'} sx={{ mt: 2 }}>
          {isForbidden
            ? t('admin_ai_config.error_forbidden')
            : t('admin_ai_config.error_load')}
        </Alert>
        <Button sx={{ mt: 2 }} variant="outlined" onClick={() => q.refetch()}>
          {t('common.retry')}
        </Button>
      </Box>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1280, mx: 'auto' }}>
      <PageHeader
        title={t('routes.admin_ai_config.title')}
        subtitle={
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="body2" color="text.secondary" component="span">
              {t('routes.admin_ai_config.subtitle')}
            </Typography>
            <Chip
              size="small"
              label={t('admin_ai_config.admin_only_badge')}
              color="warning"
              variant="outlined"
            />
          </Stack>
        }
        actions={
          <Button size="small" variant="outlined" onClick={onRefresh}>
            {t('common.refresh')}
          </Button>
        }
      />

      <Box sx={{ mb: 2 }}>
        <Typography variant="body2" color="text.secondary">
          {t('admin_ai_config.generated_at_formatted', { value: generatedDisplay })}
        </Typography>
        <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 0.5, mb: 0 }}>
          {t('admin_ai_config.generated_at_raw', { value: data.generated_at })}
        </Typography>
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12} md={4}>
          <Typography variant="overline" color="text.secondary" display="block" sx={{ mb: 1 }}>
            {t('admin_ai_config.pick_provider')}
          </Typography>
          <Stack spacing={1.5} role="radiogroup" aria-label={t('admin_ai_config.pick_provider')}>
            {data.providers.map((p) => (
              <SelectableOutlineCard
                key={p.key}
                selected={p.key === effectiveProviderKey}
                onClick={() => {
                  setSelectedProviderKey(p.key);
                  setTab('overview');
                  setComposeTarget(null);
                }}
                title={p.label}
                subtitle={p.key}
                accessibilityLabel={t('admin_ai_config.provider_card_a11y', {
                  name: p.label,
                  key: p.key,
                })}
                footer={
                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                    {p.capabilities.is_default_pipeline_provider ? (
                      <Chip size="small" label={t('admin_ai_config.default_provider_chip')} />
                    ) : null}
                    {p.capabilities.credential_configured ? (
                      <Chip size="small" color="success" variant="outlined" label={t('admin_ai_config.configured')} />
                    ) : (
                      <Chip size="small" variant="outlined" label={t('admin_ai_config.not_configured')} />
                    )}
                  </Stack>
                }
              />
            ))}
          </Stack>
        </Grid>

        <Grid item xs={12} md={8}>
          {!provider ? (
            <EmptyInspectorState message={t('admin_ai_config.empty_no_provider')} />
          ) : (
            <>
              <Tabs
                value={tab}
                onChange={(_, v) => setTab(v as InspectorTabKey)}
                variant="scrollable"
                scrollButtons="auto"
                aria-label={t('admin_ai_config.tabs_aria')}
              >
                {INSPECTOR_TAB_KEYS.map((id) => (
                  <Tab
                    key={id}
                    id={`admin-ai-tab-${id}`}
                    aria-controls={`admin-ai-tabpanel-${id}`}
                    value={id}
                    label={t(TAB_LABEL_KEYS[id])}
                  />
                ))}
              </Tabs>

              <TabPanel value={tab} id="overview">
                <Stack spacing={2}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {t('admin_ai_config.section_server_defaults')}
                      </Typography>
                      <KeyValueSummary
                        rows={[
                          {
                            label: t('admin_ai_config.default_llm_provider'),
                            value: data.server_defaults.llm_provider,
                          },
                          {
                            label: t('admin_ai_config.hybrid_prompt_key'),
                            value: data.server_defaults.hybrid_prompt_key,
                          },
                          {
                            label: t('admin_ai_config.prompt_version'),
                            value: data.server_defaults.prompt_version ?? t('common.em_dash'),
                          },
                        ]}
                      />
                    </CardContent>
                  </Card>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {provider.label} — {t('admin_ai_config.overview_provider')}
                      </Typography>
                      <KeyValueSummary
                        rows={[
                          {
                            label: t('admin_ai_config.credentials'),
                            value: provider.capabilities.credential_configured ? (
                              <Chip size="small" color="success" label={t('admin_ai_config.configured')} />
                            ) : (
                              <Chip size="small" label={t('admin_ai_config.not_configured')} />
                            ),
                          },
                          {
                            label: t('admin_ai_config.multimodal'),
                            value: provider.capabilities.multimodal_aisle_analysis_supported
                              ? t('common.yes')
                              : t('common.no'),
                          },
                          {
                            label: t('admin_ai_config.default_model'),
                            value: provider.default_model ?? t('common.em_dash'),
                          },
                          {
                            label: t('admin_ai_config.execution_mode'),
                            value:
                              provider.capabilities.execution_mode === 'native'
                                ? t('admin_ai_config.execution_mode_native')
                                : provider.capabilities.execution_mode,
                          },
                        ]}
                      />
                      <Typography variant="subtitle2" sx={{ mt: 2, mb: 0.5 }}>
                        {t('admin_ai_config.configured_models_readonly')}
                      </Typography>
                      {provider.models.length === 0 ? (
                        <Typography variant="body2" color="text.secondary">
                          {t('admin_ai_config.no_models_configured')}
                        </Typography>
                      ) : (
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                          {provider.models.map((m) => (
                            <Chip
                              key={m.id}
                              size="small"
                              label={m.is_default ? `${m.label} *` : m.label}
                              variant="outlined"
                            />
                          ))}
                        </Stack>
                      )}
                      {provider.description ? (
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                          {provider.key === 'gemini'
                            ? t('admin_ai_config.provider_note_gemini')
                            : provider.description}
                        </Typography>
                      ) : null}
                    </CardContent>
                  </Card>
                </Stack>
              </TabPanel>

              <TabPanel value={tab} id="instructions">
                <Stack spacing={2}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {t('admin_ai_config.instructions_global')}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                        {t('admin_ai_config.instructions_global_caption')}
                      </Typography>
                      <CopyableMonospaceBlock
                        text={data.global_instructions_note}
                        aria-label="global-instructions"
                        copyLabel={t('admin_ai_config.copy')}
                      />
                    </CardContent>
                  </Card>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {t('admin_ai_config.instructions_provider', { name: provider.label })}
                      </Typography>
                      <CopyableMonospaceBlock
                        text={provider.instructions.provider_specific_note || t('common.em_dash')}
                        aria-label="provider-instructions"
                        copyLabel={t('admin_ai_config.copy')}
                      />
                    </CardContent>
                  </Card>
                </Stack>
              </TabPanel>

              <TabPanel value={tab} id="response_contract">
                <Stack spacing={2}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {t('admin_ai_config.response_contract_title')}
                      </Typography>
                      <KeyValueSummary
                        rows={[
                          {
                            label: t('admin_ai_config.expects_json'),
                            value: provider.response_contract.expects_json ? t('common.yes') : t('common.no'),
                          },
                          {
                            label: t('admin_ai_config.response_wire_transport'),
                            value: (
                              <Typography variant="body2" component="span" fontFamily="monospace">
                                {provider.response_contract.wire_transport}
                              </Typography>
                            ),
                          },
                          {
                            label: t('admin_ai_config.validation_fn'),
                            value: (
                              <Typography variant="body2" component="span" fontFamily="monospace">
                                {provider.response_contract.validation_function}
                              </Typography>
                            ),
                          },
                          {
                            label: t('admin_ai_config.normalization_fn'),
                            value: (
                              <Typography variant="body2" component="span" fontFamily="monospace">
                                {provider.response_contract.normalization_function}
                              </Typography>
                            ),
                          },
                          {
                            label: t('admin_ai_config.normalization_family'),
                            value: (
                              <Typography variant="body2" component="span" fontFamily="monospace">
                                {provider.response_contract.normalization_family}
                              </Typography>
                            ),
                          },
                          {
                            label: t('admin_ai_config.response_alias_policy'),
                            value: (
                              <Typography variant="body2" component="span" fontFamily="monospace">
                                {provider.response_contract.alias_promotion_policy}
                              </Typography>
                            ),
                          },
                          {
                            label: t('admin_ai_config.response_claude_mapping'),
                            value: provider.response_contract.claude_product_label_to_internal_code_when_valid
                              ? t('common.yes')
                              : t('common.no'),
                          },
                          {
                            label: t('admin_ai_config.required_root_keys'),
                            value: (
                              <Typography variant="body2" fontFamily="monospace">
                                {provider.response_contract.required_root_keys.join(', ')}
                              </Typography>
                            ),
                          },
                          {
                            label: t('admin_ai_config.required_entity_keys'),
                            value: (
                              <Typography variant="body2" fontFamily="monospace">
                                {provider.response_contract.required_entity_keys.join(', ')}
                              </Typography>
                            ),
                          },
                          {
                            label: t('admin_ai_config.extra_root_policy'),
                            value: provider.response_contract.extra_root_keys_policy_short,
                          },
                        ]}
                      />
                      <Typography variant="subtitle2" sx={{ mt: 2, mb: 0.5 }}>
                        {t('admin_ai_config.nullable_entity_keys')}
                      </Typography>
                      <Typography variant="body2" fontFamily="monospace" sx={{ mb: 2 }}>
                        {provider.response_contract.nullable_optional_entity_keys.join(', ')}
                      </Typography>
                      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                        {t('admin_ai_config.transport_notes_heading')}
                      </Typography>
                      <BulletList items={provider.response_contract.transport_notes} />
                      <Typography variant="subtitle2" sx={{ mt: 2, mb: 0.5 }}>
                        {t('admin_ai_config.example_json_title')}
                      </Typography>
                      <CopyableMonospaceBlock
                        text={provider.response_contract.canonical_example_json}
                        maxHeight={320}
                        copyLabel={t('admin_ai_config.copy')}
                        aria-label="canonical-example-json"
                      />
                    </CardContent>
                  </Card>
                </Stack>
              </TabPanel>

              <TabPanel value={tab} id="prompts">
                <Stack spacing={2}>
                  <Typography variant="body2" color="text.secondary">
                    {t('admin_ai_config.prompts_intro_lazy')}
                  </Typography>
                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                    {data.prompt_catalog.length === 0 ? (
                      <Typography variant="body2" color="text.secondary">
                        {t('admin_ai_config.empty_prompt_catalog')}
                      </Typography>
                    ) : (
                      data.prompt_catalog.map((row) => (
                        <Chip
                          key={row.key}
                          size="small"
                          label={row.key}
                          color={row.key === effectivePromptKey ? 'primary' : 'default'}
                          variant={row.key === effectivePromptKey ? 'filled' : 'outlined'}
                          onClick={() => {
                            setSelectedPromptKey(row.key);
                            setComposeTarget(null);
                          }}
                          sx={{ cursor: 'pointer' }}
                        />
                      ))
                    )}
                  </Stack>
                  {effectivePromptKey ? (
                    <Typography variant="caption" color="text.secondary">
                      {data.prompt_catalog.find((c) => c.key === effectivePromptKey)?.description ?? ''}
                    </Typography>
                  ) : null}
                  {filteredSummaries.length === 0 ? (
                    <EmptyInspectorState message={t('admin_ai_config.empty_variants')} />
                  ) : (
                    <Stack spacing={2}>
                      {filteredSummaries.map((s) => {
                        const active =
                          composeTarget &&
                          composeTarget.prompt_key === s.prompt_key &&
                          composeTarget.prompt_parity_mode === s.prompt_parity_mode;
                        return (
                          <Card key={s.variant_label} variant="outlined">
                            <CardContent>
                              <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
                                <Chip size="small" label={s.prompt_key} />
                                <Chip
                                  size="small"
                                  variant="outlined"
                                  label={
                                    s.prompt_parity_mode
                                      ? t('admin_ai_config.parity_on')
                                      : t('admin_ai_config.parity_off')
                                  }
                                />
                                <Button
                                  size="small"
                                  variant="outlined"
                                  onClick={() =>
                                    setComposeTarget({
                                      prompt_key: s.prompt_key,
                                      prompt_parity_mode: s.prompt_parity_mode,
                                    })
                                  }
                                >
                                  {t('admin_ai_config.load_composed_prompt')}
                                </Button>
                              </Stack>
                              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                                {s.variant_label}
                              </Typography>
                              {active && composedQ.isFetching ? (
                                <Typography variant="body2" sx={{ mt: 1 }}>
                                  {t('admin_ai_config.composed_prompt_loading')}
                                </Typography>
                              ) : null}
                              {active && composedQ.isError ? (
                                <Alert severity="error" sx={{ mt: 1 }}>
                                  {t('admin_ai_config.composed_prompt_error')}
                                </Alert>
                              ) : null}
                              {active && composedQ.isSuccess ? (
                                <Box sx={{ mt: 1 }} data-testid="composed-prompt-body">
                                  <CopyableMonospaceBlock
                                    text={composedQ.data.composed_prompt_text}
                                    maxHeight={480}
                                    copyLabel={t('admin_ai_config.copy_prompt')}
                                    aria-label={`composed-prompt-${s.variant_label}`}
                                  />
                                </Box>
                              ) : null}
                            </CardContent>
                          </Card>
                        );
                      })}
                    </Stack>
                  )}
                </Stack>
              </TabPanel>

              <TabPanel value={tab} id="composition">
                <Stack spacing={2}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {t('admin_ai_config.composition_title')}
                      </Typography>
                      <KeyValueSummary
                        rows={[
                          {
                            label: t('admin_ai_config.composition_hybrid_base_mode'),
                            value: (
                              <Typography variant="body2" fontFamily="monospace">
                                {provider.composition.hybrid_base_mode}
                              </Typography>
                            ),
                          },
                          {
                            label: t('admin_ai_config.composition_parity_affects'),
                            value: provider.composition.parity_mode_affects_prompt_assembly
                              ? t('common.yes')
                              : t('common.no'),
                          },
                          {
                            label: t('admin_ai_config.composition_multimodal_policy'),
                            value: (
                              <Typography variant="body2" fontFamily="monospace">
                                {provider.composition.multimodal_context_policy}
                              </Typography>
                            ),
                          },
                        ]}
                      />
                    </CardContent>
                  </Card>
                </Stack>
              </TabPanel>
            </>
          )}
        </Grid>
      </Grid>
    </Box>
  );
}
