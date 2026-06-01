#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serviço OKX para Usuários
=========================

Integração com OKX usando tokens de usuários individuais.

Author: Sistema 1Crypten
Version: 1.0
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
import asyncio

from .okx_rest import OKXRest
from ..database.models_auth import UserOKXTokens
from ..security.encryption import get_encryption_instance

logger = logging.getLogger(__name__)

class OKXUserService(OKXRest):
    """
    Serviço OKX que usa tokens de usuários individuais
    """
    
    def __init__(self, user_id: int, db_session: Session):
        """
        Inicializa serviço OKX para usuário específico
        
        Args:
            user_id: ID do usuário
            db_session: Sessão do banco de dados
        """
        super().__init__()
        self.user_id = user_id
        self.db_session = db_session
        self.encryption = get_encryption_instance()
        self._current_token_id = None
    
    def get_user_tokens(self, active_only: bool = True) -> List[UserOKXTokens]:
        """
        Obtém tokens do usuário
        
        Args:
            active_only: Se True, retorna apenas tokens ativos
            
        Returns:
            Lista de tokens do usuário
        """
        try:
            query = self.db_session.query(UserOKXTokens).filter(
                UserOKXTokens.user_id == self.user_id
            )
            
            if active_only:
                query = query.filter(UserOKXTokens.is_active == True)
            
            return query.all()
            
        except Exception as e:
            logger.error(f"Erro ao obter tokens do usuário {self.user_id}: {e}")
            return []
    
    def setup_user_session(self, token_id: Optional[int] = None):
        """
        Configura sessão OKX com tokens do usuário
        
        Args:
            token_id: ID específico do token (se None, usa o primeiro ativo)
        """
        try:
            # Obter tokens do usuário
            tokens = self.get_user_tokens(active_only=True)
            
            if not tokens:
                raise ValueError("Nenhum token ativo encontrado para o usuário")
            
            # Selecionar token específico ou o primeiro disponível
            if token_id:
                token = next((t for t in tokens if t.id == token_id), None)
                if not token:
                    raise ValueError(f"Token {token_id} não encontrado ou inativo")
            else:
                token = tokens[0]  # Usar primeiro token ativo
            
            self._current_token_id = token.id
            
            # Descriptografar e configurar credenciais
            self.api_key = self.encryption.decrypt_token(token.api_key_encrypted)
            self.api_secret = self.encryption.decrypt_token(token.secret_key_encrypted)
            self.passphrase = self.encryption.decrypt_token(token.passphrase_encrypted) if token.passphrase_encrypted else None
            
            logger.info(f"Sessão OKX configurada para usuário {self.user_id} com token {token.id}")
            
        except Exception as e:
            logger.error(f"Erro ao configurar sessão OKX: {e}")
            raise
    
    def switch_token(self, token_id: int):
        """
        Troca para outro token do usuário
        
        Args:
            token_id: ID do token para trocar
        """
        try:
            # Verificar se token existe e está ativo
            token = self.db_session.query(UserOKXTokens).filter(
                UserOKXTokens.id == token_id,
                UserOKXTokens.user_id == self.user_id,
                UserOKXTokens.is_active == True
            ).first()
            
            if not token:
                raise ValueError(f"Token {token_id} não encontrado ou inativo")
            
            # Reconfigurar sessão
            self.setup_user_session(token_id)
            
            logger.info(f"Troca de token OKX para token {token_id} do usuário {self.user_id}")
            
        except Exception as e:
            logger.error(f"Erro ao trocar token OKX: {e}")
            raise
    
    def get_active_tokens(self) -> List[Dict[str, Any]]:
        """
        Obtém lista de tokens ativos do usuário
        
        Returns:
            Lista de tokens com informações básicas
        """
        try:
            tokens = self.get_user_tokens(active_only=True)
            
            token_info = []
            for token in tokens:
                token_info.append({
                    'id': token.id,
                    'exchange_name': token.exchange_name,
                    'is_active': token.is_active,
                    'created_at': token.created_at.isoformat(),
                    'updated_at': token.updated_at.isoformat(),
                    'ip_address': token.ip_address,
                    'user_agent': token.user_agent
                })
            
            return token_info
            
        except Exception as e:
            logger.error(f"Erro ao obter tokens ativos: {e}")
            return []
    
    # Métodos específicos que sobrescrevem os da classe base
    async def get_account_info(self) -> Dict[str, Any]:
        """Obtém informações da conta OKX"""
        try:
            if not self.api_key:
                self.setup_user_session()
            
            return await super().get_account_info()
            
        except Exception as e:
            logger.error(f"Erro ao obter info da conta OKX: {e}")
            raise
    
    async def get_account_balance(self) -> Dict[str, Any]:
        """Obtém saldo da conta OKX"""
        try:
            if not self.api_key:
                self.setup_user_session()
            
            return await super().get_account_balance()
            
        except Exception as e:
            logger.error(f"Erro ao obter saldo da conta OKX: {e}")
            raise
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Obtém posições abertas"""
        try:
            if not self.api_key:
                self.setup_user_session()
            
            return await super().get_positions()
            
        except Exception as e:
            logger.error(f"Erro ao obter posições OKX: {e}")
            raise
    
    async def place_order(self, symbol: str, side: str, order_type: str, size: str, **kwargs) -> Dict[str, Any]:
        """Coloca ordem"""
        try:
            if not self.api_key:
                self.setup_user_session()
            
            return await super().place_order(symbol, side, order_type, size, **kwargs)
            
        except Exception as e:
            logger.error(f"Erro ao colocar ordem OKX: {e}")
            raise
    
    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """Cancela ordem"""
        try:
            if not self.api_key:
                self.setup_user_session()
            
            return await super().cancel_order(symbol, order_id)
            
        except Exception as e:
            logger.error(f"Erro ao cancelar ordem OKX: {e}")
            raise
    
    async def get_order_status(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """Obtém status da ordem"""
        try:
            if not self.api_key:
                self.setup_user_session()
            
            return await super().get_order_status(symbol, order_id)
            
        except Exception as e:
            logger.error(f"Erro ao obter status da ordem OKX: {e}")
            raise
    
    # Métodos para múltiplos tokens
    async def test_all_tokens(self) -> Dict[int, Dict[str, Any]]:
        """
        Testa todos os tokens ativos do usuário
        
        Returns:
            Dicionário com resultados dos testes por token ID
        """
        results = {}
        tokens = self.get_user_tokens(active_only=True)
        
        for token in tokens:
            try:
                # Trocar para este token
                old_token_id = self._current_token_id
                self.switch_token(token.id)
                
                # Testar conexão
                account_info = await self.get_account_balance()
                
                results[token.id] = {
                    'status': 'success',
                    'message': 'Token válido',
                    'account_info': account_info
                }
                
                # Voltar para token original se existia
                if old_token_id:
                    self.switch_token(old_token_id)
                    
            except Exception as e:
                results[token.id] = {
                    'status': 'error',
                    'message': str(e),
                    'error_details': str(e)
                }
                
                # Voltar para token original se existia
                if old_token_id:
                    try:
                        self.switch_token(old_token_id)
                    except:
                        pass
        
        return results
    
    # Métodos de segurança
    def validate_token_permissions(self, required_permission: str) -> bool:
        """
        Valifica se o token atual tem permissão para operação
        
        Args:
            required_permission: Permissão necessária
            
        Returns:
            True se tiver permissão
        """
        # Aqui você pode implementar lógica de permissões específicas
        # Por exemplo, verificar se o token pode fazer trading, etc.
        return True
    
    def get_token_audit_info(self) -> Dict[str, Any]:
        """
        Obtém informações de auditoria do token atual
        
        Returns:
            Informações de auditoria
        """
        try:
            if not self._current_token_id:
                return {}
            
            token = self.db_session.query(UserOKXTokens).filter(
                UserOKXTokens.id == self._current_token_id
            ).first()
            
            if token:
                return {
                    'token_id': token.id,
                    'user_id': token.user_id,
                    'exchange_name': token.exchange_name,
                    'is_active': token.is_active,
                    'created_at': token.created_at.isoformat(),
                    'updated_at': token.updated_at.isoformat(),
                    'ip_address': token.ip_address,
                    'user_agent': token.user_agent
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"Erro ao obter info de auditoria do token: {e}")
            return {}

# Funções utilitárias
def get_okx_service_for_user(user_id: int, db_session: Session) -> OKXUserService:
    """
    Factory para criar instância de OKXUserService
    
    Args:
        user_id: ID do usuário
        db_session: Sessão do banco de dados
        
    Returns:
        Instância configurada de OKXUserService
    """
    try:
        service = OKXUserService(user_id, db_session)
        service.setup_user_session()
        return service
        
    except Exception as e:
        logger.error(f"Erro ao criar OKXUserService para usuário {user_id}: {e}")
        raise

def validate_user_has_okx_tokens(user_id: int, db_session: Session) -> bool:
    """
    Valida se usuário tem tokens OKX ativos
    
    Args:
        user_id: ID do usuário
        db_session: Sessão do banco de dados
        
    Returns:
        True se usuário tem tokens ativos
    """
    try:
        service = OKXUserService(user_id, db_session)
        tokens = service.get_user_tokens(active_only=True)
        return len(tokens) > 0
        
    except Exception as e:
        logger.error(f"Erro ao validar tokens do usuário {user_id}: {e}")
        return False