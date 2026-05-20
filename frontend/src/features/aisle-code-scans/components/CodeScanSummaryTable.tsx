import { useTranslation } from 'react-i18next';
import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import type { CodeScanSummaryItem } from '../../../api/types/codeScans';
import { formatDate } from '../../../utils/formatDate';
import { formatCodeScanCodeType } from '../formatters';
import CopyCodeValueButton from './CopyCodeValueButton';

export interface CodeScanSummaryTableProps {
  items: CodeScanSummaryItem[];
}

export default function CodeScanSummaryTable({ items }: CodeScanSummaryTableProps) {
  const { t } = useTranslation();

  if (!items.length) return null;

  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('aisleCodeScans.tables.summarySection')}
      </Typography>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('aisleCodeScans.tables.type')}</TableCell>
              <TableCell>{t('aisleCodeScans.tables.value')}</TableCell>
              <TableCell align="right">{t('aisleCodeScans.tables.occurrences')}</TableCell>
              <TableCell>{t('aisleCodeScans.tables.assets')}</TableCell>
              <TableCell>{t('aisleCodeScans.tables.firstSeenAt')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.map((row) => (
              <TableRow key={`${row.normalized_code_value}-${row.code_type}`}>
                <TableCell>{formatCodeScanCodeType(t, row.code_type)}</TableCell>
                <TableCell sx={{ maxWidth: 280 }}>
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.5 }}>
                    <Typography
                      variant="body2"
                      component="span"
                      sx={{ wordBreak: 'break-all', whiteSpace: 'pre-wrap' }}
                    >
                      {row.code_value}
                    </Typography>
                    <CopyCodeValueButton value={row.code_value} />
                  </Box>
                </TableCell>
                <TableCell align="right">{row.occurrences}</TableCell>
                <TableCell sx={{ wordBreak: 'break-all' }}>{row.asset_ids.join(', ')}</TableCell>
                <TableCell>{formatDate(row.first_seen_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
