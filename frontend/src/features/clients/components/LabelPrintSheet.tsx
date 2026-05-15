import { useMemo } from 'react';
import {
  clampLabelCopies,
  formatShortLabelDate,
  LABEL_PRINT_TITLE,
  type LabelSheetData,
} from './labelPrintUtils';
import './labelPrint.css';

function LabelRow({
  label,
  value,
  rowClassName = '',
  valueClassName = '',
}: {
  label: string;
  value: string | null | undefined;
  rowClassName?: string;
  valueClassName?: string;
}) {
  const trimmed = (value ?? '').trim();
  if (!trimmed) return null;

  const rowClass = ['label-row', rowClassName].filter(Boolean).join(' ');
  const valueClass = ['label-row-value', valueClassName].filter(Boolean).join(' ');

  return (
    <div className={rowClass}>
      <span className="label-row-label">{label}</span>
      <span className={valueClass}>{trimmed}</span>
    </div>
  );
}

function HorizontalLabelCard({ data, headerDate }: { data: Omit<LabelSheetData, 'copies'>; headerDate: string }) {
  const cardClass = ['label-card', 'label-card--horizontal'].join(' ');

  return (
    <article className={cardClass} data-testid="label-card">
      <header className="label-header">
        <div className="label-brand-mark" aria-hidden="true">
          DI
        </div>
        <div className="label-title">{LABEL_PRINT_TITLE}</div>
        <div className="label-date-code">{headerDate}</div>
      </header>

      <section className="label-meta">
        <LabelRow label="CLIENTE:" value={data.clientName} />
        <LabelRow label="PROVEEDOR:" value={data.supplierName} />
        <LabelRow label="CONTADO POR:" value={data.countedBy} />
        <LabelRow
          label="CÓDIGO INTERNO:"
          value={data.code}
          rowClassName="label-row--code"
          valueClassName="label-code-value"
        />
      </section>

      <div className="label-divider" role="presentation" />

      <section className="label-quantity-section" aria-label="Cantidad total">
        <div className="label-quantity-label">CANT. TOTAL</div>
        <div className="label-quantity-value">{data.quantity.trim()}</div>
      </section>

      <footer className="label-footer">
        {data.lot?.trim() ? <div>{`LOTE: ${data.lot.trim()}`}</div> : null}
        {data.expiry?.trim() ? <div>{`VTO: ${data.expiry.trim()}`}</div> : null}
        {data.description?.trim() ? <div>{data.description.trim()}</div> : null}
        {data.observations?.trim() ? <div>{`OBS: ${data.observations.trim()}`}</div> : null}
      </footer>
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
  const headerDate = formatShortLabelDate();

  const cardData = useMemo(
    () => ({
      clientName: data.clientName,
      supplierName: data.supplierName,
      countedBy: data.countedBy,
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
      data.countedBy,
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

  const gridClass = [
    'label-print-grid',
    'label-print-grid--horizontal',
    isSingleLabel ? 'single-label' : 'multi-label',
  ].join(' ');

  const printableSheet = (
    <div className={['label-print-root', className ?? ''].filter(Boolean).join(' ')}>
      <div className="label-print-sheet">
        <div
          className={gridClass}
          data-testid="label-print-grid"
          data-layout={isSingleLabel ? 'single' : 'multi'}
          data-copies={copies}
          aria-label="label-print-grid"
        >
          {cards.map((key) => (
            <HorizontalLabelCard key={key} data={cardData} headerDate={headerDate} />
          ))}
        </div>
      </div>
    </div>
  );

  if (!preview) {
    return (
      <div className="label-print-host" data-testid="label-print-sheet">
        {printableSheet}
      </div>
    );
  }

  return (
    <div className="label-preview-root" data-testid="label-print-sheet">
      <div className="label-preview-viewport">{printableSheet}</div>
    </div>
  );
}
