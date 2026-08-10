import { useMemo, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import InventoryBarcode from './InventoryBarcode';
import InventoryQrCode from './InventoryQrCode';
import {
  normalizeInventoryCode,
  normalizeInventoryQuantity,
  tryBuildInventoryCodePayload,
} from './inventoryCodePayload';
import {
  clampLabelCopies,
  formatShortLabelDate,
  getLabelCodeMainValueClassName,
  LABEL_PRINT_TITLE,
  type LabelSheetData,
} from './labelPrintUtils';
import { parseProductLabelPayload } from './productLabelPayload';
import './labelPrint.css';

const DESC_OBS_MAX_CHARS = 240;
const DESC_OBS_MAX_LINES = 3;

function clampMultilinePrintValue(raw: string, maxChars = DESC_OBS_MAX_CHARS): string {
  const trimmed = raw.trim();
  if (!trimmed) return '';
  if (trimmed.length <= maxChars) return trimmed;
  return `${trimmed.slice(0, Math.max(0, maxChars - 1)).trimEnd()}…`;
}

function extractVisibleLabelId(scanPayload: string): string | null {
  const parsed = parseProductLabelPayload(scanPayload);
  if (parsed.status === 'VALID' && parsed.labelId) return parsed.labelId;
  return null;
}

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

export interface InventoryLabelProps {
  data: Omit<LabelSheetData, 'copies' | 'issuedPayloads'> & {
    /** Full scannable payload override (D1 preferred). */
    scanPayload?: string | null;
  };
  headerDate: string;
  onBarcodeValidityChange?: (valid: boolean) => void;
}

/**
 * One full A4-landscape warehouse label optimized for drone-readable QR + barcode.
 * Codes encode D1 when `scanPayload` is provided; otherwise legacy code|quantity.
 */
export function InventoryLabel({ data, headerDate, onBarcodeValidityChange }: InventoryLabelProps) {
  const codeValueClassName = useMemo(() => getLabelCodeMainValueClassName(data.code), [data.code]);
  const normalizedCode = useMemo(() => normalizeInventoryCode(data.code), [data.code]);
  const normalizedQuantity = useMemo(
    () => normalizeInventoryQuantity(data.quantity),
    [data.quantity]
  );

  const scanPayload = useMemo(() => {
    const issued = (data.scanPayload ?? '').trim();
    if (issued) return issued;
    return tryBuildInventoryCodePayload({ code: data.code, quantity: data.quantity }) ?? '';
  }, [data.scanPayload, data.code, data.quantity]);

  const visibleLabelId = useMemo(() => extractVisibleLabelId(scanPayload), [scanPayload]);
  const descriptionValue = useMemo(
    () => clampMultilinePrintValue(data.description ?? ''),
    [data.description]
  );
  const observationsValue = useMemo(
    () => clampMultilinePrintValue(data.observations ?? ''),
    [data.observations]
  );

  const hasAdditionalData =
    Boolean(data.lot?.trim()) ||
    Boolean(data.expiry?.trim()) ||
    Boolean(descriptionValue) ||
    Boolean(observationsValue);

  return (
    <article
      className={[
        'label-card',
        'label-card--horizontal',
        'print-label',
        'inventory-label',
        hasAdditionalData ? 'inventory-label--with-additional' : 'inventory-label--no-additional',
      ].join(' ')}
      data-testid="label-card"
      data-print-label="true"
      data-scan-payload={scanPayload || undefined}
      data-label-id={visibleLabelId ?? undefined}
      data-has-additional={hasAdditionalData ? 'true' : 'false'}
    >
      <header className="label-header">
        <div className="label-brand-mark" aria-hidden="true">
          DI
        </div>
        <div className="label-header-main">
          <div className="label-title">{LABEL_PRINT_TITLE}</div>
          <div className="label-header-meta">
            {visibleLabelId ? (
              <div className="label-id-band" data-testid="label-visible-id">
                <span className="label-id-band__label">ID ETIQUETA:</span>
                <span className="label-id-band__value">{visibleLabelId}</span>
              </div>
            ) : null}
            <LabelRow label="CLIENTE:" value={data.clientName} rowClassName="label-row--compact" />
            <LabelRow label="PROVEEDOR:" value={data.supplierName} rowClassName="label-row--compact" />
            {data.countedBy?.trim() ? (
              <LabelRow label="CONTADO POR:" value={data.countedBy} rowClassName="label-row--compact" />
            ) : null}
          </div>
        </div>
        <div className="label-date-code">{headerDate}</div>
      </header>

      <section className="label-main-content" data-testid="label-main-content">
        <div className="label-primary-column" data-testid="label-primary-column">
          <div className="label-primary-section">
            <div className="label-primary-row label-code-section">
              <span className="label-primary-label">CÓDIGO:</span>
              <span className={codeValueClassName}>{normalizedCode}</span>
            </div>

            <div className="label-primary-row label-quantity-section">
              <span className="label-primary-label">CANT. TOTAL:</span>
              <span className="label-primary-value label-quantity-value">{normalizedQuantity}</span>
            </div>
          </div>

          {hasAdditionalData ? (
            <section
              className="label-additional-data"
              data-testid="label-additional-data"
              aria-label="Datos adicionales"
            >
              {data.lot?.trim() ? (
                <div className="label-additional-item label-additional-item--lot label-primary-row">
                  <span className="label-primary-label">LOTE:</span>
                  <span className="label-primary-value label-field-main-value" data-testid="label-lot-value">
                    {data.lot.trim()}
                  </span>
                </div>
              ) : null}
              {data.expiry?.trim() ? (
                <div className="label-additional-item label-additional-item--expiry label-primary-row">
                  <span className="label-primary-label">VENCIMIENTO:</span>
                  <span
                    className="label-primary-value label-field-main-value"
                    data-testid="label-expiry-value"
                  >
                    {data.expiry.trim()}
                  </span>
                </div>
              ) : null}
              {descriptionValue ? (
                <div className="label-additional-item label-additional-item--description label-primary-row">
                  <span className="label-primary-label">DESCRIPCIÓN:</span>
                  <span
                    className="label-primary-value label-field-main-value label-field-main-value--multiline"
                    data-testid="label-description-value"
                    style={{ WebkitLineClamp: DESC_OBS_MAX_LINES } as CSSProperties}
                  >
                    {descriptionValue}
                  </span>
                </div>
              ) : null}
              {observationsValue ? (
                <div className="label-additional-item label-additional-item--observations label-primary-row">
                  <span className="label-primary-label">OBSERVACIONES:</span>
                  <span
                    className="label-primary-value label-field-main-value label-field-main-value--multiline"
                    data-testid="label-observations-value"
                    style={{ WebkitLineClamp: DESC_OBS_MAX_LINES } as CSSProperties}
                  >
                    {observationsValue}
                  </span>
                </div>
              ) : null}
            </section>
          ) : null}
        </div>

        <div className="label-qr-column">
          <InventoryQrCode value={scanPayload} sizePx={480} level="H" />
        </div>
      </section>

      <section className="label-barcode-section" data-testid="label-barcode-section">
        <InventoryBarcode
          value={scanPayload}
          displayCode={normalizedCode}
          displayQuantity={normalizedQuantity}
          onValidityChange={onBarcodeValidityChange}
          barHeightPx={180}
        />
      </section>
    </article>
  );
}

/** @deprecated Prefer InventoryLabel — same component. */
export const PrintableLabel = InventoryLabel;
export type PrintableLabelProps = InventoryLabelProps;

export type LabelPrintSheetMode = 'preview' | 'print';

export interface LabelPrintSheetProps {
  data: LabelSheetData;
  mode?: LabelPrintSheetMode;
  className?: string;
  onBarcodeValidityChange?: (valid: boolean) => void;
}

function LabelPrintSheetContent({
  data,
  onBarcodeValidityChange,
}: {
  data: LabelSheetData;
  onBarcodeValidityChange?: (valid: boolean) => void;
}) {
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

  const issued = data.issuedPayloads ?? null;

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
        {cards.map((key, index) => (
          <InventoryLabel
            key={key}
            data={{
              ...cardData,
              scanPayload: issued?.[index] ?? null,
            }}
            headerDate={headerDate}
            onBarcodeValidityChange={index === 0 ? onBarcodeValidityChange : undefined}
          />
        ))}
      </div>
    </div>
  );
}

/** Live preview of one or more printable labels (scaled on screen). */
export function LabelPreview({
  data,
  className,
  onBarcodeValidityChange,
}: {
  data: LabelSheetData;
  className?: string;
  onBarcodeValidityChange?: (valid: boolean) => void;
}) {
  return (
    <div
      className={['label-preview-root', className ?? ''].filter(Boolean).join(' ')}
      data-testid="label-preview-sheet"
    >
      <div className="label-preview-viewport">
        <LabelPrintSheetContent data={data} onBarcodeValidityChange={onBarcodeValidityChange} />
      </div>
    </div>
  );
}

export default function LabelPrintSheet({
  data,
  mode = 'print',
  className,
  onBarcodeValidityChange,
}: LabelPrintSheetProps) {
  if (mode === 'preview') {
    return (
      <LabelPreview data={data} className={className} onBarcodeValidityChange={onBarcodeValidityChange} />
    );
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
