import * as SecureStore from 'expo-secure-store';

import type { AuthUserDto } from '../api/types';

export interface SessionUserStorage {
  getUser(): Promise<AuthUserDto | null>;
  saveUser(user: AuthUserDto): Promise<void>;
  clear(): Promise<void>;
}

const SESSION_USER_KEY = 'dinamic.auth.sessionUser';

export const secureSessionUserStorage: SessionUserStorage = {
  async getUser() {
    const raw = await SecureStore.getItemAsync(SESSION_USER_KEY);
    if (!raw) {
      return null;
    }
    try {
      const parsed = JSON.parse(raw) as AuthUserDto;
      if (!parsed?.id || !parsed.username) {
        return null;
      }
      return parsed;
    } catch {
      return null;
    }
  },
  async saveUser(user) {
    await SecureStore.setItemAsync(SESSION_USER_KEY, JSON.stringify(user));
  },
  async clear() {
    await SecureStore.deleteItemAsync(SESSION_USER_KEY);
  },
};
