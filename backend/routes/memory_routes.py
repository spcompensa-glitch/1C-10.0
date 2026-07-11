import os
import re
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
    
    for cat in categories:
        cat_path = VAULT_DIR / cat
        if not cat_path.exists():
            continue
            
        for root, _, files in os.walk(cat_path):
            for file in files:
                if not file.endswith(".md"):
                    continue
                
                rel_path = Path(root).relative_to(VAULT_DIR)
                node_id = f"{rel_path}/{file}".replace("\\", "/")
                
                if node_id not in node_ids:
                    nodes.append({
                        "id": node_id,
                        "label": file.replace(".md", ""),
                        "category": cat,
                        "val": 4 if cat == "journal" else (3 if cat == "strategies" else 2)
                    })
                    node_ids.add(node_id)
                
                file_path = Path(root) / file
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        
                    matches = link_pattern.findall(content)
                    for match in matches:
                        match_cleaned = match.strip()
                        target_id = None
                        if "/" in match_cleaned:
                            target_id = f"{match_cleaned}.md"
                        else:
                            if match_cleaned.startswith("journal/"):
                                target_id = f"{match_cleaned}.md"
                            elif match_cleaned.startswith("strategies/"):
                                target_id = f"{match_cleaned}.md"
                            elif match_cleaned.startswith("trades/"):
                                target_id = f"{match_cleaned}.md"
                            else:
                                if len(match_cleaned.split("-")) >= 2:
                                    target_id = f"trades/{match_cleaned}.md"
                                else:
                                    target_id = f"journal/{match_cleaned}.md"
                        
                        if target_id:
                            links.append({
                                "source": node_id,
                                "target": target_id
                            })
                except Exception:
                    pass
                    
    for link in links:
        target = link["target"]
        if target not in node_ids:
            cat = target.split("/")[0] if "/" in target else "journal"
            label = target.split("/")[-1].replace(".md", "") if "/" in target else target.replace(".md", "")
            nodes.append({
                "id": target,
                "label": label,
                "category": cat,
                "val": 2
            })
            node_ids.add(target)
            
    return {"nodes": nodes, "links": links}

@router.get("/files")
async def list_galaxy_files():
    result = {
        "journal": [],
        "trades": [],
        "strategies": [],
        "vault_path": str(VAULT_DIR)
    }
    for cat in ["journal", "trades", "strategies"]:
        cat_path = VAULT_DIR / cat
        if cat_path.exists():
            files = sorted([f for f in os.listdir(cat_path) if f.endswith(".md")], reverse=True)
            result[cat] = files
    return result

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
