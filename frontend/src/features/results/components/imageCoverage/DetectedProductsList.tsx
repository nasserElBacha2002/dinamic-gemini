/**
 * Lists physical products detected on a job image (D1 multi-label: 0..N).
 * `results` on the parent item remain legacy position summaries; this list is the
 * physical product truth for multi-product photos.
 */

import { Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { JobImageDetectedProduct } from '../../../../api/types';

export interface DetectedProductsListProps {
  products: JobImageDetectedProduct[];
}

export default function DetectedProductsList({ products }: DetectedProductsListProps) {
  const { t } = useTranslation();
  if (!products.length) {
    return null;
  }

  return (
    <Stack spacing={0.5} data-testid="job-image-detected-products" sx={{ mt: 1, width: '100%' }}>
      <Typography variant="caption" fontWeight={700} color="text.secondary">
        {t('results.imageCoverage.detectedProducts', {
          defaultValue: 'Productos',
          count: products.length,
        })}
      </Typography>
      {products.map((p) => {
        const qty = p.corrected_quantity ?? p.detected_quantity;
        const labelPart = p.label_id ? ` — ${p.label_id}` : '';
        return (
          <Typography
            key={p.product_record_id}
            variant="body2"
            data-testid="job-image-detected-product"
            sx={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
          >
            ✓ {p.sku} × {qty}
            {labelPart}
          </Typography>
        );
      })}
    </Stack>
  );
}
