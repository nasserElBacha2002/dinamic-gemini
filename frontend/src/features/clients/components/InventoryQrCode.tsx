import { useMemo } from 'react';
import { QRCodeSVG } from 'qrcode.react';

export interface InventoryQrCodeProps {
  /** Scannable payload (typically code|quantity). */
  value: string;
  caption?: string;
  /**
   * SVG module resolution (pixels). Physical print size is controlled by CSS in mm.
   * Use a high value so print/PDF stays sharp when CSS sizes the QR to ~80mm.
   */
  sizePx?: number;
  /** Error correction — H preferred for drone photos. */
  level?: 'L' | 'M' | 'Q' | 'H';
}

/** Large square QR for warehouse labels — black on white, quiet zone via includeMargin. */
export default function InventoryQrCode({
  value,
  caption = 'Código QR',
  sizePx = 420,
  level = 'H',
}: InventoryQrCodeProps) {
  const hasValue = useMemo(() => value.trim().length > 0, [value]);

  if (!hasValue) {
    return (
      <div
        className="label-qr-section qr-code-block inventory-qr-code"
        aria-label="Código QR"
        data-testid="qr-code-block"
        data-qr-state="empty"
      >
        <div className="qr-code qr-code--placeholder inventory-qr-svg" aria-hidden="true" />
        <div className="label-qr-caption">{caption}</div>
      </div>
    );
  }

  return (
    <div
      className="label-qr-section qr-code-block inventory-qr-code"
      aria-label="Código QR"
      data-testid="qr-code-block"
      data-qr-state="ready"
      data-qr-payload={value.trim()}
      data-qr-level={level}
    >
      <QRCodeSVG
        value={value.trim()}
        size={sizePx}
        level={level}
        includeMargin
        bgColor="#ffffff"
        fgColor="#000000"
        className="label-qr-code qr-code inventory-qr-svg"
      />
      <div className="label-qr-caption">{caption}</div>
    </div>
  );
}
