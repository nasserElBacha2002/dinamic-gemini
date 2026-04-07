/**
 * Epic 4 / Sprint 4.3 — Review actions: confirm (primary), corrections (progressive), destructive (danger zone).
 * Revised in Phase 3 for a focused decision-oriented workflow.
 */

import { useState, useEffect, useRef } from 'react';
import { Box, Button, Stack, TextField, IconButton, Typography } from '@mui/material';
import EditIcon from '@mui/icons-material/EditOutlined';
import CloseIcon from '@mui/icons-material/Close';
import type { ResultDetail } from '../../types';

export interface ResultReviewActionsProps {
  result: ResultDetail;
  actionLoading: boolean;
  /** Non-operational run: hide mutating controls (benchmark / historical browse). */
  readOnly?: boolean;
  onConfirm: () => void;
  onUpdateQuantity: (quantity: number) => void;
  onUpdateSku: (sku: string) => void;
  onUpdatePositionCode: (positionCode: string) => void;
  onDeleteClick: () => void;
}

export default function ResultReviewActions({
  result,
  actionLoading,
  readOnly = false,
  onConfirm,
  onUpdateQuantity,
  onUpdateSku,
  onUpdatePositionCode,
  onDeleteClick,
}: ResultReviewActionsProps) {
  const [activeEditor, setActiveEditor] = useState<'qty' | 'sku' | 'pos' | null>(null);
  const qtyButtonRef = useRef<HTMLButtonElement>(null);
  const skuButtonRef = useRef<HTMLButtonElement>(null);
  const posButtonRef = useRef<HTMLButtonElement>(null);
  const lastActiveEditor = useRef<'qty' | 'sku' | 'pos' | null>(null);

  // Focus management: when editor closes, return focus to the trigger
  useEffect(() => {
    if (activeEditor !== null) {
      lastActiveEditor.current = activeEditor;
    } else {
      if (lastActiveEditor.current === 'qty') {
        qtyButtonRef.current?.focus();
      } else if (lastActiveEditor.current === 'sku') {
        skuButtonRef.current?.focus();
      } else if (lastActiveEditor.current === 'pos') {
        posButtonRef.current?.focus();
      }
      lastActiveEditor.current = null;
    }
  }, [activeEditor]);

  const isDeleted = result.reviewStatus === 'INVALID';

  // Collapse editor on success (if actionLoading flips back to false and we have a result change)
  // But we rely on the parent updating the 'result' prop which triggers a re-render.
  useEffect(() => {
    if (!actionLoading) {
      setActiveEditor(null);
    }
  }, [result.correctedQty, result.sku, result.positionCode]);

  if (isDeleted) return null;

  if (readOnly) {
    return (
      <Box sx={{ mt: 1 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          This result is from a non-operational run. Open the operational job to confirm or correct.
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ mt: 1 }}>
      {/* Primary Action — Only visible if not editing */}
      {!activeEditor && (
        <Box sx={{ mb: 4.5 }}>
          <Button
            variant="contained"
            color="primary"
            size="large"
            fullWidth
            onClick={onConfirm}
            disabled={actionLoading}
            sx={{ 
              py: 2, 
              fontWeight: 800, 
              borderRadius: 2.5, 
              fontSize: '1rem',
              boxShadow: '0 4px 12px rgba(var(--mui-palette-primary-mainChannel), 0.2)',
            }}
          >
            {actionLoading ? 'Confirming…' : 'Confirm result'}
          </Button>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.25, textAlign: 'center', opacity: 0.7, fontWeight: 500 }}>
            Accept current data as correct
          </Typography>
        </Box>
      )}

      {/* Progressive Corrections */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5, textTransform: 'uppercase', fontWeight: 700, letterSpacing: 1.2 }}>
          Correction tools
        </Typography>

        <Stack spacing={0.5}>
           {activeEditor === 'qty' ? (
             <QuantityEditor 
               initialValue={result.correctedQty ?? result.detectedQty ?? 0}
               onSave={onUpdateQuantity}
               onCancel={() => setActiveEditor(null)}
               loading={actionLoading}
             />
           ) : (
             <Button 
               ref={qtyButtonRef}
               variant="text" 
               fullWidth 
               onClick={() => setActiveEditor('qty')}
               disabled={actionLoading || activeEditor !== null}
               startIcon={<EditIcon sx={{ fontSize: 18 }} />}
               sx={{ 
                 py: 1, 
                 borderRadius: 1.5, 
                 textTransform: 'none', 
                 justifyContent: 'flex-start', 
                 px: 2,
                 color: 'text.secondary',
                 '&:hover': { bgcolor: 'action.hover', color: 'text.primary' }
               }}
             >
               Correct quantity
             </Button>
           )}

           {activeEditor === 'sku' ? (
             <SkuEditor 
               initialValue={result.sku ?? ''}
               onSave={onUpdateSku}
               onCancel={() => setActiveEditor(null)}
               loading={actionLoading}
             />
           ) : (
             <Button 
               ref={skuButtonRef}
               variant="text" 
               fullWidth 
               onClick={() => setActiveEditor('sku')}
               disabled={actionLoading || activeEditor !== null}
               startIcon={<EditIcon sx={{ fontSize: 18 }} />}
               sx={{ 
                 py: 1, 
                 borderRadius: 1.5, 
                 textTransform: 'none', 
                 justifyContent: 'flex-start', 
                 px: 2,
                 color: 'text.secondary',
                 '&:hover': { bgcolor: 'action.hover', color: 'text.primary' }
               }}
             >
               Correct SKU
             </Button>
           )}

           {activeEditor === 'pos' ? (
             <PositionCodeEditor 
               initialValue={result.positionCode ?? ''}
               onSave={onUpdatePositionCode}
               onCancel={() => setActiveEditor(null)}
               loading={actionLoading}
             />
           ) : (
             <Button 
               ref={posButtonRef}
               variant="text" 
               fullWidth 
               onClick={() => setActiveEditor('pos')}
               disabled={actionLoading || activeEditor !== null}
               startIcon={<EditIcon sx={{ fontSize: 18 }} />}
               sx={{ 
                 py: 1, 
                 borderRadius: 1.5, 
                 textTransform: 'none', 
                 justifyContent: 'flex-start', 
                 px: 2,
                 color: 'text.secondary',
                 '&:hover': { bgcolor: 'action.hover', color: 'text.primary' }
               }}
             >
               Correct Position Code
             </Button>
           )}
        </Stack>
      </Box>

      {/* Danger Zone */}
      <Box sx={{ mt: 8, pt: 3, borderTop: 1, borderColor: 'divider' }}>
        <Box 
           sx={{ 
             p: 2, 
             borderRadius: 2, 
             bgcolor: 'rgba(211, 47, 47, 0.02)', 
             border: '1px dashed', 
             borderColor: 'divider', // Quieter border
             opacity: 0.9
           }}
        >
          <Typography variant="caption" sx={{ fontWeight: 700, mb: 0.5, display: 'block', color: 'error.main', textTransform: 'uppercase', letterSpacing: 1 }}>
            Danger zone
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5, lineHeight: 1.4 }}>
            Only use this if the result is a false detection or contains data that shouldn't be reviewed. 
          </Typography>
          <Button
            variant="outlined"
            color="error"
            size="small"
            fullWidth
            onClick={onDeleteClick}
            disabled={actionLoading}
            sx={{ textTransform: 'none', fontWeight: 600, py: 0.75, borderRadius: 1.5 }}
          >
            Mark result invalid
          </Button>
        </Box>
      </Box>
    </Box>
  );
}

