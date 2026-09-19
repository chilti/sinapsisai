# extract_sample.py
import tarfile
import os
import gzip
import shutil

SOURCE = "data/orcid_summaries_sample.tar.gz"
DEST = "data/sample_xml/"

def extract_safe():
    if not os.path.exists(DEST):
        os.makedirs(DEST)
    
    print(f"Opening {SOURCE}...")
    # El archivo está truncado, así que tarfile 'r:gz' podría fallar.
    # Vamos a intentar descomprimir a un tar temporal primero si falla.
    try:
        with tarfile.open(SOURCE, "r:gz") as tar:
            # Listar miembros para ver qué hay antes de extraer
            members = tar.getmembers()
            print(f"Found {len(members)} members.")
            for member in members[:10]: # Solo unos pocos para probar
                if member.isfile():
                    tar.extract(member, path=DEST)
                    print(f"Extracted: {member.name}")
    except Exception as e:
        print(f"Standard decompression failed: {e}")
        print("Attempting robust byte-by-byte decompression...")
        # A veces simplemente abrirlo como tar (sin gz) si podemos des-gzip-earlo antes
        try:
            temp_tar = "data/temp.tar"
            with gzip.open(SOURCE, 'rb') as f_in:
                with open(temp_tar, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            with tarfile.open(temp_tar, "r") as tar:
                 members = tar.getmembers()
                 print(f"After manual gunzip: {len(members)} members.")
                 for member in members:
                    if member.isfile():
                         tar.extract(member, path=DEST)
                         print(f"Extracted: {member.name}")
        except Exception as e2:
            print(f"Robust attempt failed: {e2}")

if __name__ == "__main__":
    extract_safe()
