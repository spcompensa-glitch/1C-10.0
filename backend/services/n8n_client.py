import os
import httpx
import logging

logger = logging.getLogger("N8NMCPClient")

class N8NMCPClient:
    """
    Cliente MCP HTTP para conectar o backend Python ao servidor MCP do n8n.
    Permite que os Agentes em Python listem e executem fluxos do n8n dinamicamente.
    """
    def __init__(self):
        self.url = os.getenv("N8N_MCP_URL", "https://n8n-production-8e2d4.up.railway.app/mcp-server/http")
        self.token = os.getenv("N8N_MCP_TOKEN", "")

    def _get_headers(self):
        headers = {
            "Content-Type": "application/json",
            "X-N8N-API-KEY": self.token
        }
        return headers

    async def list_tools(self) -> dict:
        """Lista os fluxos disponíveis via Public API."""
        url = self.url.replace("/mcp-server/http", "/api/v1/workflows")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._get_headers())
                resp.raise_for_status()
                data = resp.json()
                # Transforma no formato parecido com tools
                tools = []
                for wf in data.get("data", []):
                    if wf.get("active", False):
                        tools.append({
                            "id": wf.get("id"),
                            "name": wf.get("name"),
                            "description": "Fluxo ativo do n8n"
                        })
                return {"tools": tools}
        except Exception as e:
            logger.error(f"❌ Erro ao listar fluxos do n8n (API Pública): {e}")
            raise

    async def call_tool(self, tool_name_or_id: str, arguments: dict = None) -> dict:
        """Aciona um fluxo específico no n8n via Webhook ou Run."""
        if arguments is None:
            arguments = {}
            
        # Primeiro acha o ID pelo nome, se não for um ID
        workflows_url = self.url.replace("/mcp-server/http", "/api/v1/workflows")
        target_id = tool_name_or_id
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(workflows_url, headers=self._get_headers())
                if resp.status_code == 200:
                    for wf in resp.json().get("data", []):
                        if wf.get("name").lower() == tool_name_or_id.lower() or wf.get("id") == tool_name_or_id:
                            target_id = wf.get("id")
                            break
                            
                # Dispara o fluxo via API
                run_url = self.url.replace("/mcp-server/http", f"/api/v1/workflows/{target_id}/run")
                run_resp = await client.post(run_url, json={"triggerData": arguments}, headers=self._get_headers())
                run_resp.raise_for_status()
                return run_resp.json()
        except Exception as e:
            logger.error(f"❌ Erro ao executar fluxo {tool_name_or_id} no n8n: {e}")
            raise

n8n_client = N8NMCPClient()
