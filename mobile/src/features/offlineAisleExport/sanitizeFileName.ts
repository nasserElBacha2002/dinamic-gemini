/** Sanitize aisle label for filesystem — identity remains UUID in manifest. */

export function sanitizeAisleFileSlug(name: string): string {
  const base = (name || 'pasillo')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);
  return base || 'pasillo';
}

export function buildDinamicArchiveFileName(aisleName: string, aisleId: string): string {
  const slug = sanitizeAisleFileSlug(aisleName);
  const shortId = aisleId.replace(/-/g, '').slice(0, 8);
  return `${slug}_${shortId}.dinamic`;
}
