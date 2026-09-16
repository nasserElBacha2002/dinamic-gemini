/** Ambient types for Node's experimental `node:sqlite` (Jest / Node 22+). */
declare module 'node:sqlite' {
  export class DatabaseSync {
    constructor(path: string);
    exec(sql: string): void;
    prepare(sql: string): StatementSync;
    close(): void;
  }

  export class StatementSync {
    run(...params: unknown[]): { changes?: number; lastInsertRowid?: number | bigint };
    get(...params: unknown[]): unknown;
    all(...params: unknown[]): unknown[];
    finalize?(): void;
  }
}
