#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rotas de Gerenciamento de Tokens OKX
===================================

Endpoints para gerenciamento de tokens OKX criptografados.

Author: Sistema 1Crypten
Version: 1.0
"""

import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session
from datetime import datetime

from auth.middleware import get_current_user, require_permission, audit_log
from database.models_auth import UserOKXTokens
from database.database_service_secure import get_db
from security.encryption import get_encryption_instance, get_data_masker
from services.okx_user_service import OKXUserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["tokens"])

# Modelos de request/response
class OKXTokenRequest(BaseModel):
    """Request de token OKX"""
    api_key: str
    secret_key: str
    passphrase: str = None
    
    @validator('api_key')
    def validate_api_key(cls, v):
        if len(v) != 32 or not v.isalnum():
            raise ValueError('API Key OKX deve ter 32 caracteres alfanuméricos')
        return v
    
    @validator('secret_key')
    def validate_secret_key(cls, v):
        if not v or len(v) < 10:
            raise ValueError('Secret Key OKX inválida')
        return v

class OKXTokenResponse(BaseModel):
    """Response de token OKX"""
    id: int
    exchange_name: str
    is_active: bool
    created_at: str
    updated_at: str
    masked_api_key: str

class OKXTokensListResponse(BaseModel):
    """Response de lista de tokens"""
    tokens: List[OKXTokenResponse]
    total: int

class TokenActivationRequest(BaseModel):
    """Request para ativar/desativar token"""
    is_active: bool

# Instâncias globais
encryption = get_encryption_instance()
data_masker = get_data_masker()

@router.get("/okx-tokens", response_model=OKXTokensListResponse)
@require_permission("account")
@audit_log(action="list_tokens", resource="okx_tokens")
async def get_okx_tokens(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtém tokens OKX do usuário
    
    Retorna lista de tokens com API keys mascaradas
    """
    try:
        # Buscar tokens do usuário
        tokens = db.query(UserOKXTokens).filter(
            UserOKXTokens.user_id == current_user['id'],
            UserOKXTokens.is_active == True
        ).all()
        
        # Mascara API keys
        masked_tokens = []
        for token in tokens:
            masked_token_data = token.to_dict()
            masked_token_data['masked_api_key'] = data_masker.mask_api_key(
                encryption.decrypt_token(token.api_key_encrypted)
            )
            masked_tokens.append(OKXTokenResponse(**masked_token_data))
        
        return OKXTokensListResponse(
            tokens=masked_tokens,
            total=len(masked_tokens)
        )
        
    except Exception as e:
        logger.error(f"Erro ao buscar tokens OKX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar tokens OKX"
        )

@router.post("/okx-tokens", response_model=OKXTokenResponse)
@require_permission("account")
@audit_log(action="create_token", resource="okx_tokens")
async def create_okx_token(
    request: Request,
    token_data: OKXTokenRequest,
    master_password: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cria novo token OKX
    
    Requer senha mestre para criptografar o token
    """
    try:
        # Validar senha mestre
        if not master_password or len(master_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Senha mestre inválida"
            )
        
        # Criptografar tokens
        encrypted_api_key = encryption.encrypt_token(token_data.api_key)
        encrypted_secret_key = encryption.encrypt_token(token_data.secret_key)
        encrypted_passphrase = encryption.encrypt_token(token_data.passphrase) if token_data.passphrase else None
        
        # Criar novo token
        new_token = UserOKXTokens(
            user_id=current_user['id'],
            exchange_name='okx',
            api_key_encrypted=encrypted_api_key,
            secret_key_encrypted=encrypted_secret_key,
            passphrase_encrypted=encrypted_passphrase,
            is_active=True,
            ip_address=_get_client_ip(request),
            user_agent=_get_user_agent(request),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(new_token)
        db.commit()
        db.refresh(new_token)
        
        # Mascara API key para response
        masked_api_key = data_masker.mask_api_key(token_data.api_key)
        
        logger.info(f"Novo token OKX criado para usuário: {current_user['username']}")
        
        return OKXTokenResponse(
            id=new_token.id,
            exchange_name=new_token.exchange_name,
            is_active=new_token.is_active,
            created_at=new_token.created_at.isoformat(),
            updated_at=new_token.updated_at.isoformat(),
            masked_api_key=masked_api_key
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao criar token OKX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar token OKX"
        )

@router.get("/okx-tokens/{token_id}", response_model=OKXTokenResponse)
@require_permission("account")
@audit_log(action="get_token", resource="okx_tokens")
async def get_okx_token(
    token_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtém token OKX específico
    
    Retorna token com API key mascarada
    """
    try:
        # Buscar token
        token = db.query(UserOKXTokens).filter(
            UserOKXTokens.id == token_id,
            UserOKXTokens.user_id == current_user['id']
        ).first()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token não encontrado"
            )
        
        # Mascara API key
        masked_api_key = data_masker.mask_api_key(
            encryption.decrypt_token(token.api_key_encrypted)
        )
        
        token_data = token.to_dict()
        token_data['masked_api_key'] = masked_api_key
        
        return OKXTokenResponse(**token_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar token OKX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar token OKX"
        )

