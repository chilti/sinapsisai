import os
import sys

# Agregamos path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ingestion.ingest_wos import WoSIngestor
from ingestion.pipeline import IngestionPipeline

def run_test_ingestion():
    print("🧪 Iniciando prueba de ingesta mixta (WoS + PDFs)...")
    
    # 1. Ingestar una pequeña muestra de WoS (Ya implementado, usamos la clase)
    print("\n--- 1. Ingestando WoS de prueba ---")
    wos_ingestor = WoSIngestor(batch_size=5)
    wos_file = r"C:\Users\jlja\Documents\Proyectos\RAGs\data\papers_2025_2026.txt"
    if os.path.exists(wos_file):
        # Ingestar solo los primeros registros (internamente WoSParser parsea todo, 
        # pero podemos forzar un lote pequeño en WoSIngestor si quisiéramos)
        # Por ahora lo dejamos correr para el archivo pequeño de 240 registros
        wos_ingestor.ingest_file(wos_file)
    else:
        print(f"⚠️ Archivo WoS no encontrado: {wos_file}")

    # 2. Ingestar 3 PDFs de la carpeta pdf/
    print("\n--- 2. Ingestando PDFs de prueba ---")
    pdf_pipeline = IngestionPipeline()
    pdf_dir = r"C:\Users\jlja\Documents\Proyectos\RAGs\pdf"
    
    if os.path.exists(pdf_dir):
        # Listar y tomar 3 archivos
        pdf_files = [f for f in os.listdir(pdf_dir) if f.endswith('.pdf')]
        test_pdfs = pdf_files[:3]
        
        for pdf_name in test_pdfs:
            pdf_path = os.path.join(pdf_dir, pdf_name)
            print(f"📄 Procesando PDF: {pdf_name}")
            
            # Para el PDF necesitamos metadatos dummy (o recuperarlos de OpenAlex/Crossref si tuviéramos DOI)
            # Como es prueba, generamos un DOI dummy
            dummy_meta = {
                "paper_id": f"PDF_{pdf_name[:10]}",
                "title": pdf_name.replace(".pdf", ""),
                "doi": f"10.test/{pdf_name[:5]}",
                "year": 2024,
                "citations": 0,
                "authors": [{"name": "Autor Desconocido (PDF)"}],
                "concepts": [{"name": "Prueba PDF"}]
            }
            
            try:
                pdf_pipeline.ingest_scientific_paper(pdf_path, dummy_meta)
            except Exception as e:
                print(f"❌ Error al procesar {pdf_name}: {e}")
    else:
        print(f"⚠️ Carpeta de PDFs no encontrada: {pdf_dir}")

    print("\n✅ Prueba de ingesta finalizada.")

if __name__ == "__main__":
    run_test_ingestion()
