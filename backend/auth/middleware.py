#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Middleware de Autenticação e Autorização
========================================

Middleware para proteção de rotas e controle de acesso.

Author: Sistema 1Crypten
Version: 1.0
"""

import os
import logging
import functools
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.responses import JSONResponse
from sqlalchemy.orm import Session
import time

from .jwt_handler import get_jwt_manager, verify_user_token
from .permissions import validate_user_access, get_user_role_from_database
from database.models_auth import User, UserSession
from database.database_service_secure import get_db

logger = logging.getLogger(__name__)

# Instância de segurança
security = HTTPBearer(auto_error=False)

class AuthenticationError(Exception):
    """Exceção de autenticação"""
    pass

class AuthorizationError(Exception):
    """Exceção de autorização"""
    pass

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[Dict[str, Any]]:
    """
    Obtém usuário atual a partir do token JWT
    
    Args:
        credentials: Credenciais de autorização
        db: Sessão do banco de dados
        
    Returns:
        Dados do usuário se autenticado
    """
    try:
        # Se não houver credenciais, retornar None (para rotas públicas)
        if not credentials:
            return None
        
        # Verificar token JWT
        token = credentials.credentials
        jwt_manager = get_jwt_manager()
        payload = jwt_manager.verify_token(token, "access")
        
        if not payload:
            raise AuthenticationError("Token inválido ou expirado")
        
        # Obter dados do usuário do banco
        username = payload.get("sub")
        if not username:
            raise AuthenticationError("Token sem username")
        
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise AuthenticationError("Usuário não encontrado")
        
        if not user.is_active:
            raise AuthenticationError("Usuário inativo")
        
        # Atualizar último login
        from datetime import datetime as dt
        user.last_login = dt.utcnow()
        db.commit()
        
        # Retornar dados do usuário
        user_data = user.to_dict()
        user_data['token_payload'] = payload
        user_data['session_data'] = {
            'ip_address': _get_client_ip(credentials),
            'user_agent': _get_user_agent(credentials),
            'login_time': datetime.utcnow().isoformat()
        }
        
        return user_data
        
    except AuthenticationError as e:
        logger.warning(f"Autenticação falhou: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Erro na autenticação: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Erro na autenticação",
            headers={"WWW-Authenticate": "Bearer"},
        )

def require_permission(permission: str):
    """
    FastAPI dependency factory que exige permissão específica.

    Uso:
        @router.get(...)
        async def minha_rota(current_user: dict = Depends(require_permission("users"))):
            ...

    Args:
        permission: Permissão necessária
    """
    def _checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário não autenticado",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not _user_has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permissão negada: {permission} requerida"
            )
        return current_user
    return _checker


def require_admin():
    """
    FastAPI dependency factory que exige role admin.

    Uso:
        @router.get("/users", dependencies=[Depends(require_admin())])
        async def list_users(...): ...

        OU

        @router.get("/users")
        async def list_users(current_user: dict = Depends(require_admin())):
            ...
    """
    def _checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário não autenticado",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if current_user.get('role') != 'admin':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso administrativo requerido"
            )
        return current_user
    return _checker

def authenticate_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[Dict[str, Any]]:
    """
    Autenticação opcional - retorna None se não autenticado
    
    Args:
        credentials: Credenciais de autorização
        db: Sessão do banco de dados
        
    Returns:
        Dados do usuário se autenticado, None caso contrário
    """
    try:
        if credentials:
            return get_current_user(credentials, db)
        return None
    except Exception:
        return None

def _user_has_permission(user_data: Dict[str, Any], permission: str) -> bool:
    """
    Verifica se usuário tem permissão específica
    
    Args:
        user_data: Dados do usuário
        permission: Permissão a ser verificada
        
    Returns:
        True se usuário tem permissão
    """
    user_role = user_data.get('role', 'user')
    return permission in user_data.get('permissions', [])

def _get_client_ip(credentials: HTTPAuthorizationCredentials) -> str:
    """Obtém IP do cliente"""
    try:
        # Em uma implementação real, obter do request
        return "unknown"
    except Exception:
        return "unknown"

def _get_user_agent(credentials: HTTPAuthorizationCredentials) -> str:
    """Obtém user agent"""
    try:
        # Em uma implementação real, obter do request
        return "unknown"
    except Exception:
        return "unknown"

def audit_log(action: str, resource: str = None, details: Dict[str, Any] = None):
    """
    Decorator para registrar logs de auditoria
    
    Args:
        action: Ação realizada
        resource: Recurso acessado
        details: Detalhes adicionais
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Obter usuário atual
            current_user = kwargs.get('current_user')
            user_id = current_user.get('id') if current_user else None
            
            # Registrar início da ação
            start_time = time.time()
            logger.info(f"Ação iniciada: {action} por usuário {user_id}")
            
            try:
                # Executar função original
                result = await func(*args, **kwargs)
                
                # Registrar sucesso
                execution_time = time.time() - start_time
                logger.info(f"Ação concluída: {action} por usuário {user_id} em {execution_time:.2f}s")
                
                return result
                
            except Exception as e:
                # Registrar falha
                execution_time = time.time() - start_time
                logger.error(f"Ação falhou: {action} por usuário {user_id} em {execution_time:.2f}s - {str(e)}")
                raise
                
        return wrapper
    return decorator

