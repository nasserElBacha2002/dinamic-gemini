import { useMemo } from 'react';
import { createPortal } from 'react-dom';
import BarcodeBlock from './BarcodeBlock';
import QrCodeBlock from './QrCodeBlock';
import {
  buildLabelQrText,
  clampLabelCopies,
  formatShortLabelDate,
  getLabelCodeMainValueClassName,
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

export interface PrintableLabelProps {
  data: Omit<LabelSheetData, 'copies'>;
  headerDate: string;
}

/** One full A4-landscape warehouse label (preview + print). */
export function PrintableLabel({ data, headerDate }: PrintableLabelProps) {
  const qrValue = useMemo(() => buildLabelQrText(data), [data]);
  const codeValueClassName = useMemo(() => getLabelCodeMainValueClassName(data.code), [data.code]);
  const normalizedCode = useMemo(() => data.code.trim(), [data.code]);

  return (
    <article
      className="label-card label-card--horizontal print-label"
      data-testid="label-card"
      data-print-label="true"
    >
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
      </section>

      <section className="label-main-content">
        <div className="label-primary-section">
          <div className="label-primary-row label-code-section">
            <span className="label-primary-label">CÓDIGO:</span>
            <span className={codeValueClassName}>{normalizedCode}</span>
          </div>

          <div className="label-primary-row label-quantity-section">
            <span className="label-primary-label">CANT. TOTAL:</span>
            <span className="label-primary-value label-quantity-value">{data.quantity.trim()}</span>
          </div>
        </div>

        <div className="label-codes-column">
          <QrCodeBlock value={qrValue} />
          <BarcodeBlock value={normalizedCode} />
        </div>
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

export type LabelPrintSheetMode = 'preview' | 'print';

export interface LabelPrintSheetProps {
  data: LabelSheetData;
  mode?: LabelPrintSheetMode;
  className?: string;
}

function LabelPrintSheetContent({ data }: { data: LabelSheetData }) {
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

  return (
    <div className="label-print-sheet">
      <div
        className={gridClass}
        data-testid="label-print-grid"
        data-layout={isSingleLabel ? 'single' : 'multi'}
        data-copies={copies}
        aria-label="label-print-grid"
      >
        {cards.map((key) => (
          <PrintableLabel key={key} data={cardData} headerDate={headerDate} />
        ))}
      </div>
    </div>
  );
}

/** Live preview of one or more printable labels (scaled on screen). */
export function LabelPreview({ data, className }: { data: LabelSheetData; className?: string }) {
  return (
    <div
      className={['label-preview-root', className ?? ''].filter(Boolean).join(' ')}
      data-testid="label-preview-sheet"
    >
      <div className="label-preview-viewport">
        <LabelPrintSheetContent data={data} />
      </div>
    </div>
  );
}

export default function LabelPrintSheet({ data, mode = 'print', className }: LabelPrintSheetProps) {
  if (mode === 'preview') {
    return <LabelPreview data={data} className={className} />;
  }

  return (
    <div
      className={['label-print-root', className ?? ''].filter(Boolean).join(' ')}
      data-testid="label-print-sheet-print"
    >
      <LabelPrintSheetContent data={data} />
    </div>
  );
}

export function LabelPrintPortal({ data }: { data: LabelSheetData }) {
  if (typeof document === 'undefined') return null;

  return createPortal(
    <div className="label-print-only-root" aria-hidden="true">
      <LabelPrintSheet data={data} mode="print" />
    </div>,
    document.body
  );
}
