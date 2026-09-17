/**
 * Pure helpers for Mac coordinator + unit tests (no RN imports).
 */

export interface ManifestRow {
  readonly sequence: number;
  readonly filename: string;
  readonly type: 'position' | 'item' | string;
  readonly sourceTemplate: string;
  readonly width: number;
  readonly height: number;
  readonly sizeBytes: number;
  readonly sha256: string;
}

export function parseManifestCsv(text: string): ManifestRow[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length < 2) {
    throw Object.assign(new Error('MANIFEST_EMPTY'), { code: 'MANIFEST_EMPTY' });
  }
  const header = lines[0]!.toLowerCase();
  if (!header.includes('filename') || !header.includes('sha256')) {
    throw Object.assign(new Error('MANIFEST_HEADER_INVALID'), {
      code: 'MANIFEST_HEADER_INVALID',
    });
  }
  const rows: ManifestRow[] = [];
  const seenNames = new Set<string>();
  for (let i = 1; i < lines.length; i += 1) {
    const cols = splitCsvLine(lines[i]!);
    if (cols.length < 8) {
      throw Object.assign(new Error('MANIFEST_ROW_INVALID'), {
        code: 'MANIFEST_ROW_INVALID',
        row: i,
      });
    }
    const filename = cols[1]!.trim();
    if (seenNames.has(filename)) {
      throw Object.assign(new Error('MANIFEST_DUPLICATE_FILENAME'), {
        code: 'MANIFEST_DUPLICATE_FILENAME',
        filename,
      });
    }
    seenNames.add(filename);
    rows.push({
      sequence: Number(cols[0]),
      filename,
      type: cols[2]!.trim().toLowerCase(),
      sourceTemplate: cols[3]!.trim(),
      width: Number(cols[4]),
      height: Number(cols[5]),
      sizeBytes: Number(cols[6]),
      sha256: cols[7]!.trim().toLowerCase(),
    });
  }
  return rows;
}

function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i]!;
    if (ch === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (ch === ',' && !inQuotes) {
      out.push(cur);
      cur = '';
      continue;
    }
    cur += ch;
  }
  out.push(cur);
  return out;
}

export function selectSmokeFixtures(rows: readonly ManifestRow[]): ManifestRow[] {
  const positions = rows.filter((r) => r.type === 'position');
  const items = rows.filter((r) => r.type === 'item');
  if (positions.length < 1 || items.length < 2) {
    throw Object.assign(new Error('SMOKE_FIXTURE_MIX_INVALID'), {
      code: 'SMOKE_FIXTURE_MIX_INVALID',
    });
  }
  return [positions[0]!, items[0]!, items[1]!];
}

export function selectPhotoSlice(rows: readonly ManifestRow[], photos: number): ManifestRow[] {
  if (photos < 1) {
    throw Object.assign(new Error('PHOTOS_COUNT_INVALID'), { code: 'PHOTOS_COUNT_INVALID' });
  }
  if (photos > rows.length) {
    throw Object.assign(new Error('PHOTOS_EXCEED_MANIFEST'), {
      code: 'PHOTOS_EXCEED_MANIFEST',
    });
  }
  if (photos === 3) {
    return selectSmokeFixtures(rows);
  }
  return rows.slice(0, photos);
}

export function median(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1]! + sorted[mid]!) / 2;
  }
  return sorted[mid]!;
}

export function percentileNearestRank(values: readonly number[], p: number): number | null {
  if (values.length === 0) return null;
  if (p <= 0) return Math.min(...values);
  if (p >= 100) return Math.max(...values);
  const sorted = [...values].sort((a, b) => a - b);
  const rank = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, Math.min(sorted.length - 1, rank))]!;
}

export function summarizeDurations(values: readonly number[]): {
  readonly min: number | null;
  readonly max: number | null;
  readonly median: number | null;
  readonly count: number;
} {
  if (values.length === 0) {
    return { min: null, max: null, median: null, count: 0 };
  }
  return {
    min: Math.min(...values),
    max: Math.max(...values),
    median: median(values),
    count: values.length,
  };
}

export type TerminalRunStatus = 'COMPLETED' | 'FAILED' | 'TIMEOUT' | 'RUNNING' | 'PENDING';

export function isTerminalStatus(status: string): status is 'COMPLETED' | 'FAILED' | 'TIMEOUT' {
  return status === 'COMPLETED' || status === 'FAILED' || status === 'TIMEOUT';
}
