#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rotas de Gerenciamento de Tokens OKX
=====================================

Endpoints para gerenciamento de tokens OKX criptografados.
Versão 2.0 — Suporte a chaves reais OKX (formato UUID), teste em tempo real.

Author: Sistema 1Crypten
Version: 2.0
"""

import logging
import hmac
import hashlib
import base64
import httpx
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session

from auth.middleware import get_current_user, audit_log
from database.models_auth import UserOKXTokens
from database.database_service_secure import get_db
from security.encryption import get_encryption_instance, get_data_masker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["tokens"])

# ---------------------------------------------------------------------------
# Modelos de request/response
# ---------------------------------------------------------------------------

class OKXTokenRequest(BaseModel):
    """Request de token OKX — aceita formato real da OKX (UUID com hífens)"""
    api_key: str
    secret_key: str
    passphrase: Optional[str] = None

    @validator('api_key')
    def validate_api_key(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('API Key não pode ser vazia')
        # Formato UUID OKX: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx (36 chars)
        # Ou formato legado: 32 chars alfanuméricos
        clean = v.replace('-', '')
        if len(clean) < 16:
            raise ValueError('API Key OKX muito curta (mínimo 16 caracteres)')
        return v

    @validator('secret_key')
    def validate_secret_key(cls, v):
        v = v.strip()
        if not v or len(v) < 10:
            raise ValueError('Secret Key OKX inválida (mínimo 10 caracteres)')
        return v

    @validator('passphrase')
    def validate_passphrase(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v


class OKXTokenTestRequest(BaseModel):
    """Request para testar credenciais ANTES de salvar"""
    api_key: str
    secret_key: str
    passphrase: Optional[str] = None


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
    tokens: list
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

encryption = get_encryption_instance()
data_masker = get_data_masker()

OKX_BASE_URL = "https://www.okx.com"

def _build_okx_signature(timestamp: str, method: str, path: str, body: str, secret_key: str) -> str:
    """Gera assinatura HMAC-SHA256 para a OKX API (modo REAL)"""
    prehash = timestamp + method.upper() + path + body
    mac = hmac.new(
        secret_key.encode('utf-8'),
        prehash.encode('utf-8'),
        hashlib.sha256
    )
    return base64.b64encode(mac.digest()).decode()


def _okx_headers(api_key: str, secret_key: str, passphrase: str) -> dict:
    """Monta os headers de autenticação da OKX API"""
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    path = '/api/v5/account/balance'
    signature = _build_okx_signature(ts, 'GET', path, '', secret_key)
    return {
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': ts,
        'OK-ACCESS-PASSPHRASE': passphrase or '',
        'Content-Type': 'application/json',
        # SEM x-simulated-trading — modo REAL apenas
    }


async def _test_okx_credentials(api_key: str, secret_key: str, passphrase: Optional[str]) -> dict:
    """
    Faz chamada real à OKX API para testar as credenciais.
    Retorna saldo ou erro.
    """
    headers = _okx_headers(api_key.strip(), secret_key.strip(), (passphrase or '').strip())
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{OKX_BASE_URL}/api/v5/account/balance",
                headers=headers
            )
        data = resp.json()
        if data.get('code') == '0':
            # Extrair saldo USDT
            details = data.get('data', [{}])
            total_equity = '0'
            usdt_balance = '0'
            if details:
                total_equity = details[0].get('totalEq', '0')
                for asset in details[0].get('details', []):
                    if asset.get('ccy') == 'USDT':
                        usdt_balance = asset.get('availBal', '0')
                        break
            return {
                'success': True,
                'total_equity_usd': float(total_equity),
                'usdt_available': float(usdt_balance),
                'message': 'Conexão com OKX bem-sucedida ✅'
            }
        else:
            msg = data.get('msg', 'Erro desconhecido')
            code = data.get('code', '?')
            return {
                'success': False,
                'message': f'OKX rejeitou as credenciais — Código {code}: {msg}'
            }
    except httpx.TimeoutException:
        return {'success': False, 'message': 'Timeout ao conectar com a OKX'}
    except Exception as e:
        logger.error(f"Erro no teste de credenciais OKX: {e}")
        return {'success': False, 'message': f'Erro de conexão: {str(e)}'}


def _get_client_ip(request: Request) -> str:
    try:
        return request.client.host
    except Exception:
        return "unknown"


def _get_user_agent(request: Request) -> str:
    try:
        return request.headers.get("user-agent", "unknown")
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/okx-tokens/test-live")
async def test_okx_credentials_live(
    token_data: OKXTokenTestRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    [REAL] Testa credenciais OKX em tempo real ANTES de salvar.
    Faz uma chamada real à OKX API (/api/v5/account/balance).
    Não persiste nada no banco.
    """
    result = await _test_okx_credentials(
        api_key=token_data.api_key,
        secret_key=token_data.secret_key,
        passphrase=token_data.passphrase
    )
    if result['success']:
        return result
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result['message']
        )


