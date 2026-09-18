/**
 * Jest / Node entry (ts-jest resolves this file; Metro Android uses requireNodeFs.native.ts).
 */

export type NodeFsSync = {
  mkdirSync: (path: string, options?: { recursive?: boolean }) => void;
  writeFileSync: (path: string, data: Uint8Array) => void;
  appendFileSync: (path: string, data: Uint8Array) => void;
  openSync: (path: string, flags: string) => number;
  readSync: (
    fd: number,
    buffer: Uint8Array,
    offset: number,
    length: number,
    position: number,
  ) => number;
  fstatSync: (fd: number) => { size: number };
  closeSync: (fd: number) => void;
};

/** Jest/Node only — Metro must not load this file on Android (see .native.ts). */
export function requireNodeFs(): NodeFsSync {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  return require('fs') as NodeFsSync;
}
