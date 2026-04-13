import type { ReactNode } from 'react';
import { useCallback } from 'react';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import {
  Box,
  Card,
  CardContent,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useAppSnackbar } from '../ui/AppSnackbarProvider';

export function CopyIconButton({ text, ariaLabel }: { text: string; ariaLabel: string }) {
  const { showSnackbar } = useAppSnackbar();
  const { t } = useTranslation();
  const onCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      showSnackbar(t('admin_ai_config.copied'), 'success');
    } catch {
      showSnackbar(t('admin_ai_config.copy_failed'), 'error');
    }
  }, [showSnackbar, t, text]);

  return (
    <Tooltip title={ariaLabel}>
      <IconButton size="small" onClick={onCopy} aria-label={ariaLabel}>
        <ContentCopyIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
}

export function CopyableMonospaceBlock({
  text,
  'aria-label': ariaLabel,
  maxHeight = 420,
  copyLabel,
}: {
  text: string;
  'aria-label'?: string;
  maxHeight?: number;
  copyLabel: string;
}) {
  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="flex-end" sx={{ mb: 0.5 }}>
        <CopyIconButton text={text} ariaLabel={copyLabel} />
      </Stack>
      <Box
        component="pre"
        aria-label={ariaLabel}
        sx={{
          m: 0,
          p: 1.5,
          maxHeight,
          overflow: 'auto',
          bgcolor: 'action.hover',
          borderRadius: 1,
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
          fontSize: '0.8rem',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {text}
      </Box>
    </Box>
  );
}

export function KeyValueSummary({ rows }: { rows: { label: string; value: ReactNode }[] }) {
  return (
    <Table size="small">
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.label}>
            <TableCell sx={{ fontWeight: 600, width: 220, verticalAlign: 'top' }}>{row.label}</TableCell>
            <TableCell sx={{ verticalAlign: 'top' }}>{row.value}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function SelectableOutlineCard({
  selected,
  onClick,
  title,
  subtitle,
  footer,
}: {
  selected: boolean;
  onClick: () => void;
  title: string;
  subtitle?: string;
  footer?: ReactNode;
}) {
  return (
    <Card
      variant="outlined"
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      sx={{
        cursor: 'pointer',
        borderWidth: 2,
        borderColor: (theme) => (selected ? theme.palette.primary.main : theme.palette.divider),
        bgcolor: (theme) => (selected ? theme.palette.action.selected : undefined),
        transition: (theme) =>
          theme.transitions.create(['border-color', 'background-color'], { duration: theme.transitions.duration.shortest }),
      }}
      onClick={onClick}
    >
      <CardContent sx={{ '&:last-child': { pb: 2 } }}>
        <Typography variant="subtitle1" fontWeight={600}>
          {title}
        </Typography>
        {subtitle ? (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            {subtitle}
          </Typography>
        ) : null}
        {footer ? <Box sx={{ mt: 1 }}>{footer}</Box> : null}
      </CardContent>
    </Card>
  );
}

export function BulletList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        —
      </Typography>
    );
  }
  return (
    <List dense disablePadding component="ul" sx={{ listStyleType: 'disc', pl: 2 }}>
      {items.map((item, i) => (
        <ListItem key={i} disableGutters sx={{ display: 'list-item', py: 0.25 }}>
          <ListItemText primary={item} primaryTypographyProps={{ variant: 'body2' }} />
        </ListItem>
      ))}
    </List>
  );
}

export function EmptyInspectorState({ message }: { message: string }) {
  return (
    <Box sx={{ py: 4, textAlign: 'center' }}>
      <Typography color="text.secondary">{message}</Typography>
    </Box>
  );
}
