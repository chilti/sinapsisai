#!/usr/bin/env bash
# audit_snii_diff_2025_2026.py
# ============================
# Auditoría cienciométrica y análisis de transiciones entre el Padrón SNII 2025 y el Padrón SNII 2026.
# Detecta:
# 1. Altas (nuevos ingresos al SNII en 2026)
# 2. Bajas (salidas del padrón SNII 2025)
# 3. Promociones y descensos de nivel
# 4. Movilidad institucional (migraciones entre instituciones)
# 5. Genera el subset de trabajo para resolución de identidad: data/snii_2026_nuevos_pendientes.json
# 6. Guarda el reporte consolidado en data/snii/snii_audit_diff_2025_2026.json

import os
import sys
import json
import argparse
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SNII_DIR = DATA_DIR / "snii"

parser = argparse.ArgumentParser(description="Auditoría cienciométrica SNII")
parser.add_argument("--excel", type=str, default=None, help="Ruta al nuevo archivo Excel del SNII")
parser.add_argument("--excel-previo", type=str, default=None, help="Ruta al Excel previo de referencia")
args = parser.parse_args()

PATH_2025 = Path(args.excel_previo) if args.excel_previo else (SNII_DIR / "Investigadores_vigentes_2025.xlsx")
PATH_2026 = Path(args.excel) if args.excel else (SNII_DIR / "Investigadores_vigentes_2026.xlsx")
MATCHES_PATH = DATA_DIR / "snii_llm_verified_matches.json"

OUTPUT_AUDIT = SNII_DIR / "snii_audit_diff_2025_2026.json"
OUTPUT_PENDING = DATA_DIR / "snii_2026_nuevos_pendientes.json"


def normalize_nivel(val):
    if val is None or pd.isna(val):
        return "UNKNOWN"
    s = str(val).strip().upper()
    mapping = {
        "CANDIDATO": "C", "C": "C",
        "1": "1", "I": "1", "NIVEL I": "1", "NIVEL 1": "1",
        "2": "2", "II": "2", "NIVEL II": "2", "NIVEL 2": "2",
        "3": "3", "III": "3", "NIVEL III": "3", "NIVEL 3": "3",
        "E": "E", "EMERITO": "E", "EMÉRITO": "E",
    }
    return mapping.get(s, s)


def clean_text(val):
    if val is None or pd.isna(val):
        return "SIN INFORMACION"
    s = str(val).strip().upper()
    return s if s not in ("", "NAN", "NO APLICA", "-") else "SIN INFORMACION"


