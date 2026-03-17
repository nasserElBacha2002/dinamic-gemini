/**
 * Epic 3 — Result-centric table for the Results overview.
 * Columns: SKU, Qty, Traceability, Status, Confidence, Evidence, (Updated), Action.
 */

import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Button,
  Tooltip,
} from '@mui/material';
import type { ResultSummary } from '../types';
import { StatusChip, TraceabilityChip } from '../../../components/ui';
import { getReviewStatusLabel, getReviewStatusColor } from '../utils/reviewStatusDisplay';
import { visibleTraceabilityToApiStatus } from '../utils/traceabilityDisplay';
import { formatDate } from '../../../utils/formatDate';

export interface ResultsTableProps {
  results: ResultSummary[];
  onOpenDetail: (resultId: string) => void;
  /** Optional: show updated-at in a subtle way. */
  showUpdatedAt?: boolean;
}

function displaySku(r: ResultSummary): string {
  if (r.sku != null && r.sku.trim() !== '') return r.sku.trim();
  return '—';
}

function displayQty(r: ResultSummary): string {
  const value =
    r.resolvedQty != null && !Number.isNaN(r.resolvedQty)
      ? r.resolvedQty
      : r.detectedQty;

  if (value != null && !Number.isNaN(value) && value >= 0) {
    return String(value);
  }
  return '—';
}

function displayEvidence(r: ResultSummary): string {
  return r.hasEvidence ? 'Yes' : '—';
}

export default function ResultsTable({
  results,
  onOpenDetail,
  showUpdatedAt = false,
}: ResultsTableProps) {
  return (
    <TableContainer component={Paper}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell>SKU</TableCell>
            <TableCell align="right">Qty</TableCell>
            <TableCell>Traceability</TableCell>
            <TableCell>Status</TableCell>
            <TableCell align="right">Confidence</TableCell>
            <TableCell>Evidence</TableCell>
            {showUpdatedAt && (
              <TableCell sx={{ color: 'text.secondary' }}>Updated</TableCell>
            )}
            <TableCell align="right">Action</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {results.map((r) => (
            <TableRow key={r.id} hover>
              <TableCell sx={{ fontWeight: 500 }}>{displaySku(r)}</TableCell>
              <TableCell align="right">{displayQty(r)}</TableCell>
              <TableCell>
                <TraceabilityChip
                  status={visibleTraceabilityToApiStatus(r.traceabilityStatus)}
                  size="small"
                  variant="outlined"
                />
              </TableCell>
              <TableCell>
                <StatusChip
                  label={getReviewStatusLabel(r.reviewStatus)}
                  color={getReviewStatusColor(r.reviewStatus)}
                  size="small"
                  variant="outlined"
                />
              </TableCell>
              <TableCell align="right">
                {r.confidence != null
                  ? `${(r.confidence * 100).toFixed(0)}%`
                  : '—'}
              </TableCell>
              <TableCell sx={{ color: 'text.secondary', fontSize: '0.85rem' }}>
                {displayEvidence(r)}
              </TableCell>
              {showUpdatedAt && (
                <TableCell sx={{ color: 'text.secondary', fontSize: '0.85rem' }}>
                  {formatDate(r.updatedAt)}
                </TableCell>
              )}
              <TableCell align="right">
                <Tooltip title="Open result detail">
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => onOpenDetail(r.id)}
                  >
                    Review
                  </Button>
                </Tooltip>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
