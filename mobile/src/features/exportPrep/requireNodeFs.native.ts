/**
 * React Native / Metro platform entry.
 * Must not reference Node builtins — Android resolves this file instead of requireNodeFs.ts.
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

/** Unreachable on device when isNodeRuntime() is false; never import Node fs here. */
export function requireNodeFs(): NodeFsSync {
  throw new Error('Node fs is not available in the React Native runtime');
}
