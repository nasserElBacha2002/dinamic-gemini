import { useEffect, useMemo, useRef, useState } from 'react';
import JsBarcode from 'jsbarcode';

export interface BarcodeBlockProps {
  /** Raw internal code; trimmed before encoding. */
  value: string;
  /** Shown when value is empty (preview placeholder). */
  emptyMessage?: string;
  /** Shown when JsBarcode fails to encode. */
  errorMessage?: string;
}

const BARCODE_HEIGHT = 42;
const BARCODE_WIDTH = 1.5;

/**
 * CODE128 barcode from código interno.
 * Dimensions come from JsBarcode; CSS only constrains the wrapper (no bar distortion).
 */
export default function BarcodeBlock({
  value,
  emptyMessage = 'Completá el código interno para generar los códigos.',
  errorMessage = 'No se pudo generar el código de barras. Revisá el código interno ingresado.',
}: BarcodeBlockProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [renderError, setRenderError] = useState(false);

  const normalizedCode = useMemo(() => value.trim(), [value]);

  useEffect(() => {
    if (!normalizedCode) {
      setRenderError(false);
      return;
    }

    const svg = svgRef.current;
    if (!svg) return;

    try {
      JsBarcode(svg, normalizedCode, {
        format: 'CODE128',
        displayValue: false,
        height: BARCODE_HEIGHT,
        width: BARCODE_WIDTH,
        margin: 8,
        background: '#ffffff',
        lineColor: '#000000',
      });
      setRenderError(false);
    } catch {
      setRenderError(true);
      while (svg.firstChild) {
        svg.removeChild(svg.firstChild);
      }
    }
  }, [normalizedCode]);

  if (!normalizedCode) {
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

  return (
    <div
      className={['barcode-block', renderError ? 'barcode-block--error' : ''].filter(Boolean).join(' ')}
      data-testid="barcode-block"
      data-barcode-state={renderError ? 'error' : 'ready'}
      data-barcode-format="CODE128"
      data-barcode-value={normalizedCode}
      aria-label="Código de barras"
    >
      <div className={['barcode-wrapper', renderError ? 'barcode-wrapper--hidden' : ''].filter(Boolean).join(' ')}>
        <svg
          ref={svgRef}
          className="barcode-svg"
          role="img"
          aria-hidden={renderError}
          aria-label={renderError ? undefined : `Código de barras ${normalizedCode}`}
        />
      </div>
      {!renderError ? (
        <>
          <div className="barcode-text" data-testid="barcode-text">
            {normalizedCode}
          </div>
          <div className="barcode-caption">Código de barras</div>
        </>
      ) : (
        <p className="barcode-error-message" role="alert">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
