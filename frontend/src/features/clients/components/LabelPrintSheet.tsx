import { useMemo } from 'react';
import { clampLabelCopies, type LabelSheetData } from './labelPrintUtils';
import './labelPrint.css';

function LabelLine({
  prefix,
  value,
  valueClassName = '',
}: {
  prefix: string;
  value: string;
  valueClassName?: string;
}) {
  const trimmed = value.trim();
  if (!trimmed) return null;

  const valueClasses = ['label-field-value', 'label-value', valueClassName].filter(Boolean).join(' ');

  return (
    <div className="label-line">
      <span className="label-field-label label-prefix">{prefix}</span>
      <span className={valueClasses}>{trimmed}</span>
    </div>
  );
}

function LabelCard({ data }: { data: Omit<LabelSheetData, 'copies'> }) {
  return (
    <article className="label-card" data-testid="label-card">
      <LabelLine prefix="CLIENTE:" value={data.clientName} />
      {data.supplierName ? <LabelLine prefix="PROVEEDOR:" value={data.supplierName} /> : null}
      <LabelLine prefix="COD:" value={data.code} valueClassName="label-code-value label-value--code" />
      <LabelLine prefix="CANTIDAD:" value={data.quantity} valueClassName="label-quantity-value" />
      <LabelLine prefix="LOTE:" value={data.lot ?? ''} />
      <LabelLine prefix="VTO:" value={data.expiry ?? ''} />
      <LabelLine prefix="DESCRIPCION:" value={data.description ?? ''} />
      <LabelLine prefix="OBS:" value={data.observations ?? ''} />
    </article>
  );
}

export interface LabelPrintSheetProps {
  data: LabelSheetData;
  /** When true, shows dashed border and scroll (screen preview inside dialog). */
  preview?: boolean;
  className?: string;
}

export default function LabelPrintSheet({ data, preview = false, className }: LabelPrintSheetProps) {
  const copies = clampLabelCopies(data.copies);
  const isSingleLabel = copies === 1;
  const cardData = useMemo(
    () => ({
      clientName: data.clientName,
      supplierName: data.supplierName,
      code: data.code,
      quantity: data.quantity,
      lot: data.lot,
      expiry: data.expiry,
      description: data.description,
      observations: data.observations,
    }),
    [
      data.clientName,
      data.supplierName,
      data.code,
      data.quantity,
      data.lot,
      data.expiry,
      data.description,
      data.observations,
    ]
  );

  const cards = useMemo(
    () => Array.from({ length: copies }, (_, index) => `label-copy-${index}`),
    [copies]
  );

  const rootClass = [
    'label-print-root',
    preview ? 'label-print-root--preview' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');

  const gridClass = `label-print-grid ${isSingleLabel ? 'single-label' : 'multi-label'}`;

  return (
    <div className={rootClass} data-testid="label-print-sheet">
      <div className="label-print-sheet">
        <div
          className={gridClass}
          data-testid="label-print-grid"
          data-layout={isSingleLabel ? 'single' : 'multi'}
          aria-label="label-print-grid"
        >
          {cards.map((key) => (
            <LabelCard key={key} data={cardData} />
          ))}
        </div>
      </div>
    </div>
  );
}
