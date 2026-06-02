# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from services.auth_service import get_current_user, User
from services.firebase_service import firebase_service
import time
import asyncio

router = APIRouter(prefix="/api/vault", tags=["Vault"])

class VaultSaveRequest(BaseModel):
    encrypted_key: str
    encrypted_secret: str
    hint: str = "AES-256"

@router.post("/save")
async def save_vault(req: VaultSaveRequest, current_user: User = Depends(get_current_user)):
    """Salva os blobs criptografados no documento do usuário no Firestore"""
    if not firebase_service.is_active:
        await firebase_service.initialize()
        
    try:
        vault_data = {
            "okx_vault": {
                "key": req.encrypted_key,
                "secret": req.encrypted_secret,
                "hint": req.hint,
                "updated_at": time.time()
            }
        }
        # Atualizamos o documento do usuário (handle @nome.10d)
        await asyncio.to_thread(
            firebase_service.db.collection("users").document(current_user.username).set, 
            vault_data, 
            merge=True
        )
        return {"status": "success", "message": "Cofre atualizado localmente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar no cofre: {str(e)}")

@router.get("/status")
async def get_vault_status(current_user: User = Depends(get_current_user)):
    """Verifica se o usuário já possui chaves configuradas"""
    try:
        user_doc = await asyncio.to_thread(
            firebase_service.db.collection("users").document(current_user.username).get
        )
        if user_doc.exists:
            data = user_doc.to_dict()
            has_vault = "okx_vault" in data
            return {
                "has_vault": has_vault,
                "updated_at": data.get("okx_vault", {}).get("updated_at") if has_vault else None
            }
        return {"has_vault": False}
    except Exception as e:
        return {"has_vault": False, "error": str(e)}
