import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
from langchain_mcp_adapters.tools import load_mcp_tools

async def get_mcp_tools(url: str = "http://localhost:8011/sse"):
    """
    Carga dinámicamente las herramientas desde un servidor MCP vía SSE.
    """
    try:
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await load_mcp_tools(session)
                return tools
    except Exception as e:
        print(f"Error cargando herramientas MCP desde {url}: {e}")
        return []

def get_mcp_tools_sync(url: str = "http://localhost:8011/sse"):
    """
    Versión síncrona para inicialización (usa un loop temporal).
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tools = loop.run_until_complete(get_mcp_tools(url))
        loop.close()
        return tools
    except Exception as e:
        print(f"Error síncrono MCP: {e}")
        return []

