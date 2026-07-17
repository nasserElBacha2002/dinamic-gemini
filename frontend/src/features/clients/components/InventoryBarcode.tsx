import { useEffect, useRef, useState } from 'react';
import JsBarcode from 'jsbarcode';
import {
  INVENTORY_BARCODE_DEFAULT_AVAILABLE_WIDTH_PX,
  INVENTORY_BARCODE_MAX_MODULE_WIDTH,
  INVENTORY_BARCODE_MIN_MODULE_WIDTH,
  INVENTORY_BARCODE_QUIET_MODULES,
  inventoryBarcodeModuleWidth,
} from './inventoryCodePayload';

export interface InventoryBarcodeProps {
  /** Full CODE128 payload (already built — typically code|quantity). */
  value: string;
  displayCode: string;
  displayQuantity: string;
  emptyMessage?: string;
  errorMessage?: string;
  tooLongMessage?: string;
  onValidityChange?: (valid: boolean) => void;
  /** JsBarcode bar height in px before viewBox scaling into the CSS mm box. */
  barHeightPx?: number;
}

const DEFAULT_BAR_HEIGHT = 180;

function readSvgLength(svg: SVGSVGElement, attr: 'width' | 'height'): number {
  const raw = svg.getAttribute(attr);
  if (!raw) return 0;
  const parsed = parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function clearSvg(svg: SVGSVGElement): void {
  while (svg.firstChild) {
    svg.removeChild(svg.firstChild);
  }
}

function applyFillViewBox(svg: SVGSVGElement): { width: number; height: number } | null {
  const generatedWidth = readSvgLength(svg, 'width');
  const generatedHeight = readSvgLength(svg, 'height');
  if (!(generatedWidth > 0 && generatedHeight > 0)) {
    return null;
  }
  svg.setAttribute('viewBox', `0 0 ${generatedWidth} ${generatedHeight}`);
  // Uniform scale into the CSS box — never stretch bars horizontally independently.
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  svg.removeAttribute('width');
  svg.removeAttribute('height');
  return { width: generatedWidth, height: generatedHeight };
}

/**
 * Large CODE128 renderer for drone-readable warehouse labels.
 * Does not build business payloads. CSS sets physical wrapper size in mm;
 * JsBarcode module width is chosen to fill that width, then SVG scales via viewBox.
 */
export default function InventoryBarcode({
  value,
  displayCode,
  displayQuantity,
  emptyMessage = 'Completá el código interno para generar los códigos.',
  errorMessage = 'No se pudo generar el código de barras. Revisá el código interno ingresado.',
  tooLongMessage = 'El código y la cantidad generan un código de barras demasiado largo.',
  onValidityChange,
  barHeightPx = DEFAULT_BAR_HEIGHT,
}: InventoryBarcodeProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [renderError, setRenderError] = useState(false);
  const [fitError, setFitError] = useState(false);
  const [moduleWidthUsed, setModuleWidthUsed] = useState<number | null>(null);

  const payload = value.trim();

  useEffect(() => {
    if (!payload) {
      setRenderError(false);
      setFitError(false);
      setModuleWidthUsed(null);
      onValidityChange?.(false);
      return;
    }

    const svg = svgRef.current;
    const wrapper = wrapperRef.current;
    if (!svg) {
      onValidityChange?.(false);
      return;
    }

    try {
      const measured = wrapper?.clientWidth ?? 0;
      const availableWidthPx =
        measured > 8 ? measured : INVENTORY_BARCODE_DEFAULT_AVAILABLE_WIDTH_PX;

      // Probe at module width 1 to learn JsBarcode's exact module count for this payload.
      JsBarcode(svg, payload, {
        format: 'CODE128',
        displayValue: false,
        height: barHeightPx,
        width: 1,
        margin: INVENTORY_BARCODE_QUIET_MODULES,
        background: '#ffffff',
        lineColor: '#000000',
      });
      const probeWidth = readSvgLength(svg, 'width');
      if (!(probeWidth > 0)) {
        throw new Error('barcode probe failed');
      }

      const probedModuleWidth = availableWidthPx / probeWidth;
      const estimated = inventoryBarcodeModuleWidth(payload, availableWidthPx);
      // Prefer probe (exact JsBarcode geometry); fall back to estimator.
      let moduleWidth = Number.isFinite(probedModuleWidth) ? probedModuleWidth : estimated;

      if (moduleWidth != null && Number.isFinite(moduleWidth)) {
        // Soft-cap extreme thickness for very short payloads; never go below drone minimum.
        moduleWidth = Math.min(moduleWidth, INVENTORY_BARCODE_MAX_MODULE_WIDTH);
      }

      if (
        moduleWidth == null ||
        !Number.isFinite(moduleWidth) ||
        moduleWidth < INVENTORY_BARCODE_MIN_MODULE_WIDTH
      ) {
        setRenderError(false);
        setFitError(true);
        setModuleWidthUsed(null);
        clearSvg(svg);
        onValidityChange?.(false);
        return;
      }

      JsBarcode(svg, payload, {
        format: 'CODE128',
        displayValue: false,
        height: barHeightPx,
        width: moduleWidth,
        margin: INVENTORY_BARCODE_QUIET_MODULES,
        background: '#ffffff',
        lineColor: '#000000',
      });

      const box = applyFillViewBox(svg);
      if (!box) {
        throw new Error('barcode viewBox failed');
      }

      setRenderError(false);
      setFitError(false);
      setModuleWidthUsed(moduleWidth);
      onValidityChange?.(true);
    } catch {
      setRenderError(true);
      setFitError(false);
      setModuleWidthUsed(null);
      clearSvg(svg);
      onValidityChange?.(false);
    }
  }, [payload, onValidityChange, barHeightPx]);

  if (!payload) {
    return (
      <div
        className="barcode-block barcode-block--empty inventory-barcode"
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
      className={['barcode-block', 'inventory-barcode', showError ? 'barcode-block--error' : '']
        .filter(Boolean)
        .join(' ')}
      data-testid="barcode-block"
      data-barcode-state={showError ? 'error' : 'ready'}
      data-barcode-format="CODE128"
      data-barcode-value={payload}
      data-barcode-payload={payload}
      data-barcode-module-width={moduleWidthUsed != null ? String(moduleWidthUsed) : undefined}
      aria-label="Código de barras"
    >
      <div
        ref={wrapperRef}
        className={['barcode-wrapper', showError ? 'barcode-wrapper--hidden' : '']
          .filter(Boolean)
          .join(' ')}
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
        <div className="barcode-human-readable" data-testid="barcode-text">
          <span data-testid="barcode-display-code">{displayCode}</span>
          <span className="barcode-human-separator" aria-hidden="true">
            |
          </span>
          <span data-testid="barcode-display-quantity">{`CANT. ${displayQuantity}`}</span>
        </div>
      ) : (
        <p className="barcode-error-message" role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
