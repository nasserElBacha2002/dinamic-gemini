import { Dialog, DialogTitle, DialogContent, IconButton, Typography, Box } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import ImageViewer, { ImageViewerProps } from './ImageViewer';

export interface ImagePreviewDialogProps extends ImageViewerProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Shared image preview dialog shell for Phase 2.
 * Wraps the rich ImageViewer foundation.
 */
export default function ImagePreviewDialog({
  open,
  onClose,
  title,
  ...viewerProps
}: ImagePreviewDialogProps) {
  return (
    <Dialog 
      open={open} 
      onClose={onClose} 
      maxWidth="lg" 
      fullWidth
      PaperProps={{
        sx: { borderRadius: 2 }
      }}
    >
      <DialogTitle 
        sx={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between', 
          pr: 2, 
          py: 1.5,
          borderBottom: 1,
          borderColor: 'divider'
        }}
      >
        <Typography 
          variant="subtitle1" 
          noWrap 
          sx={{ flex: 1, fontWeight: 700, mr: 2 }}
        >
          {title || 'Image preview'}
        </Typography>
        <IconButton 
          aria-label="Close preview" 
          onClick={onClose} 
          size="small"
          sx={{ color: 'text.secondary' }}
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      
      <DialogContent 
        sx={{ 
          p: { xs: 1, sm: 2 }, 
          bgcolor: 'background.default',
          minHeight: 440
        }}
      >
        <Box sx={{ p: 1, height: '100%', display: 'flex', flexDirection: 'column' }}>
          <ImageViewer
            title={title}
            minHeight={400}
            maxHeight="68vh"
            {...viewerProps}
          />
        </Box>
      </DialogContent>
    </Dialog>
  );
}
