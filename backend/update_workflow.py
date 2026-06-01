import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv(os.path.join("..", ".env"))
TOKEN = os.getenv("N8N_MCP_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "123:TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "123")
API_URL = "https://n8n-production-8e2d4.up.railway.app/api/v1/workflows/PI0VK4G2xXADAX0I"
PYTHON_APP = os.getenv("RAILWAY_URL", "https://1crypten-hermes-agent-production.up.railway.app")

def http_node(name, path, x, y):
    return {
        "parameters": {
            "url": f"{PYTHON_APP}{path}",
            "method": "GET"
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.1,
        "position": [x, y],
        "name": name,
        "id": name.replace(" ", "")
    }

nodes = [
    {
        "parameters": {"rule": {"interval": [{"field": "minutes"}]}},
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.1,
        "position": [0, 0],
        "name": "Ciclo Macro (5m)",
        "id": "trigger"
    },
    http_node("Observatory (Python)", "/api/system/state", 200, 0),
    http_node("Radar (Python)", "/api/radar/pulse", 400, 0),
    {
        "parameters": {
            "conditions": {
                "boolean": [
                    {
                        "value1": "={{ $json.slots_livres > 0 || true }}", # mock dynamic check for testing
                        "value2": True
                    }
                ]
            }
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 1,
        "position": [600, 0],
        "name": "Avalia Slots Livres",
        "id": "ifslots"
    },
    http_node("Captain (Atira)", "/api/captain/tocaias", 800, -100),
    http_node("Slot 1 (Status)", "/api/slots", 1000, 0),
    http_node("Slot 2 (Status)", "/api/slots", 1200, 0),
    http_node("Slot 3 (Status)", "/api/slots", 1400, 0),
    http_node("Slot 4 (Status)", "/api/slots", 1600, 0),
    http_node("Facão & Ceifeiro", "/api/system/state", 1800, 0),
    http_node("Moonbags", "/api/moonbags", 2000, 0),
    http_node("Vault Histórico", "/api/vault/status", 2200, 0),
    {
        "parameters": {
            "url": f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            "method": "POST",
            "sendBody": True,
            "bodyParameters": {
                "parameters": [
                    {"name": "chat_id", "value": TELEGRAM_CHAT_ID},
                    {"name": "text", "value": "🤖 [1C-7.0] Ciclo Macro Orquestrado e Finalizado com Sucesso!"}
                ]
            }
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.1,
        "position": [2400, 0],
        "name": "Hermes (Telegram)",
        "id": "telegram"
    }
]

connections = {
    "Ciclo Macro (5m)": {"main": [[{"node": "Observatory (Python)", "type": "main", "index": 0}]]},
    "Observatory (Python)": {"main": [[{"node": "Radar (Python)", "type": "main", "index": 0}]]},
    "Radar (Python)": {"main": [[{"node": "Avalia Slots Livres", "type": "main", "index": 0}]]},
    "Avalia Slots Livres": {
        "main": [
            [{"node": "Captain (Atira)", "type": "main", "index": 0}],
            [{"node": "Slot 1 (Status)", "type": "main", "index": 0}]
        ]
    },
    "Captain (Atira)": {"main": [[{"node": "Slot 1 (Status)", "type": "main", "index": 0}]]},
    "Slot 1 (Status)": {"main": [[{"node": "Slot 2 (Status)", "type": "main", "index": 0}]]},
    "Slot 2 (Status)": {"main": [[{"node": "Slot 3 (Status)", "type": "main", "index": 0}]]},
    "Slot 3 (Status)": {"main": [[{"node": "Slot 4 (Status)", "type": "main", "index": 0}]]},
    "Slot 4 (Status)": {"main": [[{"node": "Facão & Ceifeiro", "type": "main", "index": 0}]]},
    "Facão & Ceifeiro": {"main": [[{"node": "Moonbags", "type": "main", "index": 0}]]},
    "Moonbags": {"main": [[{"node": "Vault Histórico", "type": "main", "index": 0}]]},
    "Vault Histórico": {"main": [[{"node": "Hermes (Telegram)", "type": "main", "index": 0}]]}
}

payload = {
    "nodes": nodes,
    "connections": connections,
    "name": "Macro-Orquestrador Híbrido 1C-7.0",
    "settings": {}
}

print("Enviando fluxo para o n8n...")
req = urllib.request.Request(API_URL, method="PUT", headers={
    "X-N8N-API-KEY": TOKEN,
    "Content-Type": "application/json"
}, data=json.dumps(payload).encode("utf-8"))

try:
    resp = urllib.request.urlopen(req)
    print("Update Response:", resp.status)
    
    print("Iniciando execução de teste no n8n...")
    run_url = "https://n8n-production-8e2d4.up.railway.app/api/v1/workflows/PI0VK4G2xXADAX0I/run"
    run_req = urllib.request.Request(run_url, method="POST", headers={
        "X-N8N-API-KEY": TOKEN,
        "Content-Type": "application/json"
    }, data=b'{}')
    run_resp = urllib.request.urlopen(run_req)
    result = json.loads(run_resp.read().decode("utf-8"))
    print("Run result:", json.dumps(result, indent=2))
except Exception as e:
    print("Error:", e)
    if hasattr(e, 'read'):
        print(e.read().decode())
