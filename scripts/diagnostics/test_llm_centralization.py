import sys
import os
import asyncio

# Asegurar que el directorio raíz esté en el path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from lib.llm_utils import (
    LLMConfig, 
    get_openai_client, 
    get_chat_model, 
    get_embeddings_model, 
    handle_llm_exception
)

async def test_all_connections():
    print("=== Diagnóstico de Centralización LLM ===")
    print(f"Auth URL: {LLMConfig.get_auth_url()}")
    print(f"Chat Model: {LLMConfig.get_model_name()}")
    print(f"Embeddings Model: {LLMConfig.get_embedding_model_name()}")
    print("-" * 40)

    # 1. Test OpenAI Client (Sync)
    print("1. Probando Cliente OpenAI (Sync)...")
    try:
        client = get_openai_client(async_mode=False)
        # Probamos listar modelos como un 'ping' básico
        models = client.models.list()
        print(f"   [OK] Exito. Modelos disponibles: {len(models.data)}")
    except Exception as e:
        try:
            handle_llm_exception(e)
        except ConnectionError as ce:
            print(f"   [FAIL] Error Critico (Esperado si el server esta caido): {ce}")
        except Exception:
            print(f"   [FAIL] Error Inesperado: {e}")

    # 2. Test LangChain Chat (Async)
    print("\n2. Probando LangChain ChatOpenAI (Async)...")
    try:
        chat = get_chat_model(temperature=0)
        # Invocación simple
        response = await chat.ainvoke("Responde solo con la palabra 'OK'")
        print(f"   [OK] Exito. Respuesta: {response.content}")
    except Exception as e:
        print(f"   [FAIL] Fallo: {e}")

    # 3. Test LangChain Embeddings (Sync)
    print("\n3. Probando LangChain OpenAIEmbeddings (Sync)...")
    try:
        embeddings = get_embeddings_model()
        vector = embeddings.embed_query("Prueba de centralizacion")
        print(f"   [OK] Exito. Dimension del vector: {len(vector)}")
    except Exception as e:
        print(f"   [FAIL] Fallo: {e}")

    print("\n=== Diagnóstico Completado ===")

if __name__ == "__main__":
    asyncio.run(test_all_connections())
