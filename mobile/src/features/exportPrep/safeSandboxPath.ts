/**
 * Path safety for sandbox deletions — never recurse on broad roots or escape document/cache.
 * Does not touch MediaStore / content:// URIs.
 */

export type SandboxRootKind = 'document' | 'cache' | 'unknown';

export interface SandboxRoots {
  readonly documentDirectory: string | null;
  readonly cacheDirectory: string | null;
}

export type PathSafetyFailure =
  | 'EMPTY'
  | 'MEDIASTORE'
  | 'CONTENT_URI'
  | 'TRAVERSAL'
  | 'OUTSIDE_SANDBOX'
  | 'IS_ROOT'
  | 'AMBIGUOUS_PREFIX'
  | 'DISALLOWED_ARTIFACT';

export class UnsafeSandboxPathError extends Error {
  constructor(
    readonly code: PathSafetyFailure,
    message: string,
  ) {
    super(message);
    this.name = 'UnsafeSandboxPathError';
  }
}

const ALLOWED_RELATIVE_PREFIXES = [
  'export-staging/',
  'aisle-exports/',
  'export-quarantine/',
  'dinamic-upload/',
] as const;

function stripFileScheme(uri: string): string {
  return uri.startsWith('file://') ? uri.slice('file://'.length) : uri;
}

/** Normalize for prefix checks (trailing slash on directories). */
export function normalizeSandboxUri(uri: string): string {
  const trimmed = uri.trim();
  if (!trimmed) return '';
  let path = stripFileScheme(trimmed);
  // Collapse duplicate slashes except leading //
  path = path.replace(/\/{2,}/g, '/');
  return path;
}

function hasTraversal(path: string): boolean {
  const parts = path.split('/');
  return parts.some((p) => p === '..');
}

function underRoot(path: string, root: string): boolean {
  const nPath = normalizeSandboxUri(path);
  const nRoot = normalizeSandboxUri(root).replace(/\/?$/, '/');
  if (!nRoot || nRoot === '/') return false;
  // Avoid ambiguous prefix: /foo must not match /foobar
  return nPath === nRoot.slice(0, -1) || nPath.startsWith(nRoot);
}

/**
 * Assert uri is under an allowed sandbox subtree and not a protected root.
 * Throws UnsafeSandboxPathError when unsafe.
 */
export function assertSafeSandboxDeleteTarget(
  uri: string,
  roots: SandboxRoots,
  options?: {
    readonly allowedPrefixes?: readonly string[];
    readonly allowSessionDirDelete?: boolean;
  },
): { readonly normalized: string; readonly rootKind: SandboxRootKind } {
  const raw = uri?.trim() ?? '';
  if (!raw) {
    throw new UnsafeSandboxPathError('EMPTY', 'Empty path');
  }
  if (/^content:/i.test(raw) || /mediastore/i.test(raw)) {
    throw new UnsafeSandboxPathError('MEDIASTORE', 'MediaStore / content URIs cannot be deleted');
  }
  if (raw.includes('..') || hasTraversal(stripFileScheme(raw))) {
    throw new UnsafeSandboxPathError('TRAVERSAL', 'Path traversal rejected');
  }

  const normalized = normalizeSandboxUri(raw);
  const doc = roots.documentDirectory ? normalizeSandboxUri(roots.documentDirectory) : null;
  const cache = roots.cacheDirectory ? normalizeSandboxUri(roots.cacheDirectory) : null;

  let rootKind: SandboxRootKind = 'unknown';
  let relative = '';
  if (doc && underRoot(normalized, doc)) {
    rootKind = 'document';
    relative = normalized.slice(normalizeSandboxUri(doc).replace(/\/?$/, '/').length);
  } else if (cache && underRoot(normalized, cache)) {
    rootKind = 'cache';
    relative = normalized.slice(normalizeSandboxUri(cache).replace(/\/?$/, '/').length);
  } else {
    throw new UnsafeSandboxPathError('OUTSIDE_SANDBOX', 'Path outside app sandbox');
  }

  const prefixes = options?.allowedPrefixes ?? ALLOWED_RELATIVE_PREFIXES;
  const allowed = prefixes.some(
    (p) => relative === p.replace(/\/$/, '') || relative.startsWith(p),
  );
  if (!allowed) {
    throw new UnsafeSandboxPathError('DISALLOWED_ARTIFACT', 'Path not under allowed artifact roots');
  }

  // Never delete document/cache root or entire export-staging / aisle-exports roots.
  const protectedExact = new Set([
    '',
    'export-staging',
    'export-staging/',
    'aisle-exports',
    'aisle-exports/',
    'export-quarantine',
    'export-quarantine/',
    'dinamic-upload',
    'dinamic-upload/',
  ]);
  if (protectedExact.has(relative) || protectedExact.has(`${relative}/`)) {
    if (!(options?.allowSessionDirDelete && relative.startsWith('export-staging/'))) {
      throw new UnsafeSandboxPathError('IS_ROOT', 'Refusing to delete protected root');
    }
  }

  // Session staging dir delete is allowed when explicitly opted in.
  if (
    relative === 'export-staging' ||
    relative === 'aisle-exports' ||
    relative === 'export-quarantine'
  ) {
    throw new UnsafeSandboxPathError('IS_ROOT', 'Refusing to delete artifact root');
  }

  return { normalized, rootKind };
}

/** True when path is under export-staging for a specific session id. */
export function isSessionExportStagingPath(uri: string, sessionId: string, roots: SandboxRoots): boolean {
  try {
    const { normalized } = assertSafeSandboxDeleteTarget(uri, roots, {
      allowedPrefixes: ['export-staging/'],
      allowSessionDirDelete: true,
    });
    const safe = sessionId.replace(/[^a-zA-Z0-9_-]/g, '_');
    const doc = roots.documentDirectory ? normalizeSandboxUri(roots.documentDirectory) : '';
    const rel = normalized.slice(normalizeSandboxUri(doc).replace(/\/?$/, '/').length);
    return rel === `export-staging/${safe}` || rel.startsWith(`export-staging/${safe}/`);
  } catch {
    return false;
  }
}
