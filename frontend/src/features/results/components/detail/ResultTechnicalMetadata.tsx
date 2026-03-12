/**
 * Epic 4 — Technical metadata section (collapsible, secondary).
 */

import { useState } from 'react';
import { Box, Typography, Button, Collapse } from '@mui/material';
import type { ResultDetail } from '../../types';

export interface ResultTechnicalMetadataProps {
  result: ResultDetail;
}

export default function ResultTechnicalMetadata({ result }: ResultTechnicalMetadataProps) {
  const [open, setOpen] = useState(false);
  const meta = result.technicalMetadata;
  if (!meta) return null;

  const hasAny =
    (meta.entityId != null && meta.entityId !== '') ||
    (meta.primaryEvidenceId != null && meta.primaryEvidenceId !== '') ||
    meta.rawStatus != null;

  if (!hasAny) return null;

  return (
    <Box sx={{ mt: 2 }}>
      <Button
        size="small"
        onClick={() => setOpen(!open)}
        sx={{ textTransform: 'none', color: 'text.secondary' }}
        aria-expanded={open}
      >
        {open ? 'Hide' : 'Show'} technical metadata
      </Button>
      <Collapse in={open}>
        <Box
          sx={{
            mt: 1,
            p: 1.5,
            bgcolor: 'grey.100',
            borderRadius: 1,
            fontFamily: 'monospace',
            fontSize: '0.8rem',
          }}
        >
          {meta.entityId != null && meta.entityId !== '' && (
            <Typography variant="caption" component="div" color="text.secondary">
              Entity ID: {meta.entityId}
            </Typography>
          )}
          {meta.primaryEvidenceId != null && meta.primaryEvidenceId !== '' && (
            <Typography variant="caption" component="div" color="text.secondary">
              Primary evidence ID: {meta.primaryEvidenceId}
            </Typography>
          )}
          {meta.rawStatus != null && (
            <Typography variant="caption" component="div" color="text.secondary">
              Raw status: {meta.rawStatus}
            </Typography>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}
