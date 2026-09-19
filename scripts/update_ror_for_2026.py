#!/usr/bin/env python3
"""
update_ror_for_2026.py
======================
Resuelve y añade las nuevas instituciones del Padrón SNII 2026 hacia
data/snii_ror_verified_matches_v2.json para alcanzar cobertura completa.
"""

import json
import os
import pandas as pd
import unicodedata
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SNII_EXCEL = DATA_DIR / "snii" / "Investigadores_vigentes_2026.xlsx"
ROR_JSON = DATA_DIR / "snii_ror_verified_matches_v2.json"
BACKUP_JSON = DATA_DIR / "snii_ror_verified_matches_v2.json.pre2026"

def norm(text):
    if not text: return ''
    text = unicodedata.normalize('NFKD', str(text))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]', '', text.upper())

OVERRIDES_2026 = {
    'INSTITUTO MEXICANO DE INVESTIGACION EN PESCA Y ACUACULTURA SUSTENTABLES (IMIPAS)': {
        'root_ror': 'https://ror.org/00z2b0n57',
        'root_openalex_id': 'https://openalex.org/I4210137324',
        'root_name': 'Instituto Mexicano de Investigación en Pesca y Acuacultura Sustentables',
        'confidence': 100,
        'reason': 'Decreto oficial: transformación de INAPESCA a IMIPAS.'
    },
    'GOBIERNO DE LA CIUDAD DE MEXICO': {
        'root_ror': 'https://ror.org/020wf9c35',
        'root_openalex_id': 'https://openalex.org/I4210148714',
        'root_name': 'Gobierno de la Ciudad de México',
        'confidence': 100,
        'reason': 'Gobierno de la CDMX / SEDESA'
    },
    'ASOCIACION PARA EVITAR LA CEGUERA EN MEXICO I.A.P.': {
        'root_ror': 'https://ror.org/03sgfhr82',
        'root_openalex_id': 'https://openalex.org/I4210135637',
        'root_name': 'Asociación para Evitar la Ceguera en México Hospital Dr. Luis Sánchez Bulnes',
        'confidence': 100,
        'reason': 'APEC Hospital de la Ceguera'
    },
    'FUNDACION CLINICA MEDICA SUR, A.C.': {
        'root_ror': 'https://ror.org/03881y913',
        'root_openalex_id': 'https://openalex.org/I4210147656',
        'root_name': 'Médica Sur',
        'confidence': 100,
        'reason': 'Fundación Clínica Médica Sur'
    },
    'UNIVERSIDAD AUTONOMA DE CIENCIAS Y ARTES DE CHIAPAS': {
        'root_ror': 'https://ror.org/01gxfn525',
        'root_openalex_id': 'https://openalex.org/I4210105143',
        'root_name': 'Universidad de Ciencias y Artes de Chiapas',
        'confidence': 100,
        'reason': 'UNICACH'
    },
    'UNIVERSIDAD TECNOLOGICA DE AGUASCALIENTES': {
        'root_ror': 'https://ror.org/0426xa281',
        'root_openalex_id': 'https://openalex.org/I4210145680',
        'root_name': 'Universidad Tecnológica de Aguascalientes',
        'confidence': 100,
        'reason': 'Match exacto'
    },
    'UNIVERSIDAD DE CELAYA (EDUCACION SUPERIOR DE CELAYA, A.C.)': {
        'root_ror': 'https://ror.org/022fepg35',
        'root_openalex_id': 'https://openalex.org/I4210137598',
        'root_name': 'Universidad de Celaya',
        'confidence': 100,
        'reason': 'Universidad de Celaya'
    },
    'UNIVERSIDAD POLITECNICA DE AMOZOC': {
        'root_ror': 'https://ror.org/05c8q5x68',
        'root_openalex_id': None,
        'root_name': 'Universidad Politécnica de Amozoc',
        'confidence': 95,
        'reason': 'Universidad Politécnica de Amozoc'
    },
    'UNIVERSIDAD TECNOLOGICA EL RETOÑO': {
        'root_ror': 'https://ror.org/02tq6z698',
        'root_openalex_id': 'https://openalex.org/I4210114098',
        'root_name': 'Universidad Tecnológica El Retoño',
        'confidence': 100,
        'reason': 'UTR Aguascalientes'
    },
    'UNIVERSIDAD INTERCULTURAL DE SAN LUIS POTOSI': {
        'root_ror': 'https://ror.org/037z8p496',
        'root_openalex_id': None,
        'root_name': 'Universidad Intercultural de San Luis Potosí',
        'confidence': 95,
        'reason': 'UICSLP'
    },
    'UNIVERSIDAD REGIOMONTANA, A.C.': {
        'root_ror': 'https://ror.org/03x187m91',
        'root_openalex_id': 'https://openalex.org/I4210118579',
        'root_name': 'Universidad Regiomontana',
        'confidence': 100,
        'reason': 'U-ERRE'
    },
    'UNIVERSIDAD TECNOLOGICA DE JALISCO': {
        'root_ror': 'https://ror.org/03w70v274',
        'root_openalex_id': 'https://openalex.org/I4210145690',
        'root_name': 'Universidad Tecnológica de Jalisco',
        'confidence': 100,
        'reason': 'UTJ'
    },
    'UNIVERSIDAD TECNOLOGICA DE SAN MIGUEL DE ALLENDE': {
        'root_ror': 'https://ror.org/04h854m72',
        'root_openalex_id': 'https://openalex.org/I4210148900',
        'root_name': 'Universidad Tecnológica de San Miguel de Allende',
        'confidence': 100,
        'reason': 'UTSMA'
    },
    'UNIVERSIDAD TECNOLOGICA GRAL. MARIANO ESCOBEDO': {
        'root_ror': 'https://ror.org/0388w8e09',
        'root_openalex_id': 'https://openalex.org/I4210145692',
        'root_name': 'Universidad Tecnológica General Mariano Escobedo',
        'confidence': 100,
        'reason': 'UTE Nuevo León'
    },
    'UNIVERSIDAD ANAHUAC XALAPA (CENTRO DE ESTUDIOS SUPERIORES DEL GOLFO, S.C.)': {
        'root_ror': 'https://ror.org/01n6h7t92',
        'root_openalex_id': 'https://openalex.org/I4210137590',
        'root_name': 'Universidad Anáhuac Xalapa',
        'confidence': 100,
        'reason': 'Universidad Anáhuac Campus Xalapa'
    }
}

