import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { IconButton, Tooltip } from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';

export interface CopyCodeValueButtonProps {
  value: string;
}

export default function CopyCodeValueButton({ value }: CopyCodeValueButtonProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }, [value]);

  return (
    <Tooltip title={copied ? t('aisleCodeScans.actions.copied') : t('aisleCodeScans.actions.copyValue')}>
      <IconButton
        size="small"
        aria-label={t('aisleCodeScans.actions.copyValue')}
        onClick={() => void handleCopy()}
      >
        <ContentCopyIcon fontSize="inherit" />
      </IconButton>
    </Tooltip>
  );
}
