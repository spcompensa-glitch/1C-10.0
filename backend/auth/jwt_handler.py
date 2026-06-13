#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema JWT de Autenticação
============================

Gerenciamento de tokens JWT para autenticação e autorização.

Author: Sistema 1Crypten
Version: 1.0
"""

import os
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

logger = logging.getLogger(__name__)

class JWTManager:
    """
    Gerenciador de tokens JWT
    """
    
    def __init__(self):
        # Configurações de JWT
        self.secret_key = self._get_jwt_secret_key()
        self.algorithm = "HS256"
        from config import settings
        self.access_token_expire = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        self.refresh_token_expire = timedelta(days=7)
        
    def _get_jwt_secret_key(self) -> str:
        """
        Obtém chave secreta do JWT
        
        Returns:
            Chave secreta para JWT
        """
        try:
            # Tentar obter da variável de ambiente
            secret_key = os.getenv('JWT_SECRET_KEY', '1crypten-jwt-secret-2026-production')
            
            # Validar comprimento mínimo
            if len(secret_key) < 32:
                logger.warning("Chave JWT muito curta, gerando nova chave")
                secret_key = secrets.token_urlsafe(64)
                os.environ['JWT_SECRET_KEY'] = secret_key
                
            return secret_key
            
        except Exception as e:
            logger.error(f"Erro ao obter chave JWT: {e}")
            # Fallback para chave padrão
            return '1crypten-jwt-secret-2026-production'
    
    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """
        Cria token de acesso JWT
        
        Args:
            data: Dados para codificar no token
            expires_delta: Tempo de expiração personalizado
            
        Returns:
            Token JWT de acesso
        """
        try:
            to_encode = data.copy()
            
            # Adicionar timestamp de emissão
            to_encode.update({
                'iat': datetime.utcnow(),
                'type': 'access'
            })
            
            # Definir tempo de expiração
            if expires_delta:
                expire = datetime.utcnow() + expires_delta
            else:
                expire = datetime.utcnow() + self.access_token_expire
                
            to_encode.update({'exp': expire})
            
            # Codificar token
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            
            logger.info(f"Token de acesso criado para usuário: {data.get('sub', 'unknown')}")
            return encoded_jwt
            
        except Exception as e:
            logger.error(f"Erro ao criar token de acesso: {e}")
            raise
    
    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """
        Cria token de refresh JWT
        
        Args:
            data: Dados para codificar no token
            
        Returns:
            Token JWT de refresh
        """
        try:
            to_encode = data.copy()
            
            # Adicionar timestamp de emissão
            to_encode.update({
                'iat': datetime.utcnow(),
                'type': 'refresh'
            })
            
            # Definir tempo de expiração (7 dias)
            expire = datetime.utcnow() + self.refresh_token_expire
            to_encode.update({'exp': expire})
            
            # Codificar token
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            
            logger.info(f"Token de refresh criado para usuário: {data.get('sub', 'unknown')}")
            return encoded_jwt
            
        except Exception as e:
            logger.error(f"Erro ao criar token de refresh: {e}")
            raise
    
    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """
        Verifica e decodifica token JWT
        
        Args:
            token: Token JWT a ser verificado
            token_type: Tipo de token esperado ('access' ou 'refresh')
            
        Returns:
            Payload do token se válido, None caso contrário
        """
        try:
            # Decodificar token
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Verificar tipo do token
            if payload.get("type") != token_type:
                logger.warning(f"Tipo de token inválido: {payload.get('type')} esperado: {token_type}")
                return None
            
            # Verificar se usuário está no payload
            username: str = payload.get("sub")
            if username is None:
                logger.warning("Token sem username")
                return None
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expirado")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Token inválido")
            return None
        except Exception as e:
            logger.error(f"Erro ao verificar token: {e}")
            return None
    
    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """
        Gera novo token de acesso a partir do token de refresh
        
        Args:
            refresh_token: Token de refresh válido
            
        Returns:
            Novo token de acesso, None se refresh token for inválido
        """
        try:
            # Verificar refresh token
            payload = self.verify_token(refresh_token, "refresh")
            if not payload:
                return None
            
            # Criar novo token de acesso
            new_access_token = self.create_access_token({
                'sub': payload.get('sub'),
                'role': payload.get('role'),
                'email': payload.get('email')
            })
            
            logger.info(f"Token de acesso refresh para usuário: {payload.get('sub')}")
            return new_access_token
            
        except Exception as e:
            logger.error(f"Erro ao refresh token: {e}")
            return None
    
    def revoke_token(self, token: str) -> bool:
        """
        Marca token como revogado (implementação básica)
        
        Args:
            token: Token a ser revogado
            
        Returns:
            True se token foi revogado, False caso contrário
        """
        try:
            # Em uma implementação real, armazenar token em blacklist
            # Por enquanto apenas logamos a ação
            payload = self.verify_token(token)
            if payload:
                logger.info(f"Token revogado para usuário: {payload.get('sub')}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Erro ao revogar token: {e}")
            return False
    
    def get_token_info(self, token: str) -> Dict[str, Any]:
        """
        Obtém informações do token sem verificar validade
        
        Args:
            token: Token JWT
            
        Returns:
            Informações do token
        """
        try:
            # Não verificamos a expiração aqui, apenas decodificamos
            import base64
            import json
            
            # Remover prefixo 'Bearer '
            if token.startswith('Bearer '):
                token = token[7:]
            
            # Dividir token em partes
            parts = token.split('.')
            if len(parts) != 3:
                return {}
            
            # Decodificar payload (sem verificação de assinatura)
            payload_b64 = parts[1]
            # Adicionar padding se necessário
            payload_b64 += '=' * (4 - len(payload_b64) % 4)
            
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            return payload
            
        except Exception as e:
            logger.error(f"Erro ao obter informações do token: {e}")
            return {}

# Instância global
jwt_manager = JWTManager()

# Funções utilitárias
def get_jwt_manager() -> JWTManager:
    """Retorna instância global do JWT Manager"""
    return jwt_manager

def create_user_tokens(user_data: Dict[str, Any]) -> Dict[str, str]:
    """
    Cria tokens para usuário
    
    Args:
        user_data: Dados do usuário
        
    Returns:
        Dicionário com access_token e refresh_token
    """
    access_token = jwt_manager.create_access_token(user_data)
    refresh_token = jwt_manager.create_refresh_token(user_data)
    
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'token_type': 'bearer'
    }

def verify_user_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifica token de usuário
    
    Args:
        token: Token JWT
        
    Returns:
        Dados do usuário se token for válido
    """
    return jwt_manager.verify_token(token, "access")