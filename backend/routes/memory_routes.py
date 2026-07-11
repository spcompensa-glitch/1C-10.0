import os
import re
import time
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pathlib import Path
from services.whisper_service import whisper_service
from services.galaxy_memory_service import galaxy_memory_service
from datetime import datetime

logger = logging.getLogger("MemoryRoutes")
router = APIRouter(prefix="/api/memory", tags=["Memory"])

VAULT_DIR = Path("vault_galaxy").resolve()

CHAT_PREFIX = "Chat_Hermes_"

def _get_recency(mtime: float) -> float:
    """Return 0.0-1.0 recency score (1 = most recent)."""
    now = time.time()
    age_hours = (now - mtime) / 3600
    # Full brightness for files < 24h old, fading to 0 over 7 days
    return max(0.0, min(1.0, 1.0 - (age_hours / 168)))

@router.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    temp_dir = Path("temp_audio")
    temp_dir.mkdir(exist_ok=True)
    
    file_ext = Path(file.filename).suffix or ".webm"
    temp_file_path = temp_dir / f"audio_{int(datetime.now().timestamp())}{file_ext}"
    
    try:
        with open(temp_file_path, "wb") as buffer:
            buffer.write(await file.read())
        
        transcription = whisper_service.transcribe(str(temp_file_path))
        
        if not transcription or transcription.startswith("[Erro"):
            raise HTTPException(status_code=500, detail=f"Falha na transcrição: {transcription}")
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        journal_file_name = f"{today_str}.md"
        journal_path = VAULT_DIR / "journal" / journal_file_name
        
        time_str = datetime.now().strftime("%H:%M:%S")
        entry_content = f"\n\n### 🎙️ Nota de Voz ({time_str})\n> {transcription}\n"
        
        if not journal_path.exists():
            os.makedirs(journal_path.parent, exist_ok=True)
            base_content = f"---\ntitle: Diário de Bordo\ndate: {today_str}\ntype: journal\ntags:\n  - diário\n  - notas_voz\n---\n# Diário de Bordo — {today_str}\n"
            with open(journal_path, "w", encoding="utf-8") as f:
                f.write(base_content)
                
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(entry_content)
            
        return {"success": True, "transcription": transcription, "file": journal_file_name}
    except Exception as e:
        logger.error(f"Error in upload_audio: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if temp_file_path.exists():
            try:
                os.remove(temp_file_path)
            except Exception as ex:
                logger.warning(f"Failed to delete temp file {temp_file_path}: {ex}")

@router.get("/graph-data")
async def get_graph_data():
    nodes = []
    links = []
    
    categories = ["journal", "trades", "strategies"]
    node_ids = set()
    link_pattern = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
    
    # Collect all files with mtime for recency scoring
    all_files = []
    for cat in categories:
        cat_path = VAULT_DIR / cat
        if not cat_path.exists():
            continue
        for root, _, files in os.walk(cat_path):
            for file in files:
                if not file.endswith(".md"):
                    continue
                file_path = Path(root) / file
                rel_path = Path(root).relative_to(VAULT_DIR)
                node_id = f"{rel_path}/{file}".replace("\\", "/")
                try:
                    mtime = file_path.stat().st_mtime
                    file_size = file_path.stat().st_size
                except Exception:
                    mtime = 0
                    file_size = 0
                all_files.append({
                    "node_id": node_id,
                    "file": file,
                    "cat": cat,
                    "file_path": file_path,
                    "file_size": file_size,
                    "mtime": mtime,
                })

    # Determine max mtime for normalization
    max_mtime = max((f["mtime"] for f in all_files), default=time.time())
    if max_mtime <= 0:
        max_mtime = time.time()

    for fi in all_files:
        node_id = fi["node_id"]
        if node_id in node_ids:
            continue

        recency = _get_recency(fi["mtime"])
        nodes.append({
            "id": node_id,
            "label": fi["file"].replace(".md", ""),
            "category": fi["cat"],
            "val": max(2.5, min(12.0, fi["file_size"] / 300.0)),
            "recency": round(recency, 3),
        })
        node_ids.add(node_id)

        # Auto-link Chat_Hermes files to their corresponding journal file
        if fi["file"].startswith(CHAT_PREFIX):
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', fi["file"])
            if date_match:
                journal_target = f"journal/{date_match.group(1)}.md"
                if journal_target not in node_ids:
                    # Will be added as phantom below
                    pass
                links.append({
                    "source": node_id,
                    "target": journal_target,
                })

        # Parse wikilinks
        try:
            with open(fi["file_path"], "r", encoding="utf-8") as f:
                content = f.read()
            matches = link_pattern.findall(content)
            for match in matches:
                match_cleaned = match.strip()
                target_id = None
                if "/" in match_cleaned:
                    target_id = f"{match_cleaned}.md"
                else:
                    if match_cleaned.startswith(("journal/", "strategies/", "trades/")):
                        target_id = f"{match_cleaned}.md"
                    else:
                        if len(match_cleaned.split("-")) >= 2:
                            target_id = f"trades/{match_cleaned}.md"
                        else:
                            target_id = f"journal/{match_cleaned}.md"
                if target_id:
                    links.append({"source": node_id, "target": target_id})
        except Exception:
            pass

    # Add phantom nodes for link targets that don't exist yet
    for link in links:
        target = link["target"]
        if target not in node_ids:
            cat = target.split("/")[0] if "/" in target else "journal"
            label = target.split("/")[-1].replace(".md", "") if "/" in target else target.replace(".md", "")
            nodes.append({
                "id": target,
                "label": label,
                "category": cat,
                "val": 2,
                "recency": 0.0,
            })
            node_ids.add(target)

    return {"nodes": nodes, "links": links}

@router.get("/files")
async def list_galaxy_files():
    result = {
        "journal": [],
        "trades": [],
        "strategies": [],
        "chats": [],
        "vault_path": str(VAULT_DIR)
    }
    for cat in ["journal", "trades", "strategies"]:
        cat_path = VAULT_DIR / cat
        if cat_path.exists():
            all_files = sorted([f for f in os.listdir(cat_path) if f.endswith(".md")], reverse=True)
            if cat == "journal":
                # Split journal into regular journals and Hermes chats
                result["journal"] = [f for f in all_files if not f.startswith(CHAT_PREFIX)]
                result["chats"] = [f for f in all_files if f.startswith(CHAT_PREFIX)]
            else:
                result[cat] = all_files

    total_all = len(result["journal"]) + len(result["trades"]) + len(result["strategies"]) + len(result["chats"])
    result["total_memories"] = total_all
    result["total_notes"] = len(result["journal"]) + len(result["strategies"]) + len(result["chats"])
    return result

@router.get("/galaxy-full")
async def get_galaxy_full():
    """Full system galaxy: agents, services, strategies, vault, routes — everything."""
    nodes = []
    links = []
    node_ids = set()
    link_pattern = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')

    def add_node(nid, label, cat, val=3, recency=0.5, desc="", group=""):
        if nid in node_ids:
            return
        nodes.append({"id": nid, "label": label, "category": cat, "val": val, "recency": recency, "description": desc, "group": group})
        node_ids.add(nid)

    def add_link(src, tgt, strength=1):
        links.append({"source": src, "target": tgt, "strength": strength})

    # ═══════════════════════════════════════════
    # 1. CORE INFRASTRUCTURE
    # ═══════════════════════════════════════════
    core_components = [
        ("core:fastapi", "FastAPI", "Backend Python 3.12", 8),
        ("core:postgresql", "PostgreSQL", "Banco principal SSOT", 7),
        ("core:firebase", "Firebase", "RTDB + Firestore sync", 6),
        ("core:okx", "OKX Exchange", "Portfolio Margin API", 7),
        ("core:redis", "Redis", "Cache layer", 4),
        ("core:railway", "Railway", "Deploy + Docker", 5),
        ("core:whisper", "Whisper", "Transcrição local", 3),
        ("core:deepseek", "DeepSeek", "AI cascade primary", 4),
    ]
    for nid, label, desc, val in core_components:
        add_node(nid, label, "core", val, 0.8, desc, "infra")

    # ═══════════════════════════════════════════
    # 2. AI AGENTS (19+)
    # ═══════════════════════════════════════════
    agents = [
        ("agent:captain", "CaptainAgent", "Despachante de sinais · Quality Gate · V20.5", 9),
        ("agent:oracle", "OracleAgent", "Regime de mercado · Grade ADX", 7),
        ("agent:flash", "FlashAgent", "Escadinha de stops · Monitor 1s", 8),
        ("agent:bankroll_guardian", "BankrollGuardian", "Autorização de trades · Limites", 7),
        ("agent:slot_operator", "SlotOperator", "Failsafe · Virtual stop loss · 3s", 6),
        ("agent:fleet_audit", "FleetAudit", "Reconciliacao 20s · Ghost cleanup", 6),
        ("agent:quartermaster", "Quartermaster", "Classificacao leverage por wick", 5),
        ("agent:hermes", "HermesAgent", "Compliance · Telemetria · Chat · DeepSeek", 7),
        ("agent:jarvis", "JarvisBrain", "Chat multi-dimensao (10 dimensoes)", 5),
        ("agent:macro_analyst", "MacroAnalyst", "Risco macro BTC · Pearson correlation", 6),
        ("agent:librarian", "Librarian", "DNA do ativo · Rankings · Setores · 2h", 6),
        ("agent:librarian_auditor", "LibrarianAuditor", "Ajuste de bias · Ciclo 4h", 4),
        ("agent:whale_tracker", "WhaleTracker", "Fluxo institucional · CVD/OI", 6),
        ("agent:onchain_watcher", "OnChainWhaleWatcher", "Blockchain · Bybit hot wallet", 5),
        ("agent:trade_analyst", "TradeAnalyst", "Autopsia pos-trade · 30min", 5),
        ("agent:sentiment", "SentimentSpecialist", "Sentimento retail · LS-Ratio", 4),
        ("agent:ai_service", "AIService", "Cascade: DeepSeek → Gemini → OpenRouter", 6),
        ("agent:execution_auditor", "ExecutionAuditor", "Sentinel · Sanitiza sinais · 50x", 6),
        ("agent:sandbox_service", "SandboxService", "Forward Testing Lab · Espelho real", 7),
    ]
    for nid, label, desc, val in agents:
        add_node(nid, label, "agent", val, 0.9, desc, "agents")

    # ═══════════════════════════════════════════
    # 3. SERVICES
    # ═══════════════════════════════════════════
    services = [
        ("svc:signal_generator", "SignalGenerator", "Motor principal · 3 estratégias M30", 8),
        ("svc:bankroll_manager", "BankrollManager", "Execução de ordens · Fila OKX", 6),
        ("svc:order_projection", "OrderProjectionService", "Escadinha de stops · 3 ladders", 7),
        ("svc:okx_rest", "OKX REST", "API REST · Klines · Tickers", 5),
        ("svc:okx_ws", "OKX WebSocket", "Dados em tempo real · Posições", 6),
        ("svc:okx_ws_public", "OKX WS Public", "Preços públicos · Conservative price", 5),
        ("svc:sandbox_swing", "SandboxSwingService", "Swing Lab · Scan M30 · Zero-Risk", 7),
        ("svc:sandbox_scalping", "SandboxScalpingEngine", "VWAP SNIPER · M1/M5 · ATR stops", 7),
        ("svc:phase_detector", "PhaseDetector", "Fase 1+2 · Explosion Score · V120", 6),
        ("svc:firebase_service", "FirebaseService", "Sync RTDB/Firestore · Radar Pulse", 5),
        ("svc:database_service", "DatabaseService", "PostgreSQL async · Slots/trades", 5),
        ("svc:websocket_service", "WebSocketService", "Broadcast UI · Real-time", 4),
        ("svc:galaxy_memory", "GalaxyMemoryService", "Obsidian vault · Trades/Journal", 5),
        ("svc:telegram", "TelegramService", "Alertas Telegram", 3),
        ("svc:whisper_svc", "WhisperService", "Transcrição de áudio", 3),
    ]
    for nid, label, desc, val in services:
        add_node(nid, label, "service", val, 0.7, desc, "services")

    # ═══════════════════════════════════════════
    # 4. STRATEGIES
    # ═══════════════════════════════════════════
    strats = [
        ("strat:velocity_flow", "VELOCITY FLOW", "Momentum de alta · Breakout · M30", 7),
        ("strat:alpha_shield", "ALPHA SHIELD", "Pullback · Proteção · M30", 7),
        ("strat:decor_shadow", "DECOR SHADOW", "Reversão · Exaustão · Decorrelação", 7),
        ("strat:decor_hunter", "DECOR_HUNTER", "Caça a decorrelação", 4),
        ("strat:lrt", "LRT", "Liquidez alta frequência", 4),
        ("strat:dvap", "DVAP", "Reversão de exaustão", 5),
        ("strat:fas", "FAS", "Funding Squeeze", 5),
        ("strat:mola", "MOLA", "Breakout de volatilidade", 5),
        ("strat:abcd", "ABCD / 1-2-3", "Tendências geométricas", 4),
        ("strat:vwap_sniper", "VWAP SNIPER", "Scalping · EMA200 + VWAP + StochRSI", 6),
    ]
    for nid, label, desc, val in strats:
        add_node(nid, label, "strategy", val, 0.6, desc, "strategies")

    # ═══════════════════════════════════════════
    # 5. FRONTEND PAGES
    # ═══════════════════════════════════════════
    pages = [
        ("ui:cockpit", "Cockpit", "Dashboard principal · SPA 430KB", 6),
        ("ui:sandbox", "Sandbox", "Forward Testing Lab UI", 5),
        ("ui:memory", "Memory Galaxy", "Obsidian Second Brain · 3D", 5),
        ("ui:observatory", "Observatory", "Asset Observatory · Fluid Grid", 4),
        ("ui:neural_chat", "Neural Chat", "Neural Chat Fusion", 4),
        ("ui:login", "Login", "Auth · JWT", 3),
    ]
    for nid, label, desc, val in pages:
        add_node(nid, label, "ui", val, 0.5, desc, "ui")

    # ═══════════════════════════════════════════
    # 6. VAULT FILES (real data)
    # ═══════════════════════════════════════════
    vault_files_info = []
    for cat in ["journal", "trades", "strategies"]:
        cat_path = VAULT_DIR / cat
        if not cat_path.exists():
            continue
        for root, _, files in os.walk(cat_path):
            for file in files:
                if not file.endswith(".md"):
                    continue
                file_path = Path(root) / file
                rel_path = Path(root).relative_to(VAULT_DIR)
                node_id = f"vault:{rel_path}/{file}".replace("\\", "/")
                try:
                    mtime = file_path.stat().st_mtime
                    file_size = file_path.stat().st_size
                except Exception:
                    mtime = 0
                    file_size = 0
                recency = _get_recency(mtime)
                val = max(2, min(8, file_size / 200.0))
                label = file.replace(".md", "")
                is_chat = file.startswith(CHAT_PREFIX)
                group = "chats" if is_chat else cat
                desc_cat = "Chat com Hermes" if is_chat else cat.capitalize()
                add_node(node_id, label, "vault", val, recency, desc_cat, group)
                vault_files_info.append({"node_id": node_id, "file": file, "cat": cat, "file_path": file_path, "is_chat": is_chat})

    # Auto-link chats to journals
    for vi in vault_files_info:
        if vi["is_chat"]:
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', vi["file"])
            if date_match:
                target = f"vault:journal/{date_match.group(1)}.md"
                add_link(vi["node_id"], target, 0.8)

    # Parse wikilinks in vault files
    for vi in vault_files_info:
        try:
            with open(vi["file_path"], "r", encoding="utf-8") as f:
                content = f.read()
            matches = link_pattern.findall(content)
            for match in matches:
                mc = match.strip()
                if "/" in mc:
                    target_id = f"vault:{mc}.md"
                elif mc.startswith(("journal/", "strategies/", "trades/")):
                    target_id = f"vault:{mc}.md"
                elif len(mc.split("-")) >= 2:
                    target_id = f"vault:trades/{mc}.md"
                else:
                    target_id = f"vault:journal/{mc}.md"
                add_link(vi["node_id"], target_id, 0.5)
        except Exception:
            pass

    # ═══════════════════════════════════════════
    # 7. SYSTEM LINKS (relationships)
    # ═══════════════════════════════════════════

    # Agent → Core
    add_link("agent:captain", "core:fastapi", 0.6)
    add_link("agent:hermes", "core:deepseek", 0.7)
    add_link("agent:hermes", "core:firebase", 0.5)
    add_link("agent:execution_auditor", "core:okx", 0.8)

    # Agent → Service
    add_link("agent:captain", "svc:signal_generator", 0.9)
    add_link("agent:captain", "svc:bankroll_manager", 0.7)
    add_link("agent:flash", "svc:order_projection", 0.9)
    add_link("agent:bankroll_guardian", "svc:bankroll_manager", 0.8)
    add_link("agent:slot_operator", "agent:flash", 0.7)
    add_link("agent:fleet_audit", "svc:database_service", 0.6)
    add_link("agent:quartermaster", "agent:captain", 0.5)
    add_link("agent:hermes", "svc:firebase_service", 0.6)
    add_link("agent:hermes", "svc:websocket_service", 0.5)
    add_link("agent:ai_service", "core:deepseek", 0.8)
    add_link("agent:macro_analyst", "svc:okx_rest", 0.6)
    add_link("agent:whale_tracker", "svc:okx_ws", 0.7)
    add_link("agent:onchain_watcher", "core:okx", 0.5)
    add_link("agent:librarian", "svc:okx_rest", 0.6)
    add_link("agent:librarian", "svc:database_service", 0.5)
    add_link("agent:sandbox_service", "svc:sandbox_swing", 0.9)
    add_link("agent:sandbox_service", "svc:sandbox_scalping", 0.9)
    add_link("agent:sandbox_service", "svc:okx_ws_public", 0.7)
    add_link("agent:execution_auditor", "svc:bankroll_manager", 0.6)
    add_link("agent:trade_analyst", "svc:database_service", 0.5)

    # Agent → Agent (consensus, dependencies)
    add_link("agent:captain", "agent:oracle", 0.8)
    add_link("agent:captain", "agent:macro_analyst", 0.6)
    add_link("agent:captain", "agent:whale_tracker", 0.7)
    add_link("agent:captain", "agent:onchain_watcher", 0.6)
    add_link("agent:bankroll_guardian", "agent:captain", 0.7)

    # Strategy → Service
    add_link("strat:velocity_flow", "svc:signal_generator", 0.8)
    add_link("strat:alpha_shield", "svc:signal_generator", 0.8)
    add_link("strat:decor_shadow", "svc:signal_generator", 0.8)
    add_link("strat:vwap_sniper", "svc:sandbox_scalping", 0.9)

    # Strategy → Agent
    add_link("strat:velocity_flow", "agent:captain", 0.6)
    add_link("strat:alpha_shield", "agent:captain", 0.6)
    add_link("strat:decor_shadow", "agent:captain", 0.6)

    # Service → Core
    add_link("svc:signal_generator", "core:okx", 0.7)
    add_link("svc:bankroll_manager", "core:okx", 0.8)
    add_link("svc:okx_rest", "core:okx", 0.9)
    add_link("svc:okx_ws", "core:okx", 0.9)
    add_link("svc:okx_ws_public", "core:okx", 0.8)
    add_link("svc:database_service", "core:postgresql", 0.9)
    add_link("svc:firebase_service", "core:firebase", 0.9)
    add_link("svc:websocket_service", "core:fastapi", 0.7)
    add_link("svc:galaxy_memory", "core:fastapi", 0.5)
    add_link("svc:galaxy_memory", "agent:hermes", 0.6)
    add_link("svc:whisper_svc", "core:whisper", 0.9)
    add_link("svc:telegram", "core:fastapi", 0.4)
    add_link("svc:phase_detector", "svc:signal_generator", 0.7)

    # Strategy internal links
    add_link("strat:velocity_flow", "strat:mola", 0.4)
    add_link("strat:alpha_shield", "strat:dvap", 0.5)
    add_link("strat:alpha_shield", "strat:fas", 0.5)
    add_link("strat:alpha_shield", "strat:lrt", 0.4)
    add_link("strat:decor_shadow", "strat:decor_hunter", 0.6)

    # UI → Service/Agent
    add_link("ui:cockpit", "svc:websocket_service", 0.6)
    add_link("ui:cockpit", "agent:captain", 0.5)
    add_link("ui:sandbox", "agent:sandbox_service", 0.8)
    add_link("ui:memory", "svc:galaxy_memory", 0.9)
    add_link("ui:memory", "agent:hermes", 0.5)
    add_link("ui:neural_chat", "agent:hermes", 0.7)
    add_link("ui:neural_chat", "agent:jarvis", 0.6)
    add_link("ui:observatory", "agent:librarian", 0.6)

    # Vault → Strategy/Agent
    for vi in vault_files_info:
        if vi["cat"] == "strategies":
            # Link strategy vault files to their strategy nodes
            strat_name = vi["file"].replace(".md", "").lower()
            for sid, slabel, _, _ in strats:
                if strat_name in sid.split(":")[1] or sid.split(":")[1] in strat_name:
                    add_link(vi["node_id"], sid, 0.7)
                    break

    # ═══════════════════════════════════════════
    # 8. CLEANUP: Remove phantom link targets
    # ═══════════════════════════════════════════
    final_links = [l for l in links if l["target"] in node_ids or any(n["id"] == l["target"] for n in nodes)]

    return {"nodes": nodes, "links": final_links}

@router.get("/file")
async def get_galaxy_file(category: str, filename: str):
    if ".." in filename or ".." in category:
        raise HTTPException(status_code=400, detail="Caminho inválido.")
        
    file_path = VAULT_DIR / category / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"filename": filename, "category": category, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
