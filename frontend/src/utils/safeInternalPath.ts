/**
 * Allow only same-app relative paths for router navigation.
 * Rejects open-redirect / XSS vectors (protocol-relative, absolute URLs, javascript:, backslashes).
 */
export function safeInternalPath(candidate: unknown, fallback = '/'): string {
  if (typeof candidate !== 'string') return fallback;
  const raw = candidate.trim();
  if (!raw) return fallback;
  if (!raw.startsWith('/')) return fallback;
  if (raw.startsWith('//')) return fallback;
  if (raw.includes('\\')) return fallback;
  const lower = raw.toLowerCase();
  if (
    lower.startsWith('http:') ||
    lower.startsWith('https:') ||
    lower.startsWith('javascript:') ||
    lower.startsWith('data:')
  ) {
    return fallback;
  }
  // Block scheme-like prefixes after the first slash (e.g. /http://evil.com)
  if (/^\/[a-z][a-z0-9+.-]*:/i.test(raw)) return fallback;
  return raw;
}
