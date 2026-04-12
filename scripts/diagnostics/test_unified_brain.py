import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from agent.orchestrator import RAGOrchestrator
import os

async def main():
    # 1. Configuración del Servidor MCP de OpenAlex (ejecutado como subproceso)
    # Importante: Asegúrate de que el path sea correcto y mcp_server.py sea ejecutable
    import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["agent/mcp_server.py"],
        env=os.environ.copy()
    )

    print("🔌 Conectando al Servidor MCP de OpenAlex...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 2. Cargar herramientas MCP a formato LangChain
            # Nota: Esto requiere langchain-mcp-adapters instalado
            mcp_tools = await load_mcp_tools(session)
            print(f"✅ {len(mcp_tools)} herramientas MCP cargadas.")

            # 3. Inicializar el Orquestador Unificado
            # El orquestador ya lee automáticamente de .env si no pasamos argumentos
            orchestrator = RAGOrchestrator(
                tools_list=mcp_tools
            )
            
            print("\n--- 🧠 Cerebro Unificado Listo ---")
            
            # 4. Prueba de Integración: Pregunta que requiere MCP + Razonamiento + (opcional) Código
            session_id = "test_user_001"
            query = "¿Cuántos trabajos publicó el autor 'Humberto Carrillo Calvet' en el último año según OpenAlex? Genera una respuesta detallada."
            
            print(f"\nUser: {query}")
            response = await orchestrator.ask(session_id, query)
            print(f"\nAssistant: {response}")
            
            # 5. Prueba de Híbrido: Pregunta que podría ir a Qdrant o Neo4j (si hubiera datos)
            query_hybrid = "¿Hay algún paper sobre 'Machine Learning' en nuestra base de datos local? Si no, búscalo en OpenAlex."
            print(f"\nUser: {query_hybrid}")
            response_hybrid = await orchestrator.ask(session_id, query_hybrid)
            print(f"\nAssistant: {response_hybrid}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSaliendo...")