// Internal Editor Components

const SKU_MAX_LEN = 128;
const POS_CODE_MAX_LEN = 64;

function QuantityEditor({ 
  initialValue, 
  onSave, 
  onCancel, 
  loading 
}: { 
  initialValue: number; 
  onSave: (val: number) => void; 
  onCancel: () => void; 
  loading: boolean;
}) {
  const [val, setVal] = useState(String(initialValue));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const isValid = !isNaN(parseInt(val)) && parseInt(val) >= 0;

  return (
    <Box sx={{ bgcolor: 'action.hover', p: 2, borderRadius: 1.5, border: 1, borderColor: 'divider' }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5, fontWeight: 700 }}>
        New quantity
      </Typography>
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <TextField
          inputRef={inputRef}
          size="small"
          fullWidth
          value={val}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && isValid && !loading) {
              onSave(parseInt(val));
            } else if (e.key === 'Escape' && !loading) {
              onCancel();
            }
          }}
          error={!isValid && val !== ''}
          placeholder="0"
          type="text"
          inputMode="numeric"
          disabled={loading}
          autoComplete="off"
        />
        <Button 
          variant="contained" 
          size="small" 
          onClick={() => onSave(parseInt(val))}
          disabled={loading || !isValid}
          sx={{ minWidth: 64, height: 40 }}
        >
          {loading ? '...' : 'Save'}
        </Button>
        <IconButton size="small" onClick={onCancel} disabled={loading} sx={{ height: 40, width: 40 }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Stack>
    </Box>
  );
}

