/**
 * Canonical package content fingerprint for ZIP reuse (Phase 4 corrections).
 */

import { sha256Hex } from '../localCsv/csvFormat';
import { LOCAL_PACKAGE_VERSION } from '../localCsv/localPackageContract';

export interface CanonicalPhotoDescriptor {
  readonly capturePhotoId: string;
  readonly sequenceNumber: number;
  readonly fileName: string;
  readonly mimeType: string;
  readonly sizeBytes: number;
  readonly sha256: string;
  readonly assetVariant: 'ORIGINAL' | 'PREPARED';
}

export interface PackageFingerprintInput {
  readonly freezeId: string | null;
  readonly freezeGeneration: number | null;
  readonly csvChecksumSha256: string;
  readonly photos: readonly CanonicalPhotoDescriptor[];
}

/** Deterministic sort: sequence then capturePhotoId. */
export function sortCanonicalPhotoDescriptors(
  photos: readonly CanonicalPhotoDescriptor[],
): CanonicalPhotoDescriptor[] {
  return [...photos].sort((a, b) => {
    if (a.sequenceNumber !== b.sequenceNumber) {
      return a.sequenceNumber - b.sequenceNumber;
    }
    return a.capturePhotoId.localeCompare(b.capturePhotoId);
  });
}

export function canonicalPhotoDescriptorLine(p: CanonicalPhotoDescriptor): string {
  return [
    p.capturePhotoId,
    String(p.sequenceNumber),
    p.fileName,
    p.mimeType,
    String(p.sizeBytes),
    p.sha256,
    p.assetVariant,
  ].join(':');
}

export async function buildPackageContentFingerprint(
  input: PackageFingerprintInput,
): Promise<string> {
  const sorted = sortCanonicalPhotoDescriptors(input.photos);
  const photoPart = sorted.map(canonicalPhotoDescriptorLine).join('|');
  return sha256Hex(
    [
      `pkg-v${LOCAL_PACKAGE_VERSION}`,
      input.freezeId ?? '',
      String(input.freezeGeneration ?? ''),
      input.csvChecksumSha256,
      photoPart,
    ].join('|'),
  );
}
