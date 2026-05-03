import json
import os
import sys

# Forzar UTF-8
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PATH = "data/snii_llm_verified_matches.json"
FIXED_PATH = "data/snii_llm_verified_matches_fixed.json"

def fix_json():
    print(f"DEBUG: Intentando rescatar JSON: {PATH}")
    if not os.path.exists(PATH):
        print("ERROR: El archivo no existe.")
        return

    try:
        with open(PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            print(f"INFO: El JSON es valido. Tiene {len(data)} registros.")
            return
    except Exception as e:
        print(f"WARN: Error detectado: {e}")
        print("INFO: Intentando rescate...")

    try:
        with open(PATH, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
        # Si termina en coma, quitarla
        if content.endswith(','):
            content = content[:-1]
            
        # Intentar encontrar el ultimo objeto completo
        last_bracket = content.rfind('}')
        if last_bracket != -1:
            fixed_content = content[:last_bracket+1] + "\n]"
            # A veces hay que asegurarse de que empiece con [ si se corrompio el inicio
            if not fixed_content.startswith('['):
                fixed_content = "[" + fixed_content
                
            data = json.loads(fixed_content)
            print(f"SUCCESS: Rescate exitoso! Se recuperaron {len(data)} registros.")
            with open(FIXED_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            os.replace(FIXED_PATH, PATH)
            print(f"INFO: Archivo original reemplazado.")
        else:
            print("ERROR: No se encontro ningun cierre de objeto '}'.")
    except Exception as e:
        print(f"ERROR: Fallo critico durante el rescate: {e}")

if __name__ == "__main__":
    fix_json()
