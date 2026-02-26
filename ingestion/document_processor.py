import requests
import json
import os
from typing import Dict, Any, List

class DocumentProcessor:
    """
    Se encarga de procesar documentos complejos (PDFs científicos) extrayendo 
    texto estructurado, metadatos, y referencias usando Grobid y Unstructured.
    """
    def __init__(self, grobid_url="http://localhost:8070/api/processFulltextDocument", unstructured_url="http://localhost:8000/general/v0/general"):
        self.grobid_url = grobid_url
        self.unstructured_url = unstructured_url

    def process_scientific_pdf(self, file_path: str) -> Dict[str, Any]:
        """
        Envía un PDF a Grobid para extraer su estructura lógica en XML (TEI) 
        y luego lo parsea a un formato de diccionario simplificado.
        Ideal para recuperar Título, Autores, Abstract, Secciones y Referencias.
        """
        print(f"📄 Procesando {file_path} con Grobid...")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"El archivo {file_path} no existe.")

        with open(file_path, 'rb') as f:
            # Grobid espera el archivo multipart/form-data
            files = {'input': f}
            response = requests.post(self.grobid_url, files=files)
            
        if response.status_code == 200:
            tei_xml = response.text
            # Aquí idealmente se usa BeautifulSoup(tei_xml, 'xml') para parsear el TEI.
            # Para este MVP, retornaremos el XML crudo o un resumen.
            print("✅ Grobid procesó el documento exitosamente.")
            return {"status": "success", "tei_xml": tei_xml, "source": file_path}
        else:
            print(f"❌ Error en Grobid: {response.status_code}")
            return {"status": "error", "message": response.text}


    def process_general_document(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Usa Unstructured.io para procesar Word, PPTX o PDFs no científicos.
        Retorna una lista de "elementos" (Title, NarrativeText, Table, etc.)
        """
        print(f"📄 Procesando {file_path} con Unstructured...")
        
        with open(file_path, 'rb') as f:
             files = {"files": (os.path.basename(file_path), f)}
             response = requests.post(self.unstructured_url, files=files)
             
        if response.status_code == 200:
             elements = response.json()
             return elements
        else:
             print(f"❌ Error en Unstructured: {response.status_code}")
             return []
