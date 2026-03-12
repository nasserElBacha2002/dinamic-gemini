/**
 * Execution log panel (v3.1.1) — operator-facing processing log.
 * Shows timestamp, level, stage, message; highlights errors.
 * Error prop is typed as unknown for safe handling of API/query error shapes.
 */

import {
  Box,
  Chip,
  CircularProgress,
  List,
  ListItem,
  ListItemText,
  Typography,
} from '@mui/material';
import type { ExecutionLogEvent } from '../api/types';

/** Derive a readable error message from unknown query/API error shape. */
export function getReadableErrorMessage(error: unknown): string {
  if (error == null) return 'Unknown error';
  if (typeof error === 'string') return error;
  if (error instanceof Error) return error.message;
  if (typeof error === 'object' && error !== null && 'message' in error) {
    const m = (error as { message?: unknown }).message;
    if (typeof m === 'string') return m;
  }
  try {
    return String(error);
  } catch {
    return 'Unknown error';
  }
}

function formatTs(ts: string): string {
  try {
    const d = new Date(ts);
    return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
  } catch {
    return ts;
  }
}

function levelColor(level: string): 'default' | 'warning' | 'error' | 'success' {
  switch (level.toLowerCase()) {
    case 'error':
      return 'error';
    case 'warning':
      return 'warning';
    case 'info':
    default:
      return 'default';
  }
}

function safePayloadString(payload: Record<string, unknown> | null | undefined): string {
  if (!payload || typeof payload !== 'object') return '';
  try {
    return JSON.stringify(payload);
  } catch {
    return '[unable to display payload]';
  }
}

interface ExecutionLogPanelProps {
  events: ExecutionLogEvent[];
  isLoading?: boolean;
  /** Query/API error; typed unknown so panel never crashes on unexpected shape. */
  error?: unknown;
  emptyMessage?: string;
}

export default function ExecutionLogPanel({
  events,
  isLoading,
  error,
  emptyMessage = 'No log entries yet.',
}: ExecutionLogPanelProps) {
  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
        <CircularProgress size={24} />
      </Box>
    );
  }
  if (error != null) {
    return (
      <Typography color="error" variant="body2" sx={{ p: 1 }}>
        Failed to load log: {getReadableErrorMessage(error)}
      </Typography>
    );
  }
  if (!events || events.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ p: 1 }}>
        {emptyMessage}
      </Typography>
    );
  }
  return (
    <List dense disablePadding sx={{ maxHeight: 360, overflow: 'auto' }}>
      {events.map((evt, i) => (
        <ListItem key={i} alignItems="flex-start" disableGutters sx={{ py: 0.25 }}>
          <ListItemText
            primary={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexWrap: 'wrap' }}>
                <Typography component="span" variant="caption" color="text.secondary">
                  {formatTs(evt.ts)}
                </Typography>
                <Chip
                  label={evt.stage}
                  size="small"
                  variant="outlined"
                  sx={{ fontFamily: 'monospace', fontSize: '0.7rem' }}
                />
                <Chip
                  label={evt.level}
                  size="small"
                  color={levelColor(evt.level)}
                  sx={{ fontSize: '0.65rem' }}
                />
              </Box>
            }
            secondary={
              <>
                <Typography variant="body2" component="span" sx={{ display: 'block', mt: 0.25 }}>
                  {evt.message}
                </Typography>
                {evt.payload && typeof evt.payload === 'object' && Object.keys(evt.payload).length > 0 && (
                  <Typography
                    variant="caption"
                    component="span"
                    sx={{ display: 'block', color: 'text.secondary', fontFamily: 'monospace' }}
                  >
                    {safePayloadString(evt.payload as Record<string, unknown>)}
                  </Typography>
                )}
              </>
            }
            primaryTypographyProps={{ component: 'div' }}
            secondaryTypographyProps={{ component: 'div' }}
            sx={{
              '& .MuiListItemText-secondary': {
                color: evt.level === 'error' ? 'error.main' : undefined,
              },
            }}
          />
        </ListItem>
      ))}
    </List>
  );
}
