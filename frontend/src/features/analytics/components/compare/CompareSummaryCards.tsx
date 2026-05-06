import { Box, Paper, Table, TableBody, TableCell, TableRow, Tooltip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { formatCostDisplay, runExecutionDisplay } from '../../adapters/compareFormatters';

type CompareRunSummary = {
  job_id: string;
  status: string;
  provider_name?: string | null;
  model_name?: string | null;
  prompt_key?: string | null;
  prompt_version?: string | null;
  created_at: string;
  execution_time_human?: string | null;
  execution_time_seconds?: number | null;
  metrics: {
    consolidated_positions: number;
    total_quantity: number;
    unknown_internal_code_count: number;
    needs_review_count: number;
  };
  llm_cost_snapshot?: {
    billing_currency?: string | null;
    pricing_available?: boolean | null;
    model?: string | null;
    computed_cost?: {
      total_cost?: string | null;
      currency?: string | null;
      total_cost_unavailable_reason?: string | null;
    };
    capture_status?: string;
    capture_notes?: string[];
  } | null;
};

type CompareSummaryCardsProps = {
  runA: CompareRunSummary;
  runB: CompareRunSummary;
};

export default function CompareSummaryCards({ runA, runB }: CompareSummaryCardsProps) {
  const { t } = useTranslation();

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
      {[
        { side: 'run_a' as const, run: runA },
        { side: 'run_b' as const, run: runB },
      ].map(({ side, run: r }) => {
        const cost = formatCostDisplay(r, t);
        return (
          <Paper key={side} sx={{ p: 2, flex: '1 1 320px' }} variant="outlined">
            <Typography variant="subtitle2" color="text.secondary">
              {side === 'run_a' ? t('results.run_a_label') : t('results.run_b_label')}
            </Typography>
            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
              {r.job_id}
            </Typography>
            <Typography variant="caption" display="block" color="text.secondary">
              {r.status} · {r.provider_name ?? t('common.em_dash')} · {r.model_name ?? t('common.em_dash')} ·{' '}
              {r.prompt_key ?? t('common.em_dash')} · {r.prompt_version ?? t('common.em_dash')}
            </Typography>
            <Typography variant="caption" display="block" color="text.secondary">
              {t('compare.created_at', { date: r.created_at })}
            </Typography>
            <Table size="small" sx={{ mt: 1 }}>
              <TableBody>
                <TableRow>
                  <TableCell>{t('compare.metric_execution_time')}</TableCell>
                  <TableCell align="right">{runExecutionDisplay(r, t)}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>{t('compare.metric_consolidated')}</TableCell>
                  <TableCell align="right">{r.metrics.consolidated_positions}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>{t('compare.metric_total_qty')}</TableCell>
                  <TableCell align="right">{r.metrics.total_quantity}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>{t('compare.metric_unknown_code')}</TableCell>
                  <TableCell align="right">{r.metrics.unknown_internal_code_count}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>{t('compare.metric_needs_review')}</TableCell>
                  <TableCell align="right">{r.metrics.needs_review_count}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>{t('compare.metric_total_cost')}</TableCell>
                  <TableCell align="right">
                    {cost.details ? (
                      <Tooltip title={cost.details}>
                        <span>{cost.value}</span>
                      </Tooltip>
                    ) : (
                      cost.value
                    )}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </Paper>
        );
      })}
    </Box>
  );
}
