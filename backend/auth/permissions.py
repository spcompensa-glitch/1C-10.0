#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Permissões do Sistema
=================================

Define permissões por nível de usuário e rotas protegidas.

Author: Sistema 1Crypten
Version: 1.0
"""

from enum import Enum
from typing import List, Dict, Set

class Permission(Enum):
    """Enumera todas as permissões do sistema"""
    # Páginas principais
    BANCA = "banca"
    CHAT = "chat"
    CONFIG = "config"
    ACCOUNT = "account"
    
    # Admin
    USERS = "users"
    LOGS = "logs"
    SETTINGS = "settings"
    
    # Operações específicas
    TRADE = "trade"
    WITHDRAW = "withdraw"
    DEPOSIT = "deposit"
    VIEW_BALANCE = "view_balance"

# Mapeamento de roles para permissões
PERMISSIONS: Dict[str, List[str]] = {
    'admin': [
        Permission.BANCA.value,
        Permission.CHAT.value,
        Permission.CONFIG.value,
        Permission.ACCOUNT.value,
        Permission.USERS.value,
        Permission.LOGS.value,
        Permission.SETTINGS.value,
        Permission.TRADE.value,
        Permission.WITHDRAW.value,
        Permission.DEPOSIT.value,
        Permission.VIEW_BALANCE.value,
    ],
    'user': [
        Permission.BANCA.value,
        Permission.CHAT.value,
        Permission.CONFIG.value,
        Permission.ACCOUNT.value,
        Permission.TRADE.value,
        Permission.VIEW_BALANCE.value,
    ]
}

# Rotas protegidas por permissão
PROTECTED_ROUTES: Dict[str, List[str]] = {
    '/api/banca/*': [Permission.BANCA.value],
    '/api/chat/*': [Permission.CHAT.value],
    '/api/config/*': [Permission.CONFIG.value],
    '/api/account/*': [Permission.ACCOUNT.value],
    
    # Admin routes
    '/api/admin/users/*': [Permission.USERS.value],
    '/api/admin/logs/*': [Permission.LOGS.value],
    '/api/admin/settings/*': [Permission.SETTINGS.value],
    
    # Trading operations
    '/api/trade/*': [Permission.TRADE.value],
    '/api/withdraw/*': [Permission.WITHDRAW.value],
    '/api/deposit/*': [Permission.DEPOSIT.value],
    
    # System operations
    '/api/balance/*': [Permission.VIEW_BALANCE.value],
}

def has_permission(user_role: str, permission: str) -> bool:
    """
    Verifica se um role tem permissão específica
    
    Args:
        user_role: Role do usuário ('admin' ou 'user')
        permission: Permissão a ser verificada
        
    Returns:
        True se tiver permissão, False caso contrário
    """
    user_permissions = PERMISSIONS.get(user_role, [])
    return permission in user_permissions

def get_user_permissions(user_role: str) -> List[str]:
    """
    Retorna todas as permissões de um role
    
    Args:
        user_role: Role do usuário
        
    Returns:
        Lista de permissões
    """
    return PERMISSIONS.get(user_role, [])

def is_route_protected(route: str) -> bool:
    """
    Verifica se uma rota está protegida
    
    Args:
        route: Rota a ser verificada
        
    Returns:
        True se rota é protegida, False caso contrário
    """
    for protected_route in PROTECTED_ROUTES:
        if route.startswith(protected_route.replace('*', '')):
            return True
    return False

def get_required_permissions(route: str) -> List[str]:
    """
    Retorna permissões necessárias para uma rota
    
    Args:
        route: Rota a ser verificada
        
    Returns:
        Lista de permissões necessárias
    """
    for protected_route, permissions in PROTECTED_ROUTES.items():
        if route.startswith(protected_route.replace('*', '')):
            return permissions
    return []

def get_user_role_from_database(user_id: int, db_session) -> str:
    """
    Obtém o role do usuário do banco de dados
    
    Args:
        user_id: ID do usuário
        db_session: Sessão do banco de dados
        
    Returns:
        Role do usuário ('admin' ou 'user')
    """
    try:
        from ..database.models_auth import User
        user = db_session.query(User).filter(User.id == user_id).first()
        return user.role if user else 'user'
    except Exception:
        return 'user'  # Fallback para segurança

def validate_user_access(user_role: str, route: str) -> bool:
    """
    Valida se usuário tem acesso a uma rota específica
    
    Args:
        user_role: Role do usuário
        route: Rota a ser acessada
        
    Returns:
        True se acesso permitido, False caso contrário
    """
    if not is_route_protected(route):
        return True  # Rota não protegida
    
    required_permissions = get_required_permissions(route)
    return any(has_permission(user_role, perm) for perm in required_permissions)