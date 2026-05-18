import json
import re
import argparse
import sys

# Patrones regex
# ORCID: 16 dígitos agrupados en bloques de 4 separados por guiones. El último puede ser 'X'.
ORCID_PATTERN = re.compile(r'\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b', re.IGNORECASE)

# Scopus ID: Secuencia de entre 8 y 12 dígitos aproximadamente.
SCOPUS_PATTERN = re.compile(r'^\d+$')

def extract_valid_id(value: str, pattern: re.Pattern) -> str | None:
    if not value:
        return None
    
    # Extraer todas las coincidencias
    if pattern == ORCID_PATTERN:
        match = ORCID_PATTERN.search(value)
        if match:
            return match.group(0).upper()
            
    # Para Scopus, limpiamos el string de URLs o comas
    if pattern == SCOPUS_PATTERN:
        # A veces Scopus viene como URL o múltiples separados por comas
        parts = value.split(',')
        for p in parts:
            p = p.strip()
            # Si es una URL, extraer el authorId de la query
            if 'scopus.com' in p and 'authorId=' in p:
                match = re.search(r'authorId=(\d+)', p)
                if match:
                    return match.group(1)
            # Solo números
            if SCOPUS_PATTERN.match(p):
                return p
    return None


def is_orcid(value: str) -> bool:
    if not value: return False
    return bool(ORCID_PATTERN.search(value))

def is_scopus(value: str) -> bool:
    if not value: return False
    parts = value.split(',')
    for p in parts:
        p = p.strip()
        if SCOPUS_PATTERN.match(p) or ('scopus.com' in p and 'authorId=' in p):
            return True
    return False


def clean_professor_ids(filepath: str, output_path: str = None):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Archivo no encontrado: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ Error al decodificar JSON en: {filepath}")
        sys.exit(1)

    print(f"Saneando archivo: {filepath} ({len(data)} profesores)")
    
    corrections = 0
    
    for key, prof in data.items():
        original_scopus = str(prof.get('scopus', '')).strip()
        original_orcid = str(prof.get('orcid', '')).strip()
        
        new_scopus = original_scopus
        new_orcid = original_orcid
        
        changed = False

        # Caso: ORCID en campo de Scopus
        if is_orcid(original_scopus) and not is_scopus(original_scopus):
            extracted = extract_valid_id(original_scopus, ORCID_PATTERN)
            if extracted:
                new_orcid = extracted
                new_scopus = ""  # Limpiamos el de scopus
                changed = True

        # Caso: Scopus en campo de ORCID
        if is_scopus(original_orcid) and not is_orcid(original_orcid):
            extracted = extract_valid_id(original_orcid, SCOPUS_PATTERN)
            if extracted:
                if not changed:
                    new_scopus = extracted
                    new_orcid = ""
                    changed = True
                else:
                    # Si ya habíamos cambiado (intercambio cruzado)
                    new_scopus = extracted

        # Extraer limpio si hay ruido visual pero está en el campo correcto
        if not changed:
            if original_scopus and is_scopus(original_scopus):
                ex_sc = extract_valid_id(original_scopus, SCOPUS_PATTERN)
                if ex_sc and ex_sc != original_scopus:
                    new_scopus = ex_sc
                    changed = True
            if original_orcid and is_orcid(original_orcid):
                ex_or = extract_valid_id(original_orcid, ORCID_PATTERN)
                if ex_or and ex_or != original_orcid:
                    new_orcid = ex_or
                    changed = True

        if changed:
            print(f"🔄 Corrigiendo ID en {prof.get('original_name', key)}:")
            if original_scopus != new_scopus:
                print(f"   [Scopus] '{original_scopus}' -> '{new_scopus}'")
            if original_orcid != new_orcid:
                print(f"   [ORCID]  '{original_orcid}' -> '{new_orcid}'")
                
            prof['scopus'] = new_scopus
            prof['orcid'] = new_orcid
            data[key] = prof
            corrections += 1

    
    if corrections == 0:
        print("\n✅ Ningún profesor necesitó correcciones.")
        return

    out_file = output_path if output_path else filepath
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        
    print(f"\n✅ Terminado. Se hicieron {corrections} correcciones.")
    print(f"💾 Guardado en: {out_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Limpia e intercambia IDs de Scopus y ORCID extraviados en dicts de JSON.")
    parser.add_argument("input_file", help="Ruta al archivo JSON a corregir")
    parser.add_argument("--output", "-o", default=None, help="Ruta de salida (por defecto, sobreescribe el input)")
    
    args = parser.parse_args()
    clean_professor_ids(args.input_file, args.output)
