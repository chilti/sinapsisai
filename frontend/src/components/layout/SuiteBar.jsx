/**
 * frontend/src/components/layout/SuiteBar.jsx
 * Envoltura del componente de la Franja del Ecosistema TlachIA
 */

import React from 'react';
import { TlachiaSuiteBar } from '@tlachia/ecosystem-bar';
import { useAppStore } from '../../store/useAppStore.js';

export function SuiteBar() {
  const language = useAppStore((state) => state.language);

  return (
    <TlachiaSuiteBar
      currentApp="sinapsisai"
      lang={language}
    />
  );
}

export default SuiteBar;
