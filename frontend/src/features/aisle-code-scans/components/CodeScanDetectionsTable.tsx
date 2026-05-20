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
import type { CodeScanDetection } from '../../../api/types/codeScans';
import { formatDate } from '../../../utils/formatDate';
import { formatCodeScanCodeType, formatCodeScanDetectionStatus } from '../formatters';
import CodeScanAssetPreviewButton from './CodeScanAssetPreviewButton';
import CopyCodeValueButton from './CopyCodeValueButton';

export interface CodeScanDetectionsTableProps {
  detections: CodeScanDetection[];
  inventoryId: string;
  aisleId: string;
  jobIdForPreview?: string | null;
}

export default function CodeScanDetectionsTable({
  detections,
  inventoryId,
  aisleId,
  jobIdForPreview,
}: CodeScanDetectionsTableProps) {
  const { t } = useTranslation();

  if (!detections.length) return null;

  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {t('aisleCodeScans.tables.detectionsSection')}
      </Typography>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('aisleCodeScans.tables.type')}</TableCell>
              <TableCell>{t('aisleCodeScans.tables.value')}</TableCell>
              <TableCell>{t('aisleCodeScans.tables.status')}</TableCell>
              <TableCell>{t('aisleCodeScans.tables.sourceAsset')}</TableCell>
              <TableCell>{t('aisleCodeScans.summary.engine')}</TableCell>
              <TableCell>{t('aisleCodeScans.tables.date')}</TableCell>
              <TableCell align="right">{t('common.actions')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {detections.map((row) => (
              <TableRow key={row.id}>
                <TableCell>{formatCodeScanCodeType(t, row.code_type)}</TableCell>
                <TableCell sx={{ maxWidth: 240 }}>
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
                <TableCell>{formatCodeScanDetectionStatus(t, row.detection_status)}</TableCell>
                <TableCell sx={{ wordBreak: 'break-all' }}>{row.asset_id}</TableCell>
                <TableCell>{row.scanner_engine}</TableCell>
                <TableCell>{formatDate(row.created_at)}</TableCell>
                <TableCell align="right">
                  <CodeScanAssetPreviewButton
                    inventoryId={inventoryId}
                    aisleId={aisleId}
                    assetId={row.asset_id}
                    jobIdForPreview={jobIdForPreview}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
