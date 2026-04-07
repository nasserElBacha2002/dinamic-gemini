/**
 * Sprint 4.3 — Evidence viewer: main image anchor, zoom, fullscreen, multi-image selection (label chips).
 * Refactored in Phase 2 Revised: Uses on-demand cards instead of invasive inline viewer.
 */

import { useMemo, useState } from 'react';
import { Box, Button, Typography, Divider } from '@mui/material';
import { ImageAssetCard, ImagePreviewDialog } from '../../../../components/ui';
import type { ResultDetail } from '../../types';
import { useEvidenceImageLoad } from '../../hooks/useEvidenceImageLoad';

export interface ResultEvidenceViewerProps {
  result: ResultDetail;
  inventoryId: string;
  aisleId: string;
}

interface EvidenceFrame {
  key: string;
  /** Operator-facing label; first row is not necessarily “full frame” — crops are preferred. */
  label: string;
  fileName: string | null;
}

function jobIdFromResult(result: ResultDetail): string | null {
  const entityId = result.technicalMetadata?.entityId;
  if (!entityId || typeof entityId !== 'string') return null;
  const idx = entityId.lastIndexOf('_');
  return idx > 0 ? entityId.slice(0, idx) : null;
}

function buildFrames(result: ResultDetail): EvidenceFrame[] {
  const seen = new Set<string>();
  const drafts: Array<{ key: string; fileName: string | null; label: string }> = [];

  const push = (
    assetId: string | null | undefined,
    fileName: string | null,
    label: string
  ) => {
    const id = assetId != null ? String(assetId).trim() : '';
    if (!id || seen.has(id)) return;
    seen.add(id);
    drafts.push({
      key: id,
      fileName,
      label,
    });
  };

  const primaryEvidenceId = result.technicalMetadata?.primaryEvidenceId?.trim() || null;
  const sortedEvidence = [...result.evidence].sort((a, b) => {
    if (primaryEvidenceId) {
      if (a.id === primaryEvidenceId) return -1;
      if (b.id === primaryEvidenceId) return 1;
    }
    if (a.role === 'PRIMARY' && b.role !== 'PRIMARY') return -1;
    if (b.role === 'PRIMARY' && a.role !== 'PRIMARY') return 1;
    return 0;
  });

  let supportingOrdinal = 0;
  sortedEvidence.forEach((ev) => {
    const isPrimary =
      (primaryEvidenceId != null && ev.id === primaryEvidenceId) ||
      (primaryEvidenceId == null && ev.role === 'PRIMARY');
    let label: string;
    if (isPrimary) {
      label = 'Primary evidence';
    } else if (sortedEvidence.length === 1) {
      label = 'Evidence';
    } else {
      supportingOrdinal += 1;
      label = `Supporting evidence ${supportingOrdinal}`;
    }
    push(ev.sourceImageId, ev.sourceFileName, label);
  });

  push(result.sourceImageId, result.sourceFileName, 'Full source photo');

  return drafts.map((d) => ({
    key: d.key,
    fileName: d.fileName,
    label: d.label,
  }));
}

export default function ResultEvidenceViewer({ result, inventoryId, aisleId }: ResultEvidenceViewerProps) {
  const frames = useMemo(() => buildFrames(result), [result]);
  const [previewTarget, setPreviewTarget] = useState<EvidenceFrame | null>(null);

  const jobId = jobIdFromResult(result);
  const imageSpec = previewTarget
    ? { inventoryId, aisleId, assetId: previewTarget.key, jobId }
    : null;
  
  // Image loading is only triggered when previewTarget is set (on-demand).
  const loadState = useEvidenceImageLoad(imageSpec);

  const hasRecordOnly = result.evidence.length > 0 && frames.length === 0;

  return (
    <Box>
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1.5 }}>
        Evidence
      </Typography>

      {frames.length === 0 && !hasRecordOnly && (
        <Box
          sx={{
            py: 4,
            px: 2,
            textAlign: 'center',
            bgcolor: 'action.hover',
            borderRadius: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Typography color="text.secondary">No image evidence available for this result.</Typography>
        </Box>
      )}

      {hasRecordOnly && (
        <Box sx={{ py: 3, px: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Evidence is recorded for this result, but no image is available to display here. Use{' '}
            <strong>Technical metadata</strong> below if you need internal reference fields.
          </Typography>
        </Box>
      )}

      {frames.length > 0 && (
        <>
          <Box 
            sx={{ 
              border: '1px solid', 
              borderColor: 'divider', 
              borderRadius: 2, 
              overflow: 'hidden',
              bgcolor: 'background.default' 
            }}
          >
            {frames.map((f, i) => (
              <Box key={f.key}>
                {i > 0 && <Divider />}
                <ImageAssetCard
                  title={f.fileName || f.label}
                  subtitle={f.fileName ? f.label : 'Result evidence'}
                  actions={
                    <Button 
                      variant="outlined" 
                      size="small" 
                      onClick={() => setPreviewTarget(f)}
                    >
                      Preview
                    </Button>
                  }
                />
              </Box>
            ))}
          </Box>

          <ImagePreviewDialog
            open={Boolean(previewTarget)}
            onClose={() => setPreviewTarget(null)}
            title={
              previewTarget?.fileName
                ? `${previewTarget.label} · ${previewTarget.fileName}`
                : previewTarget?.label ?? 'Evidence'
            }
            src={loadState.status === 'loaded' ? loadState.imageSrc : null}
            alt={previewTarget?.fileName ? `Evidence: ${previewTarget.fileName}` : 'Evidence image'}
            loading={loadState.status === 'loading'}
            error={loadState.status === 'error' ? loadState.message : null}
            caption={previewTarget?.fileName ?? previewTarget?.label}
          />
        </>
      )}
    </Box>
  );
}
