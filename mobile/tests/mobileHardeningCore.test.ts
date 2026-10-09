import { APP_ERRORS, userMessageForCode } from '../src/core/errorCatalog';
import { timeoutMsFor, DEFAULT_API_TIMEOUTS_MS } from '../src/core/apiTimeouts';
import { buildPhotoLifecycleAxes } from '../src/core/photoLifecycle';

describe('errorCatalog', () => {
  it('exposes productive codes with Spanish user messages', () => {
    expect(APP_ERRORS.AUTH_SESSION_EXPIRED.userMessage).toMatch(/sesión/i);
    expect(APP_ERRORS.NETWORK_OFFLINE.retryable).toBe(true);
    expect(userMessageForCode('JOB_FAILED')).toBe(APP_ERRORS.JOB_FAILED.userMessage);
    expect(userMessageForCode('not-a-code')).toBe(APP_ERRORS.UNKNOWN.userMessage);
  });
});

describe('apiTimeouts', () => {
  it('returns distinct timeouts per kind', () => {
    expect(timeoutMsFor('auth')).toBe(DEFAULT_API_TIMEOUTS_MS.auth);
    expect(timeoutMsFor('multipart')).toBeGreaterThan(timeoutMsFor('auth'));
    expect(timeoutMsFor('list', { list: 5_000 })).toBe(5_000);
  });
});

describe('photoLifecycle', () => {
  it('separates capture/stability/upload/remote axes', () => {
    const axes = buildPhotoLifecycleAxes('stable', 'uploaded');
    expect(axes.capture).toBe('stable');
    expect(axes.stability).toBe('stable');
    expect(axes.upload).toBe('uploaded');
    expect(axes.remote).toBe('uploaded');
  });

  it('marks excluded capture as skipped stability', () => {
    expect(buildPhotoLifecycleAxes('excluded', 'excluded').stability).toBe('skipped');
  });
});