@router.get("/okx-tokens/status")
async def get_okx_tokens_status(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retorna status rápido das credenciais OKX do usuário.
    Mostra API Key mascarada e se está ativa — sem expor dados sensíveis.
    """
    try:
        token = db.query(UserOKXTokens).filter(
            UserOKXTokens.user_id == current_user['id'],
            UserOKXTokens.is_active == True
        ).order_by(UserOKXTokens.updated_at.desc()).first()

        if not token:
            return {
                'configured': False,
                'message': 'Nenhuma credencial OKX configurada',
                'masked_api_key': None,
                'updated_at': None
            }

        decrypted_key = encryption.decrypt_token(token.api_key_encrypted)
        return {
            'configured': True,
            'message': 'Credencial OKX ativa',
            'masked_api_key': data_masker.mask_api_key(decrypted_key),
            'token_id': token.id,
            'updated_at': token.updated_at.isoformat() if token.updated_at else None
        }
    except Exception as e:
        logger.error(f"Erro ao verificar status OKX para user {current_user.get('id')}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao verificar status das credenciais"
        )


@router.get("/okx-tokens")
async def get_okx_tokens(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtém tokens OKX do usuário com API keys mascaradas"""
    try:
        tokens = db.query(UserOKXTokens).filter(
            UserOKXTokens.user_id == current_user['id'],
            UserOKXTokens.is_active == True
        ).all()

        result = []
        for token in tokens:
            decrypted_key = encryption.decrypt_token(token.api_key_encrypted)
            result.append({
                'id': token.id,
                'exchange_name': token.exchange_name,
                'is_active': token.is_active,
                'masked_api_key': data_masker.mask_api_key(decrypted_key),
                'created_at': token.created_at.isoformat() if token.created_at else None,
                'updated_at': token.updated_at.isoformat() if token.updated_at else None,
            })

        return {'tokens': result, 'total': len(result)}
    except Exception as e:
        logger.error(f"Erro ao buscar tokens OKX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar tokens OKX"
        )


@router.post("/okx-tokens")
async def create_okx_token(
    request: Request,
    token_data: OKXTokenRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Salva credenciais OKX criptografadas para o usuário.
    Faz teste em tempo real antes de persistir.
    Se o usuário já tiver credenciais ativas, desativa as antigas.
    """
    try:
        # 1. Testar credenciais em tempo real antes de salvar
        test_result = await _test_okx_credentials(
            api_key=token_data.api_key,
            secret_key=token_data.secret_key,
            passphrase=token_data.passphrase
        )
        if not test_result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Credenciais inválidas: {test_result['message']}"
            )

        # 2. Desativar tokens anteriores do usuário
        db.query(UserOKXTokens).filter(
            UserOKXTokens.user_id == current_user['id'],
            UserOKXTokens.is_active == True
        ).update({'is_active': False, 'updated_at': datetime.utcnow()})

        # 3. Criptografar e persistir
        encrypted_api_key = encryption.encrypt_token(token_data.api_key.strip())
        encrypted_secret_key = encryption.encrypt_token(token_data.secret_key.strip())
        encrypted_passphrase = (
            encryption.encrypt_token(token_data.passphrase.strip())
            if token_data.passphrase and token_data.passphrase.strip()
            else None
        )

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

        logger.info(f"Credenciais OKX salvas para usuário: {current_user.get('username')} | "
                    f"Saldo: ${test_result.get('total_equity_usd', 0):.2f}")

        return {
            'success': True,
            'message': 'Credenciais OKX salvas com sucesso',
            'masked_api_key': data_masker.mask_api_key(token_data.api_key),
            'token_id': new_token.id,
            'total_equity_usd': test_result.get('total_equity_usd'),
            'usdt_available': test_result.get('usdt_available'),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao salvar credenciais OKX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao salvar credenciais OKX"
        )


@router.put("/okx-tokens/{token_id}")
async def update_okx_token(
    token_id: int,
    request: Request,
    token_data: OKXTokenRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Atualiza credenciais OKX existentes (com teste em tempo real)"""
    try:
        token = db.query(UserOKXTokens).filter(
            UserOKXTokens.id == token_id,
            UserOKXTokens.user_id == current_user['id']
        ).first()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token não encontrado"
            )

        # Testar antes de atualizar
        test_result = await _test_okx_credentials(
            api_key=token_data.api_key,
            secret_key=token_data.secret_key,
            passphrase=token_data.passphrase
        )
        if not test_result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Credenciais inválidas: {test_result['message']}"
            )

        token.api_key_encrypted = encryption.encrypt_token(token_data.api_key.strip())
        token.secret_key_encrypted = encryption.encrypt_token(token_data.secret_key.strip())
        token.passphrase_encrypted = (
            encryption.encrypt_token(token_data.passphrase.strip())
            if token_data.passphrase and token_data.passphrase.strip()
            else None
        )
        token.updated_at = datetime.utcnow()

        db.commit()

        return {
            'success': True,
            'message': 'Credenciais OKX atualizadas com sucesso',
            'masked_api_key': data_masker.mask_api_key(token_data.api_key),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao atualizar token OKX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao atualizar token OKX"
        )


@router.delete("/okx-tokens/{token_id}")
async def delete_okx_token(
    token_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove credenciais OKX do usuário"""
    try:
        token = db.query(UserOKXTokens).filter(
            UserOKXTokens.id == token_id,
            UserOKXTokens.user_id == current_user['id']
        ).first()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token não encontrado"
            )

        db.delete(token)
        db.commit()

        logger.info(f"Credenciais OKX removidas para usuário: {current_user.get('username')}")
        return {'success': True, 'message': 'Credenciais OKX removidas com sucesso'}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao deletar token OKX: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao deletar token OKX"
        )