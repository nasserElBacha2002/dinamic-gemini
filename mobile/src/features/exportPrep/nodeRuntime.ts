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

/**
 * True only in real Node (Jest core). React Native may expose `process` but must
 * never take the Node fs ZIP sink path.
 */
export function isNodeRuntime(): boolean {
  if (!getNodeProcess()?.versions?.node) {
    return false;
  }
  const product = (globalThis as { navigator?: { product?: string } }).navigator?.product;
  if (product === 'ReactNative') {
    return false;
  }
  // Hermes / RN bridge present ⇒ device or emulator, not Jest node.
  if (typeof (globalThis as { nativeCallSyncHook?: unknown }).nativeCallSyncHook === 'function') {
    return false;
  }
  return true;
}

export function nodeTmpDir(): string {
  const env = getNodeProcess()?.env;
  return env?.TMPDIR || env?.TMP || env?.TEMP || '/tmp';
}
