import { useEffect, useRef, useState } from 'react';
import JsBarcode from 'jsbarcode';
import { barcodeModuleWidth } from './labelBarcodePayload';

export interface BarcodeBlockProps {
  /** Full CODE128 payload (already built by the label layer). */
  value: string;
  /** Human-readable código interno (not the technical payload). */
  displayCode: string;
  /** Human-readable cantidad. */
  displayQuantity: string;
  /** Shown when value is empty (preview placeholder). */
  emptyMessage?: string;
  /** Shown when JsBarcode fails or the barcode does not fit. */
  errorMessage?: string;
  /** Shown when payload is too long for a scannable print. */
  tooLongMessage?: string;
  /** Notify parent when barcode is ready to print (true) or not (false). */
  onValidityChange?: (valid: boolean) => void;
}

const BARCODE_HEIGHT = 54;
const BARCODE_MARGIN = 10;

/**
 * CODE128 renderer only — does not build business payloads.
 * Dimensions come from JsBarcode; CSS only constrains the wrapper (no bar distortion).
 */
export default function BarcodeBlock({
  value,
  displayCode,
  displayQuantity,
  emptyMessage = 'Completá el código interno para generar los códigos.',
  errorMessage = 'No se pudo generar el código de barras. Revisá el código interno ingresado.',
  tooLongMessage = 'El código y la cantidad generan un código de barras demasiado largo.',
  onValidityChange,
}: BarcodeBlockProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [renderError, setRenderError] = useState(false);
  const [fitError, setFitError] = useState(false);

  const payload = value.trim();

  useEffect(() => {
    if (!payload) {
      setRenderError(false);
      setFitError(false);
      onValidityChange?.(false);
      return;
    }

    const svg = svgRef.current;
    if (!svg) {
      onValidityChange?.(false);
      return;
    }

    try {
      JsBarcode(svg, payload, {
        format: 'CODE128',
        displayValue: false,
        height: BARCODE_HEIGHT,
        width: barcodeModuleWidth(payload),
        margin: BARCODE_MARGIN,
        background: '#ffffff',
        lineColor: '#000000',
      });

      const wrapper = wrapperRef.current;
      const svgWidth = Number(svg.getAttribute('width') || 0);
      const containerWidth = wrapper?.clientWidth ?? 0;
      // In jsdom clientWidth is often 0 — only treat as overflow when measurable.
      const overflows = containerWidth > 0 && svgWidth > containerWidth + 0.5;
      if (overflows) {
        setRenderError(false);
        setFitError(true);
        while (svg.firstChild) {
          svg.removeChild(svg.firstChild);
        }
        onValidityChange?.(false);
        return;
      }

      setRenderError(false);
      setFitError(false);
      onValidityChange?.(true);
    } catch {
      setRenderError(true);
      setFitError(false);
      while (svg.firstChild) {
        svg.removeChild(svg.firstChild);
      }
      onValidityChange?.(false);
    }
  }, [payload, onValidityChange]);

  if (!payload) {
    return (
      <div
        className="barcode-block barcode-block--empty"
        data-testid="barcode-block"
        data-barcode-state="empty"
        aria-label="Código de barras"
      >
        <div className="barcode-wrapper barcode-wrapper--placeholder" aria-hidden="true" />
        <p className="barcode-empty-message">{emptyMessage}</p>
      </div>
    );
  }

  const showError = renderError || fitError;
  const message = fitError ? tooLongMessage : errorMessage;

  return (
    <div
      className={['barcode-block', showError ? 'barcode-block--error' : ''].filter(Boolean).join(' ')}
      data-testid="barcode-block"
      data-barcode-state={showError ? 'error' : 'ready'}
      data-barcode-format="CODE128"
      data-barcode-value={payload}
      data-barcode-payload={payload}
      aria-label="Código de barras"
    >
      <div
        ref={wrapperRef}
        className={['barcode-wrapper', showError ? 'barcode-wrapper--hidden' : ''].filter(Boolean).join(' ')}
      >
        <svg
          ref={svgRef}
          className="barcode-svg"
          role="img"
          aria-hidden={showError}
          aria-label={
            showError ? undefined : `Código de barras ${displayCode} cantidad ${displayQuantity}`
          }
        />
      </div>
      {!showError ? (
        <>
          <div className="barcode-human-readable" data-testid="barcode-text">
            <span data-testid="barcode-display-code">{displayCode}</span>
            <span className="barcode-human-separator" aria-hidden="true">
              ·
            </span>
            <span data-testid="barcode-display-quantity">{`CANT. ${displayQuantity}`}</span>
          </div>
          <div className="barcode-caption">Código de barras</div>
        </>
      ) : (
        <p className="barcode-error-message" role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
