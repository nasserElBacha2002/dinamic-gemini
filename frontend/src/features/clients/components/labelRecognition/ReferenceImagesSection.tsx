import { Alert, Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { LabelKind } from '../../../../api/types';
import { SectionCard } from '../../../../components/ui';
import SupplierReferenceImagesModule from '../SupplierReferenceImagesModule';

interface Props {
  clientId: string;
  supplierId: string;
  supplierName: string;
  labelKind: LabelKind;
}

/**
 * Kind-scoped wrapper: title reflects ITEM vs POSITION.
 * Upload/list filtering uses label_kind when the API exposes it.
 */
export default function ReferenceImagesSection({
  clientId,
  supplierId,
  supplierName,
  labelKind,
}: Props) {
  const { t } = useTranslation();
  return (
    <SectionCard
      title={t('clients.extraction_profile.section_reference_images', { kind: labelKind })}
      variant="outlined"
    >
      <Box sx={{ display: 'grid', gap: 1.5 }}>
        <Alert severity="info">{t('clients.extraction_profile.reference_images_kind_hint')}</Alert>
        <Typography variant="body2" color="text.secondary">
          {t('clients.supplier_page.reference_section_policy')}
        </Typography>
        <SupplierReferenceImagesModule
          clientId={clientId}
          supplierId={supplierId}
          supplierName={supplierName}
          open
          presentation="inline"
          onClose={() => {}}
          labelKind={labelKind}
        />
      </Box>
    </SectionCard>
  );
}