function SkuEditor({ 
  initialValue, 
  onSave, 
  onCancel, 
  loading 
}: { 
  initialValue: string; 
  onSave: (val: string) => void; 
  onCancel: () => void; 
  loading: boolean;
}) {
  const [val, setVal] = useState(initialValue);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const isValid = val.trim().length > 0 && val.length <= SKU_MAX_LEN;

  return (
    <Box sx={{ bgcolor: 'action.hover', p: 2, borderRadius: 1.5, border: 1, borderColor: 'divider' }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5, fontWeight: 700 }}>
        Corrected SKU
      </Typography>
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <TextField
          inputRef={inputRef}
          size="small"
          fullWidth
          value={val}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && isValid && !loading) {
              onSave(val.trim());
            } else if (e.key === 'Escape' && !loading) {
              onCancel();
            }
          }}
          error={!isValid && val.length > 0}
          placeholder="Update SKU..."
          disabled={loading}
          inputProps={{ maxLength: SKU_MAX_LEN }}
          autoComplete="off"
        />
        <Button 
          variant="contained" 
          size="small" 
          onClick={() => onSave(val.trim())}
          disabled={loading || !isValid}
          sx={{ minWidth: 64, height: 40 }}
        >
          {loading ? '...' : 'Save'}
        </Button>
        <IconButton size="small" onClick={onCancel} disabled={loading} sx={{ height: 40, width: 40 }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Stack>
    </Box>
  );
}

function PositionCodeEditor({ 
  initialValue, 
  onSave, 
  onCancel, 
  loading 
}: { 
  initialValue: string; 
  onSave: (val: string) => void; 
  onCancel: () => void; 
  loading: boolean;
}) {
  const [val, setVal] = useState(initialValue);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const isValid = val.trim().length > 0 && val.length <= POS_CODE_MAX_LEN;

  return (
    <Box sx={{ bgcolor: 'action.hover', p: 2, borderRadius: 1.5, border: 1, borderColor: 'divider' }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5, fontWeight: 700 }}>
        Corrected Position Code
      </Typography>
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <TextField
          inputRef={inputRef}
          size="small"
          fullWidth
          value={val}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setVal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && isValid && !loading) {
              onSave(val.trim());
            } else if (e.key === 'Escape' && !loading) {
              onCancel();
            }
          }}
          error={!isValid && val.length > 0}
          placeholder="Update Position Code..."
          disabled={loading}
          inputProps={{ maxLength: POS_CODE_MAX_LEN }}
          autoComplete="off"
        />
        <Button 
          variant="contained" 
          size="small" 
          onClick={() => onSave(val.trim())}
          disabled={loading || !isValid}
          sx={{ minWidth: 64, height: 40 }}
        >
          {loading ? '...' : 'Save'}
        </Button>
        <IconButton size="small" onClick={onCancel} disabled={loading} sx={{ height: 40, width: 40 }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Stack>
    </Box>
  );
}
