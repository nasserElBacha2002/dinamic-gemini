import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import es from './locales/es/translation.json';

const isDev = import.meta.env.DEV;

/**
 * Runtime locale: Spanish only (no selector, no `changeLanguage` to English in production UI).
 *
 * `locales/en/translation.json` is kept in the repo on purpose: reference, tooling, and future
 * bilingual support. It is not imported here so the bundle stays Spanish-only.
 */
export const i18nInit = i18n.use(initReactI18next).init({
  resources: {
    es: { translation: es },
  },
  lng: 'es',
  fallbackLng: 'es',
  supportedLngs: ['es'],
  load: 'languageOnly',
  nonExplicitSupportedLngs: false,
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