def run_audit():
    print("=" * 70)
    print("🔬 AUDITORÍA CIENCIOMÉTRICA: TRANSICIÓN PADRÓN SNII 2025 -> 2026")
    print("=" * 70)

    # 1. Cargar 2025
    print(f"\n📂 Cargando Padrón 2025 desde {PATH_2025.name}...")
    xl25 = pd.ExcelFile(PATH_2025)
    # Buscar hoja 4T
    sheet_25 = next((s for s in xl25.sheet_names if "4T" in s.upper()), xl25.sheet_names[-1])
    print(f"   Hoja 2025 seleccionada: '{sheet_25}'")
    df25 = xl25.parse(sheet_25)
    df25.columns = [str(c).upper().strip() for c in df25.columns]
    
    cvu_col_25 = next(c for c in df25.columns if "CVU" in c)
    df25["cvu_clean"] = pd.to_numeric(df25[cvu_col_25], errors="coerce")
    df25 = df25.dropna(subset=["cvu_clean"]).copy()
    df25["cvu_int"] = df25["cvu_clean"].astype(int)
    
    name_col_25 = next((c for c in df25.columns if "NOMBRE" in c), "NOMBRE")
    nivel_col_25 = next((c for c in df25.columns if "NIVEL" in c), "NIVEL")
    inst_col_25 = next((c for c in df25.columns if "INSTITUCION" in c or "INSTITUCIÓN" in c), "INSTITUCION")
    area_col_25 = next((c for c in df25.columns if "AREA" in c or "ÁREA" in c), "AREA")
    
    df25["nivel_norm"] = df25[nivel_col_25].apply(normalize_nivel)
    df25["inst_clean"] = df25[inst_col_25].apply(clean_text)
    
    # 2. Cargar 2026
    print(f"\n📂 Cargando Padrón 2026 desde {PATH_2026.name}...")
    xl26 = pd.ExcelFile(PATH_2026)
    sheet_26 = xl26.sheet_names[0]
    print(f"   Hoja 2026 seleccionada: '{sheet_26}'")
    df26 = xl26.parse(sheet_26)
    df26.columns = [str(c).upper().strip() for c in df26.columns]
    
    cvu_col_26 = next(c for c in df26.columns if "CVU" in c)
    df26["cvu_clean"] = pd.to_numeric(df26[cvu_col_26], errors="coerce")
    df26 = df26.dropna(subset=["cvu_clean"]).copy()
    df26["cvu_int"] = df26["cvu_clean"].astype(int)
    
    name_col_26 = next((c for c in df26.columns if "NOMBRE" in c), "NOMBRE")
    nivel_col_26 = next((c for c in df26.columns if "NIVEL" in c), "NIVEL")
    inst_col_26 = next((c for c in df26.columns if "INSTITUCION" in c or "INSTITUCIÓN" in c), "INSTITUCION")
    dep_col_26 = next((c for c in df26.columns if "DEPENDENCIA" in c and "SUB" not in c), "DEPENDENCIA")
    sub_col_26 = next((c for c in df26.columns if "SUBDEPENDENCIA" in c), "SUBDEPENDENCIA")
    area_col_26 = next((c for c in df26.columns if "AREA" in c or "ÁREA" in c), "AREA")
    vig_fin_col_26 = next((c for c in df26.columns if "FIN DE VIGENCIA" in c or "FIN" in c), None)

    df26["nivel_norm"] = df26[nivel_col_26].apply(normalize_nivel)
    df26["inst_clean"] = df26[inst_col_26].apply(clean_text)

    set_25 = set(df25["cvu_int"])
    set_26 = set(df26["cvu_int"])

    print(f"\n📊 Total investigadores en Padrón 2025: {len(set_25):,}")
    print(f"📊 Total investigadores en Padrón 2026: {len(set_26):,}")

    # Altas y Bajas
    nuevos_cvus = set_26 - set_25
    bajas_cvus = set_25 - set_26
    continuantes_cvus = set_26.intersection(set_25)

    print(f"\n📈 Variación neta: +{len(set_26) - len(set_25):,} investigadores")
    print(f"   🟢 Nuevos ingresos (Altas 2026): {len(nuevos_cvus):,}")
    print(f"   🔴 Salidas del padrón (Bajas 2025): {len(bajas_cvus):,}")
    print(f"   🔄 Investigadores que continúan: {len(continuantes_cvus):,}")

    # Análisis de Altas
    df_nuevos = df26[df26["cvu_int"].isin(nuevos_cvus)]
    nuevos_por_nivel = df_nuevos["nivel_norm"].value_counts().to_dict()
    nuevos_por_inst = df_nuevos["inst_clean"].value_counts().head(10).to_dict()
    nuevos_por_area = df_nuevos[area_col_26].value_counts().to_dict()

    print("\n🟢 Distribución por Nivel en Nuevos Ingresos:")
    for niv, cnt in nuevos_por_nivel.items():
        print(f"   • Nivel {niv}: {cnt:>5,} ({cnt/len(df_nuevos)*100:.1f}%)")

    # Análisis de Bajas
    df_bajas = df25[df25["cvu_int"].isin(bajas_cvus)]
    bajas_por_nivel = df_bajas["nivel_norm"].value_counts().to_dict()
    print("\n🔴 Distribución por Nivel de Bajas (de 2025):")
    for niv, cnt in bajas_por_nivel.items():
        print(f"   • Nivel {niv}: {cnt:>5,} ({cnt/len(df_bajas)*100:.1f}%)")

    # Movilidad y Promociones en Continuantes
    map_25 = df25.set_index("cvu_int").to_dict(orient="index")
    map_26 = df26.set_index("cvu_int").to_dict(orient="index")

    order_niv = {"C": 0, "1": 1, "2": 2, "3": 3, "E": 4}
    promociones = []
    descensos = []
    sin_cambio_nivel = 0
    movilidad_inst = []

    for cvu in continuantes_cvus:
        r25 = map_25[cvu]
        r26 = map_26[cvu]
        n25 = r25["nivel_norm"]
        n26 = r26["nivel_norm"]
        
        # Comparación de nivel
        if n25 in order_niv and n26 in order_niv:
            if order_niv[n26] > order_niv[n25]:
                promociones.append({
                    "cvu": cvu,
                    "nombre": str(r26[name_col_26]),
                    "nivel_2025": n25,
                    "nivel_2026": n26,
                    "institucion": r26["inst_clean"]
                })
            elif order_niv[n26] < order_niv[n25]:
                descensos.append({
                    "cvu": cvu,
                    "nombre": str(r26[name_col_26]),
                    "nivel_2025": n25,
                    "nivel_2026": n26,
                    "institucion": r26["inst_clean"]
                })
            else:
                sin_cambio_nivel += 1
        else:
            sin_cambio_nivel += 1

        # Movilidad institucional
        i25 = r25["inst_clean"]
        i26 = r26["inst_clean"]
        if i25 != i26 and i25 != "SIN INFORMACION" and i26 != "SIN INFORMACION":
            movilidad_inst.append({
                "cvu": cvu,
                "nombre": str(r26[name_col_26]),
                "origen": i25,
                "destino": i26,
                "nivel": n26
            })

    print(f"\n🎖️  Dinámica de Niveles (sobre {len(continuantes_cvus):,} continuantes):")
    print(f"   ⬆️  Promociones de nivel: {len(promociones):,} ({len(promociones)/len(continuantes_cvus)*100:.1f}%)")
    print(f"   ⬇️  Descensos de nivel:   {len(descensos):,} ({len(descensos)/len(continuantes_cvus)*100:.1f}%)")
    print(f"   ⏹️  Mismo nivel:           {sin_cambio_nivel:,} ({sin_cambio_nivel/len(continuantes_cvus)*100:.1f}%)")

    # Principales transiciones de promociones
    trans_counts = {}
    for p in promociones:
        pair = f"{p['nivel_2025']} -> {p['nivel_2026']}"
        trans_counts[pair] = trans_counts.get(pair, 0) + 1
    print("   Principales ascensos:")
    for pair, cnt in sorted(trans_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"     • {pair}: {cnt:,}")

    print(f"\n🚚 Movilidad Institucional:")
    print(f"   • Investigadores que cambiaron de institución: {len(movilidad_inst):,}")

    # 3. Traslape con Identidades Previamente Resueltas
    print(f"\n🔍 Verificando identificadores persistentes contra {MATCHES_PATH.name}...")
    verified_cvus = set()
    if MATCHES_PATH.exists():
        with open(MATCHES_PATH, "r", encoding="utf-8") as f:
            v_data = json.load(f)
        for r in v_data:
            c = r.get("cvu") or r.get("snii_cvu")
            if c:
                try:
                    verified_cvus.add(int(c))
                except:
                    pass

    ya_resueltos_2026 = set_26.intersection(verified_cvus)
    pendientes_resolucion = set_26 - verified_cvus

    print(f"   ✅ CVUs 2026 con ORCID/OpenAlex ya verificado: {len(ya_resueltos_2026):,} ({len(ya_resueltos_2026)/len(set_26)*100:.1f}%)")
    print(f"   ⏳ CVUs 2026 pendientes de resolver identidad: {len(pendientes_resolucion):,} ({len(pendientes_resolucion)/len(set_26)*100:.1f}%)")

    # 4. Generar subset de trabajo para Fase 4 (Resolución de Identidad)
    df_pendientes = df26[df26["cvu_int"].isin(pendientes_resolucion)]
    records_pendientes = []
    for _, row in df_pendientes.iterrows():
        records_pendientes.append({
            "cvu": int(row["cvu_int"]),
            "nombre": str(row[name_col_26]).strip(),
            "nivel": row["nivel_norm"],
            "area": str(row[area_col_26]).strip() if pd.notna(row[area_col_26]) else "SIN AREA",
            "institucion": row["inst_clean"],
            "dependencia": clean_text(row[dep_col_26]) if dep_col_26 else "SIN INFORMACION",
            "subdependencia": clean_text(row[sub_col_26]) if sub_col_26 else "SIN INFORMACION",
            "vigencia_fin": str(row[vig_fin_col_26]) if vig_fin_col_26 and pd.notna(row[vig_fin_col_26]) else None
        })

    with open(OUTPUT_PENDING, "w", encoding="utf-8") as f:
        json.dump(records_pendientes, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Guardado subset de {len(records_pendientes):,} investigadores pendientes en: {OUTPUT_PENDING}")

    # 5. Consolidar informe JSON de auditoría
    audit_data = {
        "fecha_corte": "Junio 2026 (2T 2026)",
        "total_2025": len(set_25),
        "total_2026": len(set_26),
        "variacion_neta": len(set_26) - len(set_25),
        "altas_totales": len(nuevos_cvus),
        "bajas_totales": len(bajas_cvus),
        "continuantes_totales": len(continuantes_cvus),
        "promociones_totales": len(promociones),
        "descensos_totales": len(descensos),
        "mismo_nivel": sin_cambio_nivel,
        "movilidad_institucional_total": len(movilidad_inst),
        "altas_por_nivel": nuevos_por_nivel,
        "altas_por_institucion_top10": nuevos_por_inst,
        "altas_por_area": nuevos_por_area,
        "bajas_por_nivel": bajas_por_nivel,
        "transiciones_promocion": trans_counts,
        "resumen_resolucion_identidad": {
            "ya_resueltos": len(ya_resueltos_2026),
            "pendientes": len(pendientes_resolucion)
        }
    }

    with open(OUTPUT_AUDIT, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, ensure_ascii=False, indent=2)
    print(f"💾 Guardado reporte completo de auditoría en: {OUTPUT_AUDIT}")

    # 6. Generar reporte HTML interactivo
    try:
        if str(BASE_DIR) not in sys.path:
            sys.path.insert(0, str(BASE_DIR))
        from scripts.tools.generate_snii_html_report import generate_snii_html_report
        html_out = generate_snii_html_report(json_path=OUTPUT_AUDIT)
        print(f"🌐 Generado reporte ejecutivo HTML en: {html_out}")
    except Exception as e:
        print(f"⚠️ No se pudo generar reporte HTML: {e}")

    print("\n" + "=" * 70)
    print("✅ AUDITORÍA FINALIZADA EXITOSAMENTE")
    print("=" * 70)


if __name__ == "__main__":
    run_audit()
