jest.mock('../src/database/database', () => ({
  closeDatabaseForRelaunch: jest.fn(async () => undefined),
}));

import {
  __resetAppBootstrapLifecycleForTests,
  runSerializedAppBootstrap,
} from '../src/runtime/bootstrap/appBootstrapLifecycle';

type TestService = { readonly id: string; dispose: () => Promise<void> };

describe('appBootstrapLifecycle', () => {
  beforeEach(() => {
    __resetAppBootstrapLifecycleForTests();
  });

  it('serializes bootstraps and disposes the previous instance', async () => {
    const order: string[] = [];
    const make = (id: string): TestService => ({
      id,
      dispose: jest.fn(async () => {
        order.push(`dispose:${id}`);
      }),
    });

    let firstDispose!: jest.Mock;
    const firstPromise = runSerializedAppBootstrap(async () => {
      order.push('build:first');
      await new Promise((r) => setTimeout(r, 30));
      const svc = make('first');
      firstDispose = svc.dispose as jest.Mock;
      return svc;
    });
    const secondPromise = runSerializedAppBootstrap(async () => {
      order.push('build:second');
      return make('second');
    });

    const [first, second] = await Promise.all([firstPromise, secondPromise]);
    expect(first.id).toBe('first');
    expect(second.id).toBe('second');
    expect(order.indexOf('build:first')).toBeLessThan(order.indexOf('build:second'));
    expect(firstDispose).toHaveBeenCalledTimes(1);
  });
});
