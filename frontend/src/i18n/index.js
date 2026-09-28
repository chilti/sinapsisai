/**
 * frontend/src/i18n/index.js
 * Módulo de Internacionalización Trilingüe
 */

import { es } from './es.js';
import { pt } from './pt.js';
import { en } from './en.js';

export const LANGUAGES = [
  { code: 'es', label: 'Español', flag: '🇲🇽' },
  { code: 'pt', label: 'Português', flag: '🇧🇷' },
  { code: 'en', label: 'English', flag: '🇺🇸' }
];

const dictionaries = { es, pt, en };

export function getDictionary(lang = 'es') {
  return dictionaries[lang] || dictionaries.es;
}

export default getDictionary;