def main():
    print("Mapeando instituciones 2026 hacia ROR...")
    df = pd.read_excel(SNII_EXCEL)
    inst_col = next((c for c in df.columns if 'INSTITUCION' in c or 'INSTITUCIÓN' in c), None)
    
    with open(ROR_JSON, "r", encoding="utf-8") as f:
        ror_data = json.load(f)

    # Crear backup si no existe
    if not BACKUP_JSON.exists():
        with open(BACKUP_JSON, "w", encoding="utf-8") as f:
            json.dump(ror_data, f, ensure_ascii=False, indent=2)

    unique_insts = df[inst_col].dropna().unique()
    added = 0
    for inst in unique_insts:
        raw_key = str(inst).strip()
        clean_key = norm(raw_key)

        # Check if already present
        if raw_key in ror_data:
            continue

        # Check override
        matched = False
        for ov_k, ov_v in OVERRIDES_2026.items():
            if norm(ov_k) == clean_key or raw_key.startswith(ov_k[:25]):
                ror_data[raw_key] = {
                    "root_info": ov_v,
                    "units": {}
                }
                added += 1
                matched = True
                print(f"  ✅ [Override] {raw_key} -> {ov_v['root_name']} ({ov_v['root_ror']})")
                break
        
        if not matched:
            # Fallback placeholder to maintain 100% dictionary coverage
            ror_data[raw_key] = {
                "root_info": {
                    "root_ror": None,
                    "root_openalex_id": None,
                    "root_name": raw_key,
                    "confidence": 10,
                    "reason": "Institución de reciente incorporación 2026 sin ROR asignado aún",
                    "raw_data": None
                },
                "units": {}
            }
            added += 1
            print(f"  ℹ️  [Placeholder] {raw_key}")

    with open(ROR_JSON, "w", encoding="utf-8") as f:
        json.dump(ror_data, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 Actualizadas {added} instituciones en {ROR_JSON.name}. Total instituciones en diccionario: {len(ror_data)}")

if __name__ == "__main__":
    main()
