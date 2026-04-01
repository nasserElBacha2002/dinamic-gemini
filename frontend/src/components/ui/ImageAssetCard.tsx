import { ReactNode } from 'react';
import { Box, Tooltip, Typography } from '@mui/material';
import ImageIcon from '@mui/icons-material/Image';

export interface ImageAssetCardProps {
  title: string;
  subtitle?: string | ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
}

/**
 * Lightweight asset card for displaying image metadata and actions.
 * Used in Reference Images and Result Evidence flows.
 */
export default function ImageAssetCard({
  title,
  subtitle,
  actions,
  icon = <ImageIcon color="action" fontSize="small" />,
}: ImageAssetCardProps) {
  return (
    <Box
      sx={{
        px: 2,
        py: 1.5,
        display: 'grid',
        gap: 1.25,
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 2,
          minWidth: 0,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0, flex: 1 }}>
          {/* Lightweight Icon Placeholder (Instead of Eager Image) */}
          <Box
            sx={{
              width: 40,
              height: 40,
              borderRadius: 1,
              bgcolor: 'action.hover',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              border: '1px solid',
              borderColor: 'divider',
            }}
          >
            {icon}
          </Box>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Tooltip title={title} placement="top-start" disableFocusListener={!title}>
              <Typography
                variant="subtitle2"
                noWrap
                sx={{ 
                  fontWeight: 600, 
                  textOverflow: 'ellipsis', 
                  overflow: 'hidden',
                  lineHeight: 1.2
                }}
              >
                {title}
              </Typography>
            </Tooltip>
            {subtitle && (
              <Typography 
                variant="caption" 
                color="text.secondary" 
                noWrap 
                sx={{ display: 'block', mt: 0.5 }}
              >
                {subtitle}
              </Typography>
            )}
          </Box>
        </Box>
        
        {actions && (
          <Box sx={{ flexShrink: 0, display: 'flex', gap: 1, alignItems: 'center' }}>
            {actions}
          </Box>
        )}
      </Box>
    </Box>
  );
}
