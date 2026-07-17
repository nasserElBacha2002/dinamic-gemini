import { resolveAppConfig, validateAppConfig } from '../src/runtime/config/resolveAppConfig';

describe('resolveAppConfig', () => {
  const OLD_ENV = process.env;

  beforeEach(() => {
    process.env = { ...OLD_ENV };
    delete process.env.DINAMIC_API_BASE_URL;
    delete process.env.DINAMIC_API_KEY;
    delete process.env.DINAMIC_ENVIRONMENT;
  });

  afterAll(() => {
    process.env = OLD_ENV;
  });

  it('reads values from Expo extra (build-time injected config)', () => {
    const config = resolveAppConfig({
      apiBaseUrl: 'https://api.dinamic.example/',
      apiKey: 'secret',
      environment: 'production',
    });
    expect(config.apiBaseUrl).toBe('https://api.dinamic.example');
    expect(config.apiKey).toBe('secret');
    expect(config.environment).toBe('production');
    expect(config.isDevelopment).toBe(false);
    expect(validateAppConfig(config)).toBeNull();
  });

  it('trims trailing slashes and defaults environment to development', () => {
    const config = resolveAppConfig({ apiBaseUrl: 'http://192.168.1.50:8000///' });
    expect(config.apiBaseUrl).toBe('http://192.168.1.50:8000');
    expect(config.environment).toBe('development');
    expect(config.apiKey).toBeNull();
  });

  it('falls back to process.env only when extra is missing (Node/CI)', () => {
    process.env.DINAMIC_API_BASE_URL = 'http://10.0.2.2:8000';
    const config = resolveAppConfig(undefined);
    expect(config.apiBaseUrl).toBe('http://10.0.2.2:8000');
  });

  it('prefers Expo extra over process.env', () => {
    process.env.DINAMIC_API_BASE_URL = 'http://from-env:8000';
    const config = resolveAppConfig({ apiBaseUrl: 'http://from-extra:8000' });
    expect(config.apiBaseUrl).toBe('http://from-extra:8000');
  });

  it('reports a clear error when the base URL is missing', () => {
    const config = resolveAppConfig({});
    expect(validateAppConfig(config)).toBe('Falta configurar DINAMIC_API_BASE_URL.');
  });

  it('rejects non-http protocols', () => {
    const config = resolveAppConfig({ apiBaseUrl: 'ftp://api.dinamic.example' });
    expect(validateAppConfig(config)).toBe('DINAMIC_API_BASE_URL debe usar http o https.');
  });

  it('rejects cleartext HTTP in production', () => {
    const config = resolveAppConfig({
      apiBaseUrl: 'http://api.dinamic.example',
      environment: 'production',
    });
    expect(validateAppConfig(config)).toBe('En producción DINAMIC_API_BASE_URL debe usar HTTPS.');
  });

  it('allows HTTP in development', () => {
    const config = resolveAppConfig({
      apiBaseUrl: 'http://10.0.2.2:8000',
      environment: 'development',
    });
    expect(validateAppConfig(config)).toBeNull();
  });

  it('includes version metadata and feature flags', () => {
    const config = resolveAppConfig({
      apiBaseUrl: 'https://api.example.com',
      versionName: '0.3.0',
      versionCode: 30,
      gitSha: 'abc123',
      flags: { allowMobileDataUploads: false },
    });
    expect(config.versionName).toBe('0.3.0');
    expect(config.versionCode).toBe(30);
    expect(config.gitSha).toBe('abc123');
    expect(config.flags.allowMobileDataUploads).toBe(false);
  });
});
