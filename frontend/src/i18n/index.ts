import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import es from './locales/es/translation.json';
import en from './locales/en/translation.json';

const isDev = import.meta.env.DEV;
const SUPPORTED_LANGS = new Set(['es', 'en']);

function resolveInitialLanguage(): 'es' | 'en' {
  // Product default is always Spanish for clean starts.
  const fallback: 'es' = 'es';
  if (import.meta.env.MODE === 'test') {
    // Keep unit tests deterministic with existing expectations.
    return 'en';
  }
  try {
    const persisted = window.localStorage.getItem('i18nextLng')?.trim().toLowerCase();
    if (persisted && SUPPORTED_LANGS.has(persisted)) {
      return persisted as 'es' | 'en';
    }
  } catch {
    // Ignore storage access errors (SSR/sandboxed contexts) and use Spanish default.
  }
  return fallback;
}

const initialLng = resolveInitialLanguage();

/** Await in Vitest setup so components render translated strings, not raw keys. */
export const i18nInit = i18n.use(initReactI18next).init({
  resources: {
    es: { translation: es },
    en: { translation: en },
  },
  lng: initialLng,
  fallbackLng: 'es',
  interpolation: { escapeValue: false },
  returnNull: false,
  ...(isDev
    ? {
        missingKeyHandler: (_lngs: readonly string[], _ns: string, key: string) => {
          console.warn(`[i18n] missing translation key: ${key}`);
        },
      }
    : {}),
});

export default i18n;
