import { useMemo } from 'react';
import { QRCodeSVG } from 'qrcode.react';

export interface QrCodeBlockProps {
  /** Plain-text QR payload (same as current label QR). */
  value: string;
  caption?: string;
  sizePx?: number;
}

/** Square QR block for warehouse labels — black on white, quiet zone via includeMargin. */
export default function QrCodeBlock({
  value,
  caption = 'Código QR',
  sizePx = 96,
}: QrCodeBlockProps) {
  const hasValue = useMemo(() => value.trim().length > 0, [value]);

  if (!hasValue) {
    return (
      <div className="label-qr-section qr-code-block" aria-label="Código QR" data-testid="qr-code-block">
        <div className="qr-code qr-code--placeholder" aria-hidden="true" />
        <div className="label-qr-caption">{caption}</div>
      </div>
    );
  }

  return (
    <div className="label-qr-section qr-code-block" aria-label="Código QR" data-testid="qr-code-block">
      <QRCodeSVG
        value={value}
        size={sizePx}
        level="M"
        includeMargin
        bgColor="#ffffff"
        fgColor="#000000"
        className="label-qr-code qr-code"
      />
      <div className="label-qr-caption">{caption}</div>
    </div>
  );
}
