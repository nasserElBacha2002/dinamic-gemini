import { useCallback, useEffect, useMemo, useState } from 'react';
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
import { getAdminAiConfig } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import {
  ApiError,
  type AdminAiConfigProviderDetail,
  type AdminAiConfigPromptVariant,
} from '../api/types';
import {
  BulletList,
  CopyableMonospaceBlock,
  EmptyInspectorState,
  KeyValueSummary,
  SelectableOutlineCard,
} from '../components/adminAiInspector/InspectorPrimitives';
import PageHeader from '../components/shell/PageHeader';

function TabPanel({ children, value, index }: { children: React.ReactNode; value: number; index: number }) {
  if (value !== index) return null;
  return (
    <Box role="tabpanel" sx={{ pt: 2 }}>
      {children}
    </Box>
  );
}

export default function AdminAiConfigPage() {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: queryKeys.admin.aiConfig(),
    queryFn: getAdminAiConfig,
  });

  const [selectedProviderKey, setSelectedProviderKey] = useState<string | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [selectedPromptKey, setSelectedPromptKey] = useState<string | null>(null);
  const [tab, setTab] = useState(0);

  const data = q.data;

  useEffect(() => {
    if (!data) return;
    setSelectedProviderKey((cur) => {
      if (cur) return cur;
      const def = data.server_defaults.llm_provider;
      const match = data.providers.find((p) => p.key === def);
      return match?.key ?? data.providers[0]?.key ?? null;
    });
    setSelectedPromptKey((k) => k ?? data.server_defaults.hybrid_prompt_key);
  }, [data]);

  const provider: AdminAiConfigProviderDetail | undefined = useMemo(() => {
    if (!data || !selectedProviderKey) return undefined;
    return data.providers.find((p) => p.key === selectedProviderKey);
  }, [data, selectedProviderKey]);

  useEffect(() => {
    if (!provider) return;
    const def = provider.models.find((m) => m.is_default)?.id ?? provider.models[0]?.id ?? null;
    setSelectedModelId(def);
  }, [provider]);

  const onRefresh = useCallback(() => {
    void q.refetch();
  }, [q]);

  const filteredVariants: AdminAiConfigPromptVariant[] = useMemo(() => {
    if (!provider || !selectedPromptKey) return [];
    return provider.prompt_variants.filter((v) => v.prompt_key === selectedPromptKey);
  }, [provider, selectedPromptKey]);

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

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t('admin_ai_config.generated_at', { value: data.generated_at })}
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} md={4}>
          <Typography variant="overline" color="text.secondary" display="block" sx={{ mb: 1 }}>
            {t('admin_ai_config.pick_provider')}
          </Typography>
          <Stack spacing={1.5}>
            {data.providers.map((p) => (
              <SelectableOutlineCard
                key={p.key}
                selected={p.key === selectedProviderKey}
                onClick={() => {
                  setSelectedProviderKey(p.key);
                  setTab(0);
                }}
                title={p.label}
                subtitle={p.key}
                footer={
                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                    {p.overview.is_default_pipeline_provider ? (
                      <Chip size="small" label={t('admin_ai_config.default_provider_chip')} />
                    ) : null}
                    {p.overview.credential_configured ? (
                      <Chip size="small" color="success" variant="outlined" label={t('admin_ai_config.configured')} />
                    ) : (
                      <Chip size="small" variant="outlined" label={t('admin_ai_config.not_configured')} />
                    )}
                  </Stack>
                }
              />
            ))}
          </Stack>

          {provider ? (
            <Box sx={{ mt: 3 }}>
              <Typography variant="overline" color="text.secondary" display="block" sx={{ mb: 1 }}>
                {t('admin_ai_config.pick_model')}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                {t('admin_ai_config.model_hint')}
              </Typography>
              <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                {provider.models.map((m) => (
                  <Chip
                    key={m.id}
                    size="small"
                    label={m.is_default ? `${m.label} *` : m.label}
                    color={m.id === selectedModelId ? 'primary' : 'default'}
                    variant={m.id === selectedModelId ? 'filled' : 'outlined'}
                    onClick={() => setSelectedModelId(m.id)}
                    sx={{ cursor: 'pointer' }}
                  />
                ))}
              </Stack>
            </Box>
          ) : null}
        </Grid>

        <Grid item xs={12} md={8}>
          {!provider ? (
            <EmptyInspectorState message={t('admin_ai_config.empty_no_provider')} />
          ) : (
            <>
              <Tabs
                value={tab}
                onChange={(_, v) => setTab(v)}
                variant="scrollable"
                scrollButtons="auto"
                aria-label={t('admin_ai_config.tabs_aria')}
              >
                <Tab label={t('admin_ai_config.tab_overview')} />
                <Tab label={t('admin_ai_config.tab_instructions')} />
                <Tab label={t('admin_ai_config.tab_response_contract')} />
                <Tab label={t('admin_ai_config.tab_prompts')} />
                <Tab label={t('admin_ai_config.tab_composition')} />
              </Tabs>

              <TabPanel value={tab} index={0}>
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
                            value: provider.overview.credential_configured ? (
                              <Chip size="small" color="success" label={t('admin_ai_config.configured')} />
                            ) : (
                              <Chip size="small" label={t('admin_ai_config.not_configured')} />
                            ),
                          },
                          {
                            label: t('admin_ai_config.operational'),
                            value: provider.overview.operationally_available ? t('common.yes') : t('common.no'),
                          },
                          {
                            label: t('admin_ai_config.multimodal'),
                            value: provider.overview.multimodal_aisle_analysis_supported
                              ? t('common.yes')
                              : t('common.no'),
                          },
                          {
                            label: t('admin_ai_config.default_model'),
                            value: provider.default_model ?? t('common.em_dash'),
                          },
                          {
                            label: t('admin_ai_config.selected_model'),
                            value: selectedModelId ?? t('common.em_dash'),
                          },
                          {
                            label: t('admin_ai_config.execution_mode'),
                            value: provider.overview.execution_mode,
                          },
                        ]}
                      />
                      {provider.description ? (
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                          {provider.description}
                        </Typography>
                      ) : null}
                    </CardContent>
                  </Card>
                </Stack>
              </TabPanel>

              <TabPanel value={tab} index={1}>
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

              <TabPanel value={tab} index={2}>
                <Stack spacing={2}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {t('admin_ai_config.response_raw_title')}
                      </Typography>
                      <Typography variant="body2" sx={{ mb: 1 }}>
                        {provider.response_contract.raw_provider_expectation}
                      </Typography>
                      <Typography variant="subtitle2" sx={{ mt: 2, mb: 0.5 }}>
                        {t('admin_ai_config.wire_notes')}
                      </Typography>
                      <BulletList items={provider.response_contract.provider_wire_notes} />
                    </CardContent>
                  </Card>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {t('admin_ai_config.response_canonical_title')}
                      </Typography>
                      <Typography variant="body2" sx={{ mb: 2 }}>
                        {provider.response_contract.canonical_contract_summary}
                      </Typography>
                      <KeyValueSummary
                        rows={[
                          {
                            label: t('admin_ai_config.expects_json'),
                            value: provider.response_contract.expects_json ? t('common.yes') : t('common.no'),
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
                            value: provider.response_contract.extra_root_keys_policy,
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
                        {t('admin_ai_config.normalization_notes_heading')}
                      </Typography>
                      <BulletList items={provider.response_contract.normalization_notes} />
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

              <TabPanel value={tab} index={3}>
                <Stack spacing={2}>
                  <Typography variant="body2" color="text.secondary">
                    {t('admin_ai_config.prompts_intro')}
                  </Typography>
                  <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                    {data.prompt_catalog.map((row) => (
                      <Chip
                        key={row.key}
                        size="small"
                        label={row.key}
                        color={row.key === selectedPromptKey ? 'primary' : 'default'}
                        variant={row.key === selectedPromptKey ? 'filled' : 'outlined'}
                        onClick={() => setSelectedPromptKey(row.key)}
                        sx={{ cursor: 'pointer' }}
                      />
                    ))}
                  </Stack>
                  {selectedPromptKey ? (
                    <Typography variant="caption" color="text.secondary">
                      {data.prompt_catalog.find((c) => c.key === selectedPromptKey)?.description ?? ''}
                    </Typography>
                  ) : null}
                  {filteredVariants.length === 0 ? (
                    <EmptyInspectorState message={t('admin_ai_config.empty_variants')} />
                  ) : (
                    <Stack spacing={2}>
                      {filteredVariants.map((v) => (
                        <Card key={v.variant_label} variant="outlined">
                          <CardContent>
                            <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
                              <Chip size="small" label={v.prompt_key} />
                              <Chip
                                size="small"
                                variant="outlined"
                                label={
                                  v.prompt_parity_mode
                                    ? t('admin_ai_config.parity_on')
                                    : t('admin_ai_config.parity_off')
                                }
                              />
                            </Stack>
                            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                              {v.variant_label}
                            </Typography>
                            <CopyableMonospaceBlock
                              text={v.composed_prompt_text}
                              maxHeight={480}
                              copyLabel={t('admin_ai_config.copy_prompt')}
                              aria-label={`composed-prompt-${v.variant_label}`}
                            />
                          </CardContent>
                        </Card>
                      ))}
                    </Stack>
                  )}
                </Stack>
              </TabPanel>

              <TabPanel value={tab} index={4}>
                <Stack spacing={2}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {t('admin_ai_config.composition_hybrid')}
                      </Typography>
                      <Typography variant="body2">{provider.composition_notes.hybrid_base_resolution}</Typography>
                    </CardContent>
                  </Card>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {t('admin_ai_config.composition_parity')}
                      </Typography>
                      <Typography variant="body2">{provider.composition_notes.parity_mode}</Typography>
                    </CardContent>
                  </Card>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {t('admin_ai_config.composition_multimodal')}
                      </Typography>
                      <Typography variant="body2">{provider.composition_notes.multimodal_context_rules}</Typography>
                    </CardContent>
                  </Card>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                        {t('admin_ai_config.composition_summary')}
                      </Typography>
                      <CopyableMonospaceBlock
                        text={
                          provider.composition_notes.bullets.length > 0
                            ? provider.composition_notes.bullets
                                .filter(Boolean)
                                .map((line) => `• ${line}`)
                                .join('\n')
                            : t('common.em_dash')
                        }
                        copyLabel={t('admin_ai_config.copy')}
                        aria-label="composition-bullets"
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
