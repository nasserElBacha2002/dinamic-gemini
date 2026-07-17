export type ApiTimeoutKind = 'auth' | 'list' | 'multipart' | 'process' | 'polling' | 'default';

export interface ApiTimeoutsMs {
  readonly auth: number;
  readonly list: number;
  readonly multipart: number;
  readonly process: number;
  readonly polling: number;
  readonly default: number;
}

export const DEFAULT_API_TIMEOUTS_MS: ApiTimeoutsMs = {
  auth: 15_000,
  list: 30_000,
  multipart: 120_000,
  process: 30_000,
  polling: 20_000,
  default: 20_000,
};

export function timeoutMsFor(kind: ApiTimeoutKind, overrides?: Partial<ApiTimeoutsMs>): number {
  const merged = { ...DEFAULT_API_TIMEOUTS_MS, ...overrides };
  return merged[kind];
}
