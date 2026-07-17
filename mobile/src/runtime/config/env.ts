import Constants from 'expo-constants';

import { resolveAppConfig, type RawAppExtra } from './resolveAppConfig';

export type { AppConfig, AppEnvironment, RawAppExtra } from './resolveAppConfig';
export { resolveAppConfig, validateAppConfig } from './resolveAppConfig';

export function loadAppConfig() {
  const extra = Constants.expoConfig?.extra as RawAppExtra | undefined;
  return resolveAppConfig(extra);
}
