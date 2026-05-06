import { Paper, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

type CompareDiffRow = {
  match_key: string;
  side: string;
  quantity_a?: number | null;
  quantity_b?: number | null;
  sku_a?: string | null;
  sku_b?: string | null;
  position_code_a?: string | null;
  position_code_b?: string | null;
};

type CompareDiffSummary = {
  keys_only_in_a: number;
  keys_only_in_b: number;
  keys_in_both: number;
  quantity_changed: number;
  sku_changed: number;
  position_code_changed: number;
};

type CompareDiffTableProps = {
  summary: CompareDiffSummary;
  rows: CompareDiffRow[];
  rowsTruncated: boolean;
};

export default function CompareDiffTable({ summary, rows, rowsTruncated }: CompareDiffTableProps) {
  const { t } = useTranslation();

  return (
    <>
      <Paper sx={{ p: 2 }} variant="outlined">
        <Typography variant="subtitle1" gutterBottom>
          {t('compare.diff_summary_title')}
        </Typography>
        <Typography variant="body2">
          {t('compare.diff_summary_stats', {
            onlyA: summary.keys_only_in_a,
            onlyB: summary.keys_only_in_b,
            both: summary.keys_in_both,
            qty: summary.quantity_changed,
            sku: summary.sku_changed,
            pos: summary.position_code_changed,
          })}
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
          {t('compare.diff_summary_note')}
        </Typography>
      </Paper>

      <Paper sx={{ p: 2 }} variant="outlined">
        <Typography variant="subtitle1" gutterBottom>
          {t('compare.diff_rows_title')} {rowsTruncated ? t('compare.diff_rows_truncated') : ''}
        </Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('compare.col_key')}</TableCell>
              <TableCell>{t('compare.col_side')}</TableCell>
              <TableCell align="right">{t('compare.col_qty_a')}</TableCell>
              <TableCell align="right">{t('compare.col_qty_b')}</TableCell>
              <TableCell>{t('compare.col_sku_a')}</TableCell>
              <TableCell>{t('compare.col_sku_b')}</TableCell>
              <TableCell>{t('compare.col_pos_a')}</TableCell>
              <TableCell>{t('compare.col_pos_b')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={`${row.match_key}-${row.side}`}>
                <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{row.match_key}</TableCell>
                <TableCell>{row.side}</TableCell>
                <TableCell align="right">{row.quantity_a ?? t('common.em_dash')}</TableCell>
                <TableCell align="right">{row.quantity_b ?? t('common.em_dash')}</TableCell>
                <TableCell>{row.sku_a ?? t('common.em_dash')}</TableCell>
                <TableCell>{row.sku_b ?? t('common.em_dash')}</TableCell>
                <TableCell>{row.position_code_a ?? t('common.em_dash')}</TableCell>
                <TableCell>{row.position_code_b ?? t('common.em_dash')}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {rows.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t('compare.no_diff_rows')}
          </Typography>
        ) : null}
      </Paper>
    </>
  );
}
