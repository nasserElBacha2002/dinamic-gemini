import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import es from './locales/es/translation.json';
import en from './locales/en/translation.json';

const isDev = import.meta.env.DEV;
/** Vitest runs with MODE=test; keep English strings so unit tests stay stable. */
const defaultLng = import.meta.env.MODE === 'test' ? 'en' : 'es';

/** Await in Vitest setup so components render translated strings, not raw keys. */
export const i18nInit = i18n.use(initReactI18next).init({
  resources: {
    es: { translation: es },
    en: { translation: en },
  },
  lng: defaultLng,
  fallbackLng: defaultLng,
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
