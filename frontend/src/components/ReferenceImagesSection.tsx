import { Box, Divider, Typography } from '@mui/material';
import type { InventoryVisualReference } from '../api/types';
import { formatDate } from '../utils/formatDate';
import { EmptyState, ErrorAlert, LoadingBlock, SectionCard } from './ui';

export interface ReferenceImagesSectionProps {
  items: InventoryVisualReference[];
  isLoading: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
}

export default function ReferenceImagesSection({
  items,
  isLoading,
  errorMessage,
  onRetry,
}: ReferenceImagesSectionProps) {
  return (
    <SectionCard
      title="Reference images"
      subtitle="Inventory-level references used as comparative context for future processing runs."
      variant="elevation"
      elevation={1}
    >
      {isLoading ? <LoadingBlock /> : null}

      {!isLoading && errorMessage ? <ErrorAlert message={errorMessage} onRetry={onRetry} /> : null}

      {!isLoading && !errorMessage && items.length === 0 ? (
        <EmptyState
          title="No reference images uploaded yet"
          message="Upload 1-3 images to help future processing runs use the expected pallet, label, or packaging references for this inventory."
        />
      ) : null}

      {!isLoading && !errorMessage && items.length > 0 ? (
        <Box sx={{ display: 'grid', gap: 1.5 }}>
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
        </Box>
      ) : null}
    </SectionCard>
  );
}