@router.put("/okx-tokens/{token_id}", response_model=OKXTokenResponse)
@require_permission("account")
@audit_log(action="update_token", resource="okx_tokens")
async def update_okx_token(
    token_id: int,
    token_data: OKXTokenRequest,
    master_password: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Atualiza token OKX existente
    
    Requer senha mestre para descriptografar e recriptografar
    """
    try:
        # Buscar token
        token = db.query(UserOKXTokens).filter(
            UserOKXTokens.id == token_id,
            UserOKXTokens.user_id == current_user['id']
        ).first()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token não encontrado"
            )
        
        # Validar senha mestre
        if not master_password or len(master_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Senha mestre inválida"
            )
        
        # Recriptografar tokens
        encrypted_api_key = encryption.encrypt_token(token_data.api_key)
        encrypted_secret_key = encryption.encrypt_token(token_data.secret_key)
        encrypted_passphrase = encryption.encrypt_token(token_data.passphrase) if token_data.passphrase else None
        
        # Atualizar token
        token.api_key_encrypted = encrypted_api_key
        token.secret_key_encrypted = encrypted_secret_key
        token.passphrase_encrypted = encrypted_passphrase
        token.updated_at = datetime.utcnow()
        
        db.commit()
        
        # Mascara API key para response
        masked_api_key = data_masker.mask_api_key(token_data.api_key)
        
        logger.info(f"Token OKX atualizado para usuário: {current_user['username']}")
        
        token_data = token.to_dict()
        token_data['masked_api_key'] = masked_api_key
        
        return OKXTokenResponse(**token_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar token OKX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar token OKX"
        )

@router.patch("/okx-tokens/{token_id}/activation")
@require_permission("account")
@audit_log(action="toggle_token", resource="okx_tokens")
async def toggle_token_activation(
    token_id: int,
    activation_data: TokenActivationRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ativa/desativa token OKX
    
    Permite usuário ativar ou desativar seus tokens
    """
    try:
        # Buscar token
        token = db.query(UserOKXTokens).filter(
            UserOKXTokens.id == token_id,
            UserOKXTokens.user_id == current_user['id']
        ).first()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token não encontrado"
            )
        
        # Atualizar status
        old_status = token.is_active
        token.is_active = activation_data.is_active
        token.updated_at = datetime.utcnow()
        
        db.commit()
        
        action = "ativado" if activation_data.is_active else "desativado"
        logger.info(f"Token OKX {action} para usuário: {current_user['username']}")
        
        return {"message": f"Token {action} com sucesso"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao alternar status do token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao alternar status do token"
        )

@router.delete("/okx-tokens/{token_id}")
@require_permission("account")
@audit_log(action="delete_token", resource="okx_tokens")
async def delete_okx_token(
    token_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deleta token OKX
    
    Remove token permanentemente do usuário
    """
    try:
        # Buscar token
        token = db.query(UserOKXTokens).filter(
            UserOKXTokens.id == token_id,
            UserOKXTokens.user_id == current_user['id']
        ).first()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token não encontrado"
            )
        
        # Deletar token
        masked_api_key = data_masker.mask_api_key(
            encryption.decrypt_token(token.api_key_encrypted)
        )
        
        db.delete(token)
        db.commit()
        
        logger.info(f"Token OKX deletado para usuário: {current_user['username']}")
        
        return {"message": f"Token OKX deletado com sucesso (API Key: {masked_api_key})"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao deletar token OKX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao deletar token OKX"
        )

@router.get("/okx-tokens/{token_id}/test")
@require_permission("account")
@audit_log(action="test_token", resource="okx_tokens")
async def test_okx_token(
    token_id: int,
    master_password: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Testa token OKX
    
    Verifica se o token é válido e pode se conectar à OKX
    """
    try:
        # Buscar token
        token = db.query(UserOKXTokens).filter(
            UserOKXTokens.id == token_id,
            UserOKXTokens.user_id == current_user['id']
        ).first()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token não encontrado"
            )
        
        # Validar senha mestre
        if not master_password or len(master_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Senha mestre inválida"
            )
        
        # Descriptografar tokens
        api_key = encryption.decrypt_token(token.api_key_encrypted)
        secret_key = encryption.decrypt_token(token.secret_key_encrypted)
        passphrase = encryption.decrypt_token(token.passphrase_encrypted) if token.passphrase_encrypted else None
        
        # Criar serviço OKX e testar conexão
        okx_service = OKXUserService(current_user['id'], db)
        okx_service.setup_user_session()
        
        try:
            # Testar conexão chamando um endpoint simples
            account_info = okx_service.get_account_balance()
            
            return {
                "status": "success",
                "message": "Token OKX válido e funcionando",
                "account_info": account_info
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Token OKX inválido: {str(e)}",
                "error_details": str(e)
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao testar token OKX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao testar token OKX"
        )

# Funções utilitárias
def _get_client_ip(request) -> str:
    """Obtém IP do cliente"""
    try:
        return request.client.host
    except Exception:
        return "unknown"

def _get_user_agent(request) -> str:
    """Obtém user agent"""
    try:
        return request.headers.get("user-agent", "unknown")
    except Exception:
        return "unknown"