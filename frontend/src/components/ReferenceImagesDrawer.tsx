import { Box, Button, Divider, Drawer, IconButton, Typography } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import type { InventoryVisualReference } from '../api/types';
import { formatDate } from '../utils/formatDate';
import { EmptyState, ErrorAlert, LoadingBlock } from './ui';

export interface ReferenceImagesDrawerProps {
  open: boolean;
  onClose: () => void;
  items: InventoryVisualReference[];
  isLoading: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
}

export default function ReferenceImagesDrawer({
  open,
  onClose,
  items,
  isLoading,
  errorMessage,
  onRetry,
}: ReferenceImagesDrawerProps) {
  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: { xs: '100%', sm: 'min(560px, 96vw)' },
          maxWidth: '100vw',
          display: 'flex',
          flexDirection: 'column',
          p: 0,
        },
      }}
    >
      <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, bgcolor: 'background.paper' }}>
        <Box
          sx={{
            flexShrink: 0,
            position: 'sticky',
            top: 0,
            zIndex: 1,
            bgcolor: 'background.paper',
            borderBottom: 1,
            borderColor: 'divider',
            px: 2.5,
            py: 1.5,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 1,
          }}
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.5 }}>
              Inventory
            </Typography>
            <Typography component="h2" variant="h6" sx={{ fontWeight: 600, lineHeight: 1.2, mt: 0.25 }}>
              Reference images
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
              Manage inventory-level references used as comparative context for future processing runs.
            </Typography>
          </Box>
          <IconButton aria-label="Close reference images drawer" onClick={onClose} size="small" edge="end">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        <Box sx={{ flex: 1, overflow: 'auto', minHeight: 0, px: 2.5, py: 2 }}>
          {isLoading ? <LoadingBlock /> : null}

          {!isLoading && errorMessage ? <ErrorAlert message={errorMessage} onRetry={onRetry} /> : null}

          {!isLoading && !errorMessage ? (
            <Box sx={{ display: 'grid', gap: 2 }}>
              {items.length === 0 ? (
                <EmptyState
                  title="No reference images uploaded yet"
                  message="Upload 1-3 images to help the analysis use expected pallet, label, or packaging references for this inventory."
                />
              ) : (
                <>
                  <Typography variant="body2" color="text.secondary">
                    Reference images are used for future processing runs only. Updating them does not modify existing
                    results automatically.
                  </Typography>
                  <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}>
                    {items.map((item, index) => (
                      <Box key={item.id}>
                        {index > 0 ? <Divider /> : null}
                        <Box
                          sx={{
                            px: 2,
                            py: 1.5,
                            display: 'grid',
                            gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 2fr) repeat(2, minmax(120px, 1fr))' },
                            gap: 1,
                            alignItems: 'center',
                          }}
                        >
                          <Box sx={{ minWidth: 0 }}>
                            <Typography variant="subtitle2" sx={{ wordBreak: 'break-word' }}>
                              {item.filename}
                            </Typography>
                          </Box>
                          <Typography variant="body2" color="text.secondary">
                            {item.mime_type}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            Uploaded {formatDate(item.created_at)}
                          </Typography>
                        </Box>
                      </Box>
                    ))}
                  </Box>
                </>
              )}

              <Box
                sx={{
                  border: '1px dashed',
                  borderColor: 'divider',
                  borderRadius: 2,
                  p: 2,
                  display: 'grid',
                  gap: 1,
                }}
              >
                <Typography variant="subtitle2">Management actions</Typography>
                <Typography variant="body2" color="text.secondary">
                  Upload, replace, preview, and delete actions will live in this panel as the next phase wires the
                  existing backend capabilities into the Inventory Detail UX.
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  <Button variant="outlined" size="small" disabled>
                    Upload references
                  </Button>
                  <Button variant="outlined" size="small" disabled>
                    Replace
                  </Button>
                  <Button variant="outlined" size="small" disabled>
                    Delete
                  </Button>
                </Box>
              </Box>
            </Box>
          ) : null}
        </Box>
      </Box>
    </Drawer>
  );
}
