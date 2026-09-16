/**
 * Optional Node/Jest process access without requiring @types/node in the RN tsconfig.
 */

type NodeProcessLike = {
  readonly versions?: { readonly node?: string };
  readonly env?: Record<string, string | undefined>;
};

export function getNodeProcess(): NodeProcessLike | undefined {
  const g = globalThis as { process?: NodeProcessLike };
  return typeof g.process !== 'undefined' ? g.process : undefined;
}

export function isNodeRuntime(): boolean {
  return Boolean(getNodeProcess()?.versions?.node);
}

export function nodeTmpDir(): string {
  const env = getNodeProcess()?.env;
  return env?.TMPDIR || env?.TMP || env?.TEMP || '/tmp';
}
