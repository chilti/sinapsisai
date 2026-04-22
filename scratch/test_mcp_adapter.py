from langchain_mcp_adapters.tools import load_mcp_tools
import asyncio

async def test():
    try:
        # Intentamos cargar herramientas desde el servidor MCP (aunque no esté corriendo, para ver la firma)
        tools = await load_mcp_tools("http://localhost:8001/sse")
        print(f"Tools: {tools}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
