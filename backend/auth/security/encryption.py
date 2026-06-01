#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de Criptografia Segura
=============================

Gerencia criptografia e descriptografia de dados sensíveis.

Author: Sistema 1Crypten
Version: 1.0
"""

import logging
import os
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from auth_config import auth_settings as settings

logger = logging.getLogger(__name__)

class TokenEncryption:
    """
    Sistema de criptografia para tokens OKX e outros dados sensíveis
    """
    
    def __init__(self):
        """Inicializa o sistema de criptografia"""
        self._key = None
        self.fernet = None
        self._initialize_encryption()
    
    def _initialize_encryption(self):
        """
        Inicializa o sistema de criptografia
        """
        try:
            # Derivar chave a partir da senha e salt
            password = settings.encryption_password.encode('utf-8')
            salt = settings.encryption_salt.encode('utf-8')
            
            # KDF para derivar chave
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            
            key = base64.urlsafe_b64encode(kdf.derive(password))
            self.fernet = Fernet(key)
            
            logger.info("Sistema de criptografia inicializado com sucesso")
            
        except Exception as e:
            logger.error(f"Erro ao inicializar criptografia: {e}")
            raise
    
    def encrypt_token(self, token: str) -> str:
        """
        Criptografa um token
        
        Args:
            token: Token em texto plano
            
        Returns:
            Token criptografado
        """
        try:
            if not token:
                raise ValueError("Token não pode ser vazio")
            
            # Criptografar
            encrypted = self.fernet.encrypt(token.encode('utf-8'))
            
            # Retornar como string
            return encrypted.decode('utf-8')
            
        except Exception as e:
            logger.error(f"Erro ao criptografar token: {e}")
            raise
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """
        Descriptografa um token
        
        Args:
            encrypted_token: Token criptografado
            
        Returns:
            Token em texto plano
        """
        try:
            if not encrypted_token:
                raise ValueError("Token criptografado não pode ser vazio")
            
            # Descriptografar
            decrypted = self.fernet.decrypt(encrypted_token.encode('utf-8'))
            
            # Retornar como string
            return decrypted.decode('utf-8')
            
        except Exception as e:
            logger.error(f"Erro ao descriptografar token: {e}")
            raise
    
    def rotate_key(self) -> bool:
        """
        Rotaciona a chave de criptografia
        
        Returns:
            True se a rotação foi bem sucedida
        """
        try:
            # Gerar novo salt
            import secrets
            new_salt = secrets.token_urlsafe(32)
            settings.encryption_salt = new_salt
            
            # Recriar chave
            self._initialize_encryption()
            
            logger.info("Chave de criptografia rotacionada com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao rotacionar chave: {e}")
            return False
    
    def is_valid_encrypted_data(self, encrypted_data: str) -> bool:
        """
        Verifica se os dados criptografados são válidos
        
        Args:
            encrypted_data: Dados criptografados
            
        Returns:
            True se os dados forem válidos
        """
        try:
            # Tentar descriptografar
            self.decrypt_token(encrypted_data)
            return True
            
        except Exception:
            return False

class DataMasker:
    """
    Sistema para mascarar dados sensíveis
    """
    
    @staticmethod
    def mask_api_key(api_key: str) -> str:
        """
        Mascara uma API key para exibição segura
        
        Args:
            api_key: API key em texto plano
            
        Returns:
            API key mascarada
        """
        try:
            if not api_key or len(api_key) < 8:
                return api_key
            
            # Manter os primeiros 4 e últimos 4 caracteres
            masked = api_key[:4] + '*' * (len(api_key) - 8) + api_key[-4:]
            
            return masked
            
        except Exception as e:
            logger.error(f"Erro ao mascarar API key: {e}")
            return api_key
    
    @staticmethod
    def mask_secret_key(secret_key: str) -> str:
        """
        Mascara uma secret key para exibição segura
        
        Args:
            secret_key: Secret key em texto plano
            
        Returns:
            Secret key mascarada
        """
        try:
            if not secret_key:
                return secret_key
            
            # Manter apenas os primeiros 2 e últimos 2 caracteres
            masked = secret_key[:2] + '*' * (len(secret_key) - 4) + secret_key[-2:]
            
            return masked
            
        except Exception as e:
            logger.error(f"Erro ao mascarar secret key: {e}")
            return secret_key
    
    @staticmethod
    def mask_passphrase(passphrase: str) -> str:
        """
        Mascara uma passphrase para exibição segura
        
        Args:
            passphrase: Passphrase em texto plano
            
        Returns:
            Passphrase mascarada
        """
        try:
            if not passphrase:
                return passphrase
            
            # Esconder completamente
            masked = '*' * len(passphrase)
            
            return masked
            
        except Exception as e:
            logger.error(f"Erro ao mascarar passphrase: {e}")
            return passphrase

# Instância global
_encryption_instance = None

def get_encryption_instance() -> TokenEncryption:
    """
    Obtém instância global de criptografia
    
    Returns:
        Instância de TokenEncryption
    """
    global _encryption_instance
    
    if _encryption_instance is None:
        _encryption_instance = TokenEncryption()
    
    return _encryption_instance

def get_data_masker() -> DataMasker:
    """
    Obtém instância global de mascaramento de dados
    
    Returns:
        Instância de DataMasker
    """
    return DataMasker()

# Funções utilitárias
def encrypt_token(token: str) -> str:
    """Criptografa token"""
    encryption = get_encryption_instance()
    return encryption.encrypt_token(token)

def decrypt_token(encrypted_token: str) -> str:
    """Descriptografa token"""
    encryption = get_encryption_instance()
    return encryption.decrypt_token(encrypted_token)

def mask_api_key(api_key: str) -> str:
    """Mascara API key"""
    masker = get_data_masker()
    return masker.mask_api_key(api_key)