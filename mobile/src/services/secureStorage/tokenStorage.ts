import * as SecureStore from 'expo-secure-store';

export interface AuthTokens {
  readonly accessToken: string;
  readonly refreshToken: string | null;
  readonly expiresIn: number | null;
  readonly refreshExpiresIn: number | null;
}

export interface TokenStorage {
  getAccessToken(): Promise<string | null>;
  getRefreshToken(): Promise<string | null>;
  saveTokens(tokens: AuthTokens): Promise<void>;
  clear(): Promise<void>;
}

const ACCESS_KEY = 'dinamic.auth.accessToken';
const REFRESH_KEY = 'dinamic.auth.refreshToken';

export const secureTokenStorage: TokenStorage = {
  async getAccessToken() {
    return SecureStore.getItemAsync(ACCESS_KEY);
  },
  async getRefreshToken() {
    return SecureStore.getItemAsync(REFRESH_KEY);
  },
  async saveTokens(tokens) {
    await SecureStore.setItemAsync(ACCESS_KEY, tokens.accessToken);
    if (tokens.refreshToken) {
      await SecureStore.setItemAsync(REFRESH_KEY, tokens.refreshToken);
    } else {
      await SecureStore.deleteItemAsync(REFRESH_KEY);
    }
  },
  async clear() {
    await SecureStore.deleteItemAsync(ACCESS_KEY);
    await SecureStore.deleteItemAsync(REFRESH_KEY);
  },
};

