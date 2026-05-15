/**
 * BaseDialog — shared shell for **simple** operational dialogs (Re diseño 3.3 §8.11: form dialogs, confirmations body).
 *
 * **Dialog family (Sprint 2.3):**
 * - **BaseDialog** — generic title + body + optional actions (compose this for feature forms).
 * - **ConfirmDialog** — composes `BaseDialog` with a fixed two-button confirmation layout (§14.5).
 * - **WizardModal** — separate: stepper + multi-step body (§8.10); does not use `BaseDialog` to avoid awkward nesting.
 *
 * **Actions:** Pass `actions` as `ReactNode`. A declarative `actions[]` API may be added later without removing this slot.
 */

import { useId, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import {
  Alert,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Typography,
  type DialogProps,
} from '@mui/material';
import type { SxProps, Theme } from '@mui/material/styles';

export interface BaseDialogProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  /**
   * Secondary line under the title (legacy). Prefer `description` for new code; both are supported:
   * rendered content is `description ?? subtitle`.
   */
  subtitle?: ReactNode;
  /** Optional description under the title; takes precedence over `subtitle` when both are set. */
  description?: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  maxWidth?: DialogProps['maxWidth'];
  fullWidth?: boolean;
  /** When true, backdrop / escape do not call `onClose` (e.g. while parent sets `loading`). */
  disableClose?: boolean;
  /** When true, show a header close control that calls `onClose` when not `disableClose`. */
  showCloseButton?: boolean;
  /**
   * Optional error region below description and above `children`.
   * Plain strings render as MUI `Alert` (severity error), matching `ConfirmDialog` inline errors.
   */
  error?: ReactNode;
  /** Pass `dividers` to `DialogContent` (e.g. long forms with visual separation). */
  contentDividers?: boolean;
  /** Applied to `DialogActions` when `actions` is set (e.g. confirm dialogs need extra padding). */
  actionsSx?: SxProps<Theme>;
}

function isNonEmptyDescription(value: ReactNode): boolean {
  if (value === null || value === undefined || value === false) return false;
  if (typeof value === 'string' || typeof value === 'number') return String(value).length > 0;
  return true;
}

export default function BaseDialog({
  open,
  onClose,
  title,
  subtitle,
  description,
  children,
  actions,
  maxWidth = 'sm',
  fullWidth = true,
  disableClose = false,
  showCloseButton = false,
  error,
  contentDividers = false,
  actionsSx,
}: BaseDialogProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const descriptionId = useId();

  const descriptionContent = description ?? subtitle;
  const hasDescription = isNonEmptyDescription(descriptionContent);

  const closeLabel = t('common.close');

  const titleText = (
    <Box component="span" id={titleId} sx={showCloseButton ? { flex: 1, minWidth: 0 } : undefined}>
      {title}
    </Box>
  );

  const titleBar = showCloseButton ? (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
      {titleText}
      <IconButton
        type="button"
        aria-label={closeLabel}
        onClick={onClose}
        disabled={disableClose}
        edge="end"
        size="small"
      >
        <CloseRoundedIcon fontSize="small" />
      </IconButton>
    </Box>
  ) : (
    titleText
  );

  const errorBlock =
    error !== null && error !== undefined && error !== false && error !== '' ? (
      <Box sx={{ mb: 2 }}>
        {typeof error === 'string' ? <Alert severity="error">{error}</Alert> : error}
      </Box>
    ) : null;

  return (
    <Dialog
      open={open}
      onClose={disableClose ? undefined : onClose}
      maxWidth={maxWidth}
      fullWidth={fullWidth}
      aria-labelledby={titleId}
      aria-describedby={hasDescription ? descriptionId : undefined}
    >
      <DialogTitle>{titleBar}</DialogTitle>
      <DialogContent dividers={contentDividers}>
        {hasDescription ? (
          <Box id={descriptionId} sx={{ mb: 2 }}>
            {typeof descriptionContent === 'string' || typeof descriptionContent === 'number' ? (
              <Typography variant="body2" color="text.secondary" component="p">
                {descriptionContent}
              </Typography>
            ) : (
              descriptionContent
            )}
          </Box>
        ) : null}
        {errorBlock}
        {children}
      </DialogContent>
      {actions ? <DialogActions sx={actionsSx}>{actions}</DialogActions> : null}
    </Dialog>
  );
}
