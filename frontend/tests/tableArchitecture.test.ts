import { describe, expect, it } from 'vitest';

const sources = import.meta.glob('../src/**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const allowedMuiTableFiles = new Set(['../src/components/ui/DataTable.tsx']);

describe('table architecture guard', () => {
  it('keeps MUI table primitives inside DataTable only', () => {
    const offenders = Object.entries(sources).flatMap(([path, source]) => {
      if (allowedMuiTableFiles.has(path)) return [];
      const importsMuiTable = /import\s*{[^}]*\b(Table|TableContainer|TableHead|TableBody|TableRow|TableCell)\b[^}]*}\s*from ['"]@mui\/material['"]/s.test(
        source
      );
      return importsMuiTable ? [path.replace('../src/', '')] : [];
    });

    expect(offenders).toEqual([]);
  });

  it('does not use legacy renderMobileItem or mobileSecondaryFilters APIs', () => {
    const offenders = Object.entries(sources).flatMap(([path, source]) =>
      /renderMobileItem|mobileSecondaryFilters/.test(source) ? [path.replace('../src/', '')] : []
    );

    expect(offenders).toEqual([]);
  });
});
