import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Box, Button, List, ListItem, ListItemText, Typography } from '@mui/material';

export interface CodeScanWarningsProps {
  warnings: string[];
}

export default function CodeScanWarnings({ warnings }: CodeScanWarningsProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  if (!warnings.length) return null;

  const preview = warnings.slice(0, 3);
  const hasMore = warnings.length > 3;

  return (
    <Alert severity="warning" sx={{ mb: 2 }}>
      <Typography variant="subtitle2" gutterBottom>
        {t('aisleCodeScans.warnings.title')}
      </Typography>
      <List dense disablePadding>
        {(expanded ? warnings : preview).map((w) => (
          <ListItem key={w} disablePadding sx={{ py: 0.25 }}>
            <ListItemText primary={w} primaryTypographyProps={{ variant: 'body2' }} />
          </ListItem>
        ))}
      </List>
      {hasMore ? (
        <Box sx={{ mt: 0.5 }}>
          <Button size="small" onClick={() => setExpanded((v) => !v)}>
            {expanded ? t('aisleCodeScans.warnings.hide') : t('aisleCodeScans.warnings.show')}
          </Button>
        </Box>
      ) : null}
    </Alert>
  );
}
