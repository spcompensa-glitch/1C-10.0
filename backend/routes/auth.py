#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rotas de Autenticação e Autorização
===================================

Endpoints para login, registro, gerenciamento de tokens e usuários.

Author: Sistema 1Crypten
Version: 1.0
"""

import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session
import secrets
import string
from datetime import datetime

from ..auth.middleware import get_current_user, require_permission, require_admin, audit_log
from ..auth.jwt_handler import get_jwt_manager, create_user_tokens
from ..auth.permissions import PERMISSIONS
from ..auth.security.password_handler import hash_password, verify_password
from ..database.models_auth import User, UserOKXTokens, AuditLog
from ..database.database_service_secure import get_db
from ..security.encryption import get_password_hasher, get_security_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Modelos de request/response
class LoginRequest(BaseModel):
    """Request de login"""
    username: str
    password: str

class LoginResponse(BaseModel):
    """Response de login"""
    access_token: str
    refresh_token: str
    token_type: str
    user: Dict[str, Any]

class RegisterRequest(BaseModel):
    """Request de registro"""
    username: str
    email: Optional[str] = None
    password: str
    confirm_password: str

    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'password' in values and v != values['password']:
            raise ValueError('As senhas não coincidem')
        return v

class RegisterResponse(BaseModel):
    """Response de registro"""
    message: str
    user: Dict[str, Any]

class RefreshTokenRequest(BaseModel):
    """Request de refresh token"""
    refresh_token: str

class RefreshTokenResponse(BaseModel):
    """Response de refresh token"""
    access_token: str
    token_type: str

class PasswordChangeRequest(BaseModel):
    """Request de troca de senha"""
    current_password: str
    new_password: str
    confirm_new_password: str
    
    @validator('confirm_new_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('As novas senhas não coincidem')
        return v

class UserProfileResponse(BaseModel):
    """Response de perfil de usuário"""
    user: Dict[str, Any]

class UserListResponse(BaseModel):
    """Response de lista de usuários"""
    users: list
    total: int
    page: int
    per_page: int

# Instâncias globais
jwt_manager = get_jwt_manager()
password_hasher = get_password_hasher()
security_validator = get_security_validator()

@router.post("/login", response_model=LoginResponse)
@audit_log(action="login", resource="auth")
async def login(
    request: Request,
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Login de usuário
    
    Realiza login e retorna tokens JWT
    """
    try:
        # Verificar rate limiting
        client_ip = _get_client_ip(request)
        username = login_data.username
        
        # Buscar usuário no banco
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            logger.warning(f"Tentativa de login falha: usuário {username} não existe")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário ou senha inválidos"
            )
        
        if not user.is_active:
            logger.warning(f"Tentativa de login falha: usuário {username} inativo")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário inativo"
            )
        
        # Verificar senha
        if not verify_password(login_data.password, user.password_hash):
            logger.warning(f"Tentativa de login falha: senha incorreta para {username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário ou senha inválidos"
            )
        
        # Criar tokens
        user_data = {
            'sub': user.username,
            'role': user.role,
            'email': user.email,
            'user_id': user.id
        }
        
        tokens = create_user_tokens(user_data)
        
        # Registrar login bem sucedido
        logger.info(f"Login bem sucedido para usuário: {username}")
        
        # Registrar log de auditoria
        _create_audit_log(
            db=db,
            user_id=user.id,
            action="login",
            resource="auth",
            details={
                'username': username,
                'ip_address': client_ip,
                'user_agent': _get_user_agent(request),
                'success': True
            }
        )
        
        return LoginResponse(
            access_token=tokens['access_token'],
            refresh_token=tokens['refresh_token'],
            token_type=tokens['token_type'],
            user=user.to_dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno no login"
        )