def _create_audit_log(
    user_id: Optional[int],
    action: str,
    resource: Optional[str],
    details: Dict[str, Any],
    success: bool
):
    """
    Cria registro de auditoria
    
    Args:
        user_id: ID do usuário
        action: Ação realizada
        resource: Recurso acessado
        details: Detalhes da ação
        success: Sucesso da ação
    """
    try:
        # Criar log de auditoria
        audit_data = {
            'user_id': user_id,
            'action': action,
            'resource': resource,
            'details': details,
            'success': success,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Em uma implementação real, salvar no banco de dados
        logger.info(f"Log de auditoria: {audit_data}")
        
    except Exception as e:
        logger.error(f"Erro ao criar log de auditoria: {e}")

# Funções utilitárias para rotas
def create_rate_limit_key(user_id: str, endpoint: str) -> str:
    """Cria chave para rate limiting"""
    return f"rate_limit:{user_id}:{endpoint}"

def is_rate_limited(user_id: str, endpoint: str, max_requests: int = 100, window: int = 3600) -> bool:
    """
    Verifica se usuário está rate limited
    
    Args:
        user_id: ID do usuário
        endpoint: Endpoint acessado
        max_requests: Máximo de requisições
        window: Janela de tempo em segundos
        
    Returns:
        True se estiver rate limited
    """
    try:
        # Em uma implementação real, usar Redis
        import time
        key = create_rate_limit_key(user_id, endpoint)
        current_time = time.time()
        
        # Simulação - em produção usar Redis com zadd
        return False
        
    except Exception as e:
        logger.error(f"Erro no rate limiting: {e}")
        return False

# Exceções personalizadas
class RateLimitError(HTTPException):
    """Exceção de rate limiting"""
    def __init__(self, detail: str = "Limite de requisições excedido"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": "60"}
        )

# Middleware global - será aplicado no auth_main.py
def add_security_headers_middleware(app):
    """
    Aplica middleware de segurança global
    """
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        """Adiciona headers de segurança"""
        response = await call_next(request)

        # Adicionar headers de segurança
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
    
    return add_security_headers

# Handler de exceções global - será aplicado no auth_main.py
def setup_exception_handlers(app):
    """
    Configura handlers de exceção globais
    """
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Manipulador global de exceções"""
        logger.error(f"Erro não tratado: {exc}")

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Erro interno do servidor"},
        )
    
    return global_exception_handler

# Função principal de setup de middlewares
def setup_middleware(app):
    """
    Configura todos os middlewares da aplicação
    """
    # Aplica middleware de segurança
    add_security_headers_middleware(app)
    
    # Configura handlers de exceção
    setup_exception_handlers(app)
    
    logger.info("Middlewares configurados com sucesso")