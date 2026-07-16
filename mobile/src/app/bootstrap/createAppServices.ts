import { loadAppConfig, validateAppConfig } from '../config/env';
import { createLogger } from '../../core/logging';
import { getDatabase } from '../../database/database';
import { CaptureRepository } from '../../database/repositories/captureRepository';
import { AuthService } from '../../features/auth/authService';
import { AisleService } from '../../features/aisles/aisleService';
import { CaptureService } from '../../features/capture/captureService';
import { InventoryService } from '../../features/inventories/inventoryService';
import { createForegroundService } from '../../native/foregroundService';
import { ApiClient } from '../../services/api/apiClient';
import { secureTokenStorage } from '../../services/secureStorage/tokenStorage';

export interface AppServices {
  readonly configError: string | null;
  readonly auth: AuthService;
  readonly inventories: InventoryService;
  readonly aisles: AisleService;
  readonly capture: CaptureService;
  readonly api: ApiClient;
}

export async function createAppServices(onAuthExpired: () => void): Promise<AppServices> {
  const config = loadAppConfig();
  const configError = validateAppConfig(config);
  const logger = createLogger();
  const api = new ApiClient({
    config,
    tokenStorage: secureTokenStorage,
    logger,
    onAuthExpired,
  });
  const db = await getDatabase();
  const captureRepo = new CaptureRepository(db);
  const capture = new CaptureService(captureRepo, createForegroundService(), logger);
  return {
    configError,
    api,
    auth: new AuthService(api, secureTokenStorage, logger),
    inventories: new InventoryService(api),
    aisles: new AisleService(api),
    capture,
  };
}

