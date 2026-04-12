import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import json

async def test_mcp_tools():
    # Parámetros del servidor (usando el python del venv)
    params = StdioServerParameters(
        command=r".\venv\Scripts\python",
        args=["agent/mcp_server.py"],
        env=None
    )
    
    print("Conectando al servidor MCP...")
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                print("Inicializando sesión...")
                await session.initialize()
                
                print("Listando herramientas...")
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                print(f"Herramientas encontradas: {tool_names}")
                
                if "download_paper_by_doi" in tool_names:
                    print("✅ La herramienta 'download_paper_by_doi' está disponible.")
                    
                    # Opcional: Probar la descarga con un DOI de prueba si se desea
                    # result = await session.call_tool("download_paper_by_doi", {"doi": "10.1038/s41586-020-2003-x"})
                    # print(f"Resultado de prueba: {result.content}")
                else:
                    print("❌ La herramienta 'download_paper_by_doi' NO se encontró.")
                    
    except Exception as e:
        print(f"Error durante la prueba: {e}")

if __name__ == "__main__":
    asyncio.run(test_mcp_tools())
