import { isSqliteBusyError, isSqliteMalformedError } from '../src/database/sqliteErrors';
import {
  __resetSqliteWriteGateForTests,
  runExclusiveDbWrite,
  runImmediateTransaction,
  withSqliteBusyRetry,
} from '../src/database/sqliteWriteGate';

describe('isSqliteMalformedError', () => {
  it('detects common SQLite corruption messages', () => {
    expect(isSqliteMalformedError(new Error('database disk image is malformed'))).toBe(true);
    expect(isSqliteMalformedError(new Error('SQLITE_CORRUPT: database disk image is malformed'))).toBe(
      true,
    );
    expect(isSqliteMalformedError('file is not a database')).toBe(true);
    expect(isSqliteMalformedError(new Error('UNIQUE constraint failed'))).toBe(false);
  });
});

describe('isSqliteBusyError', () => {
  it('detects locked / busy messages from expo-sqlite', () => {
    expect(isSqliteBusyError(new Error('Error code 5: database is locked'))).toBe(true);
    expect(
      isSqliteBusyError(
        new Error(
          "Call to function 'NativeStatement.finalizeAsync' has been rejected.\n→ Caused by: Error code \u0005: database is locked",
        ),
      ),
    ).toBe(true);
    expect(isSqliteBusyError(new Error('database disk image is malformed'))).toBe(false);
  });
});

describe('sqliteWriteGate', () => {
  beforeEach(() => {
    __resetSqliteWriteGateForTests();
  });

  it('serializes exclusive writers', async () => {
    const order: number[] = [];
    await Promise.all([
      runExclusiveDbWrite(async () => {
        order.push(1);
        await new Promise((r) => setTimeout(r, 30));
        order.push(2);
      }),
      runExclusiveDbWrite(async () => {
        order.push(3);
        order.push(4);
      }),
    ]);
    expect(order).toEqual([1, 2, 3, 4]);
  });

  it('retries SQLITE_BUSY then succeeds', async () => {
    let attempts = 0;
    const value = await withSqliteBusyRetry(
      async () => {
        attempts += 1;
        if (attempts < 3) {
          throw new Error('Error code 5: database is locked');
        }
        return 'ok';
      },
      { maxAttempts: 5, baseDelayMs: 1 },
    );
    expect(value).toBe('ok');
    expect(attempts).toBe(3);
  });

  it('gives up after max busy attempts', async () => {
    await expect(
      withSqliteBusyRetry(
        async () => {
          throw new Error('database is locked');
        },
        { maxAttempts: 2, baseDelayMs: 1 },
      ),
    ).rejects.toThrow(/database is locked/);
  });

  describe('runImmediateTransaction', () => {
    it('retries when BEGIN IMMEDIATE is busy', async () => {
      let beginAttempts = 0;
      const db = {
        execAsync: jest.fn(async (sql: string) => {
          if (sql.startsWith('BEGIN')) {
            beginAttempts += 1;
            if (beginAttempts < 2) {
              throw new Error('Error code 5: database is locked');
            }
          }
        }),
      };
      let workRuns = 0;
      const result = await runImmediateTransaction(
        db,
        async () => {
          workRuns += 1;
          return 'done';
        },
        { maxAttempts: 5, baseDelayMs: 1 },
      );
      expect(result).toBe('done');
      expect(beginAttempts).toBe(2);
      expect(workRuns).toBe(1);
      expect(db.execAsync).toHaveBeenCalledWith('COMMIT;');
    });

    it('rolls back and retries when busy after BEGIN succeeds', async () => {
      let workAttempts = 0;
      let commitAttempts = 0;
      const db = {
        execAsync: jest.fn(async (sql: string) => {
          if (sql.startsWith('BEGIN')) {
            return;
          }
          if (sql === 'ROLLBACK;') {
            return;
          }
          if (sql === 'COMMIT;') {
            commitAttempts += 1;
            if (commitAttempts < 2) {
              throw new Error('database is locked');
            }
          }
        }),
      };
      const result = await runImmediateTransaction(
        db,
        async () => {
          workAttempts += 1;
          return 'done';
        },
        { maxAttempts: 5, baseDelayMs: 1 },
      );
      expect(result).toBe('done');
      expect(workAttempts).toBe(2);
      expect(db.execAsync).toHaveBeenCalledWith('ROLLBACK;');
    });

    it('does not infinite-retry on non-busy errors', async () => {
      let workAttempts = 0;
      const db = {
        execAsync: jest.fn(async (sql: string) => {
          if (sql.startsWith('BEGIN')) {
            return;
          }
          if (sql === 'ROLLBACK;') {
            return;
          }
        }),
      };
      await expect(
        runImmediateTransaction(
          db,
          async () => {
            workAttempts += 1;
            throw new Error('UNIQUE constraint failed');
          },
          { maxAttempts: 5, baseDelayMs: 1 },
        ),
      ).rejects.toThrow(/UNIQUE constraint failed/);
      expect(workAttempts).toBe(1);
      expect(db.execAsync).toHaveBeenCalledWith('ROLLBACK;');
    });
  });
});