@router.post("/register", response_model=RegisterResponse)
@audit_log(action="register", resource="auth")
async def register(
    request: Request,
    register_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Registro de novo usuário
    
    Cria novo usuário com role padrão (user)
    """
    try:
        # Validar força da senha
        password_validation = security_validator.validate_password_strength(register_data.password)
        if not password_validation['is_valid']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Senha fraca: {', '.join(password_validation['errors'])}"
            )
        
        # Verificar se username já existe
        existing_user = db.query(User).filter(User.username == register_data.username).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username já existe"
            )
        
        # Verificar se email já existe (se informado)
        if register_data.email:
            existing_email = db.query(User).filter(User.email == register_data.email).first()
            if existing_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email já existe"
                )
        
        # Criar hash da senha
        password_hash = hash_password(register_data.password)
        
        # Criar novo usuário
        new_user = User(
            username=register_data.username,
            email=register_data.email,
            password_hash=password_hash,
            role='user',  # Role padrão
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Registrar criação de usuário
        logger.info(f"Novo usuário criado: {register_data.username}")
        
        # Registrar log de auditoria
        _create_audit_log(
            db=db,
            user_id=new_user.id,
            action="register",
            resource="auth",
            details={
                'username': register_data.username,
                'email': register_data.email,
                'ip_address': _get_client_ip(request),
                'user_agent': _get_user_agent(request),
                'success': True
            }
        )
        
        return RegisterResponse(
            message="Usuário criado com sucesso",
            user=new_user.to_dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no registro: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno no registro"
        )

@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest
):
    """
    Refresh token
    
    Gera novo access token a partir do refresh token
    """
    try:
        # Refresh token
        new_access_token = jwt_manager.refresh_access_token(refresh_data.refresh_token)
        
        if not new_access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido"
            )
        
        return RefreshTokenResponse(
            access_token=new_access_token,
            token_type="bearer"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no refresh token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro no refresh token"
        )

@router.post("/logout")
@audit_log(action="logout", resource="auth")
async def logout(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Logout de usuário
    
    Invalida tokens do usuário
    """
    try:
        # Registrar logout
        logger.info(f"Logout realizado para usuário: {current_user['username']}")
        
        # Registrar log de auditoria
        _create_audit_log(
            db=db,
            user_id=current_user['id'],
            action="logout",
            resource="auth",
            details={
                'username': current_user['username'],
                'success': True
            }
        )
        
        return {"message": "Logout realizado com sucesso"}
        
    except Exception as e:
        logger.error(f"Erro no logout: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro no logout"
        )

@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Obtém perfil do usuário atual
    
    Retorna informações do usuário autenticado
    """
    try:
        return UserProfileResponse(user=current_user)
        
    except Exception as e:
        logger.error(f"Erro ao obter perfil: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter perfil"
        )

@router.post("/change-password")
@audit_log(action="change_password", resource="auth")
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Troca de senha
    
    Permite usuário trocar sua senha atual
    """
    try:
        # Validar força da nova senha
        password_validation = security_validator.validate_password_strength(password_data.new_password)
        if not password_validation['is_valid']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Senha fraca: {', '.join(password_validation['errors'])}"
            )
        
        # Verificar senha atual
        if not verify_password(password_data.current_password, current_user['password_hash']):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Senha atual incorreta"
            )
        
        # Atualizar senha
        new_password_hash = hash_password(password_data.new_password)
        user = db.query(User).filter(User.id == current_user['id']).first()
        user.password_hash = new_password_hash
        user.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Senha alterada para usuário: {current_user['username']}")
        
        return {"message": "Senha alterada com sucesso"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao trocar senha: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao trocar senha"
        )

# Rotas administrativas
@router.get("/users", response_model=UserListResponse)
@require_admin()
@audit_log(action="list_users", resource="admin_users")
async def list_users(
    page: int = 1,
    per_page: int = 10,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Lista usuários (admin)
    
    Lista todos os usuários do sistema
    """
    try:
        # Calcular offset
        offset = (page - 1) * per_page
        
        # Buscar usuários
        users_query = db.query(User).filter(User.id != current_user['id'])  # Excluir usuário atual
        total = users_query.count()
        users = users_query.offset(offset).limit(per_page).all()
        
        return UserListResponse(
            users=[user.to_dict() for user in users],
            total=total,
            page=page,
            per_page=per_page
        )
        
    except Exception as e:
        logger.error(f"Erro ao listar usuários: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar usuários"
        )

@router.put("/users/{user_id}/role")
@require_admin()
@audit_log(action="change_user_role", resource="admin_users")
async def change_user_role(
    user_id: int,
    new_role: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Altera role do usuário (admin)
    
    Permite admin alterar role de outro usuário
    """
    try:
        # Validar role
        if new_role not in PERMISSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role inválido"
            )
        
        # Buscar usuário
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado"
            )
        
        # Atualizar role
        old_role = user.role
        user.role = new_role
        user.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Role alterada para usuário {user.username}: {old_role} -> {new_role}")
        
        return {"message": f"Role do usuário {user.username} alterada para {new_role}"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao alterar role: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao alterar role"
        )

@router.delete("/users/{user_id}")
@require_admin()
@audit_log(action="delete_user", resource="admin_users")
async def delete_user(
    user_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deleta usuário (admin)
    
    Permite admin deletar outro usuário
    """
    try:
        # Buscar usuário
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuário não encontrado"
            )
        
        # Não permitir deletar a si mesmo
        if user.id == current_user['id']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível deletar seu próprio usuário"
            )
        
        # Deletar usuário (cascade deletará tokens e logs)
        username = user.username
        db.delete(user)
        db.commit()
        
        logger.info(f"Usuário deletado: {username}")
        
        return {"message": f"Usuário {username} deletado com sucesso"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao deletar usuário: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao deletar usuário"
        )

# Funções utilitárias
def _get_client_ip(request: Request) -> str:
    """Obtém IP do cliente"""
    try:
        return request.client.host
    except Exception:
        return "unknown"

def _get_user_agent(request: Request) -> str:
    """Obtém user agent"""
    try:
        return request.headers.get("user-agent", "unknown")
    except Exception:
        return "unknown"

def _create_audit_log(
    db: Session,
    user_id: int,
    action: str,
    resource: str,
    details: Dict[str, Any]
):
    """Cria registro de auditoria"""
    try:
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource=resource,
            details=details,
            timestamp=datetime.utcnow()
        )
        db.add(audit_log)
        db.commit()
    except Exception as e:
        logger.error(f"Erro ao criar log de auditoria: {e}")

