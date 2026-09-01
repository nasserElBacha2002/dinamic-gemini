import { closeDatabaseForRelaunch } from '../../database/database';
import { resetSqliteWriteGate } from '../../database/sqliteWriteGate';

type Disposable = { dispose(): Promise<void> };

let bootstrapTail: Promise<Disposable | undefined> = Promise.resolve(undefined);

/**
 * Run app bootstrap one at a time. Expo reload can mount multiple App trees briefly;
 * without serialization each instance starts schedulers/queues and SQLite writers collide.
 */
export function runSerializedAppBootstrap<T extends Disposable>(
  factory: () => Promise<T>,
): Promise<T> {
  const task = bootstrapTail.catch(() => undefined).then(async (previous) => {
    if (previous) {
      // Never block the next bootstrap on slow async teardown (upload drains, etc.).
      void previous.dispose().catch(() => undefined);
    }
    await closeDatabaseForRelaunch();
    resetSqliteWriteGate();
    return factory();
  });
  bootstrapTail = task.then(
    (services) => services,
    () => undefined,
  );
  return task;
}

/** @internal test helper */
export function __resetAppBootstrapLifecycleForTests(): void {
  bootstrapTail = Promise.resolve(undefined);
}
