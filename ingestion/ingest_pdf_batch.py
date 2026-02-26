"""
ingest_pdf_batch.py  – Ingesta liviana de PDFs a Qdrant (sin Grobid)
Uso:
    python ingestion/ingest_pdf_batch.py              # procesa los primeros 50 PDFs
    python ingestion/ingest_pdf_batch.py --limit 100  # procesa los primeros 100
    python ingestion/ingest_pdf_batch.py --all        # procesa TODOS (puede tardar)
"""
import sys
import os
import argparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import httpx
from dotenv import load_dotenv
from database.vector_store import QdrantStore

# -- PyPDF para extracción de texto liviana
try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader

load_dotenv()

# --- Config auth ---
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
if not base_url.endswith("/"):
    base_url += "/"
model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

auth_url = base_url
if user and password:
    if "://" in base_url:
        proto, rest = base_url.split("://", 1)
        auth_url = f"{proto}://{user}:{password}@{rest}"
    else:
        auth_url = f"http://{user}:{password}@{base_url}"

# Cliente httpx directo (evita incompatibilidades de formato de langchain-openai)
http_client = httpx.Client(verify=False, timeout=60)
EMBEDDINGS_URL = auth_url.rstrip('/') + '/embeddings'


def get_embeddings(texts: list) -> list:
    """Llama directamente al API de embeddings con httpx."""
    response = http_client.post(
        EMBEDDINGS_URL,
        json={"model": model, "input": texts},
    )
    response.raise_for_status()
    data = response.json()
    # Devuelve vectores ordenados por index
    return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]


qdrant = QdrantStore()

CHUNK_SIZE = 800   # caracteres por chunk
PDF_DIR = "pdf"


def extract_text_from_pdf(path: str) -> str:
    """Extrae el texto plano de un PDF con pypdf."""
    try:
        reader = PdfReader(path)
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n".join(pages)
    except Exception as e:
        print(f"  ⚠️  Error leyendo {path}: {e}")
        return ""


def chunk_text(text: str, size: int = CHUNK_SIZE):
    """Divide el texto en chunks de tamaño fijo."""
    return [text[i:i+size] for i in range(0, len(text), size) if text[i:i+size].strip()]


def ingest_pdf(file_path: str):
    filename = os.path.basename(file_path)
    print(f"  📄 Procesando: {filename}")

    text = extract_text_from_pdf(file_path)
    if not text:
        print(f"  ⚠️  Sin texto extraíble. Saltando.")
        return 0

    chunks = chunk_text(text)
    if not chunks:
        return 0

    # Filtro estricto: solo strings no vacíos de al menos 20 caracteres
    payloads = [
        {
            "source": filename,
            "text": chunk,
            "title": filename.replace(".pdf", ""),
        }
        for chunk in chunks
        if chunk and isinstance(chunk, str) and len(chunk.strip()) >= 20
    ]

    if not payloads:
        print("  ⚠️  No hay chunks válidos tras filtrar. Saltando.")
        return 0

    # Embeddings en lotes de 32
    try:
        texts = [p["text"] for p in payloads]
        embedded = []
        batch_size = 32
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            embedded.extend(get_embeddings(batch))
    except Exception as e:
        print(f"  ❌ Error generando embeddings: {e}")
        return 0

    qdrant.add_documents(payloads, embedded)
    print(f"  ✅ {len(chunks)} chunks indexados.")
    return len(chunks)


def main():
    parser = argparse.ArgumentParser(description="Ingesta liviana de PDFs a Qdrant")
    parser.add_argument("--limit", type=int, default=50, help="Número de PDFs a procesar (default: 50)")
    parser.add_argument("--all", action="store_true", help="Procesar todos los PDFs (puede tardar)")
    args = parser.parse_args()

    pdfs = sorted([
        os.path.join(PDF_DIR, f)
        for f in os.listdir(PDF_DIR)
        if f.lower().endswith(".pdf")
    ])

    total_available = len(pdfs)
    limit = total_available if args.all else args.limit
    pdfs = pdfs[:limit]

    print(f"\n📚 PDFs disponibles: {total_available}  |  A procesar: {len(pdfs)}")
    print("=" * 60)

    total_chunks = 0
    failed = 0
    for i, pdf_path in enumerate(pdfs, 1):
        print(f"\n[{i}/{len(pdfs)}]")
        n = ingest_pdf(pdf_path)
        if n == 0:
            failed += 1
        total_chunks += n

    print("\n" + "=" * 60)
    print(f"🎉 Ingesta completada: {len(pdfs) - failed} PDFs exitosos, {failed} fallidos.")
    print(f"📊 Total chunks indexados en Qdrant: {total_chunks}")

    # Verificar estado final
    info = qdrant.client.get_collection("scientific_papers")
    print(f"📦 Qdrant ahora tiene: {info.points_count} puntos totales.")


if __name__ == "__main__":
    main()
