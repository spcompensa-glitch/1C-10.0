import os
import uvicorn
from fastapi import FastAPI
from mcp.server.fastapi import create_mcp_server

# Instância do App FastAPI
app = FastAPI(title="Crypten 1C-7.0 MCP Server", description="Servidor MCP para orquestração n8n e IA")

# Criar o servidor MCP
mcp_server = create_mcp_server(
    title="Crypten 1C-7.0 MCP",
    version="1.0.0"
)

# Acoplar o servidor MCP ao FastAPI
app.include_router(mcp_server.router)

# ===== FERRAMENTAS MCP (TOOLS) =====

@mcp_server.tool()
async def armar_tocaia(symbol: str, allocation: float) -> str:
    """
    Arma uma Tocaia para um par de criptomoeda.
    """
    # Aqui vamos integrar com o Captain / Quartermaster
    return f"Tocaia armada para {symbol} com {allocation}% de banca."

@mcp_server.tool()
async def obter_sinais_radar() -> str:
    """
    Retorna os sinais atuais mapeados pelo Radar (Librarian).
    """
    return "Sinais do Radar: WLDUSDT (LONG), INJUSDT (LONG)."

@mcp_server.tool()
async def status_okx() -> str:
    """
    Retorna o status de conexão com a OKX e o saldo atual.
    """
    return "OKX Conectada (Testnet). Saldo: $5000."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Iniciando Servidor MCP SSE na porta {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
