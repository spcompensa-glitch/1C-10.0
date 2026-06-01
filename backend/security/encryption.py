#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Criptografia Segura
==============================

Gerenciamento criptográfico para tokens OKX e dados sensíveis.

Author: Sistema 1Crypten
Version: 1.0
"""

import os
import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import secrets
import logging

logger = logging.getLogger(__name__)

class TokenEncryption:
    """
    Sistema de criptografia para tokens OKX
    
    Utiliza AES-256 para criptografia de dados sensíveis
    """
    
    def __init__(self):
        # Gerar chave de criptografia a partir de variáveis de ambiente
        self.encryption_key = self._get_encryption_key()
        self.fernet = Fernet(self.encryption_key)
        
    def _get_encryption_key(self) -> bytes:
        """
        Gera chave de criptografia a partir de senha mestre e sal
        
        Returns:
            Chave criptográfica para Fernet
        """
        try:
            # Obter senha mestre das variáveis de ambiente
            master_password = os.getenv('ENCRYPTION_PASSWORD', '1crypten-2026-system')
            salt = os.getenv('ENCRYPTION_SALT', '1crypten-security-salt-2026').encode()
            
            # Derivar chave usando PBKDF2
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,  # 256 bits
                salt=salt,
                iterations=100000,  # 100.000 iterações para segurança
            )
            
            key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
            return key
            
        except Exception as e:
            logger.error(f"Erro ao gerar chave de criptografia: {e}")
            # Fallback para chave fixa em caso de erro
            fallback_key = b'1crypten-encryption-key-2026-system-fallback'
            return base64.urlsafe_b64encode(hashlib.sha256(fallback_key).digest())
    
    def encrypt_token(self, token: str) -> str:
        """
        Criptografa token OKX
        
        Args:
            token: Token a ser criptografado
            
        Returns:
            Token criptografado em formato string
        """
        try:
            if not token:
                raise ValueError("Token não pode ser vazio")
            
            # Criptografar token
            encrypted = self.fernet.encrypt(token.encode())
            return encrypted.decode()
            
        except Exception as e:
            logger.error(f"Erro ao criptografar token: {e}")
            raise
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """
        Descriptografa token OKX
        
        Args:
            encrypted_token: Token criptografado
            
        Returns:
            Token original em texto plano
        """
        try:
            if not encrypted_token:
                raise ValueError("Token criptografado não pode ser vazio")
            
            # Descriptografar token
            decrypted = self.fernet.decrypt(encrypted_token.encode())
            return decrypted.decode()
            
        except Exception as e:
            logger.error(f"Erro ao descriptografar token: {e}")
            raise
    
    def encrypt_multiple_tokens(self, tokens_dict: dict) -> dict:
        """
        Criptografa múltiplos tokens de uma vez
        
        Args:
            tokens_dict: Dicionário com tokens
            
        Returns:
            Dicionário com tokens criptografados
        """
        encrypted_tokens = {}
        
        for key, value in tokens_dict.items():
            if value and isinstance(value, str):
                encrypted_tokens[key + '_encrypted'] = self.encrypt_token(value)
            else:
                encrypted_tokens[key] = value
                
        return encrypted_tokens
    
    def decrypt_multiple_tokens(self, encrypted_tokens: dict) -> dict:
        """
        Descriptografa múltiplos tokens de uma vez
        
        Args:
            encrypted_tokens: Dicionário com tokens criptografados
            
        Returns:
            Dicionário com tokens descriptografados
        """
        decrypted_tokens = {}
        
        for key, value in encrypted_tokens.items():
            if key.endswith('_encrypted') and value:
                try:
                    decrypted_key = key.replace('_encrypted', '')
                    decrypted_tokens[decrypted_key] = self.decrypt_token(value)
                except Exception as e:
                    logger.warning(f"Não foi possível descriptografar {key}: {e}")
                    decrypted_tokens[key] = value
            else:
                decrypted_tokens[key] = value
                
        return decrypted_tokens

class PasswordHasher:
    """
    Sistema de hash de senha segura
    
    Utiliza bcrypt com salt aleatório
    """
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Gera hash de senha com bcrypt
        
        Args:
            password: Senha em texto plano
            
        Returns:
            Hash da senha
        """
        try:
            import bcrypt
            
            # Gerar salt aleatório
            salt = bcrypt.gensalt(rounds=12)  # 12 rounds = segurança alta
            
            # Gerar hash
            password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
            
            return password_hash.decode('utf-8')
            
        except Exception as e:
            logger.error(f"Erro ao gerar hash de senha: {e}")
            raise
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verifica se senha corresponde ao hash
        
        Args:
            plain_password: Senha em texto plano
            hashed_password: Hash armazenado
            
        Returns:
            True se senha corresponde, False caso contrário
        """
        try:
            import bcrypt
            
            # Verificar senha
            return bcrypt.checkpw(
                plain_password.encode('utf-8'),
                hashed_password.encode('utf-8')
            )
            
        except Exception as e:
            logger.error(f"Erro ao verificar senha: {e}")
            return False

class DataMasker:
    """
    Sistema de mascaramento de dados sensíveis
    """
    
    @staticmethod
    def mask_api_key(api_key: str, visible_chars: int = 8) -> str:
        """
        Mascara API key mostrando apenas primeiros e últimos caracteres
        
        Args:
            api_key: API key original
            visible_chars: Quantidade de caracteres visíveis no início
            
        Returns:
            API key mascarada
        """
        if not api_key or len(api_key) <= visible_chars * 2:
            return '*' * len(api_key)
        
        visible_part = api_key[:visible_chars]
        hidden_part = '*' * (len(api_key) - visible_chars * 2)
        last_part = api_key[-visible_chars:]
        
        return f"{visible_part}{hidden_part}{last_part}"
    
    @staticmethod
    def mask_sensitive_data(data: dict, sensitive_fields: list) -> dict:
        """
        Mascara campos sensíveis em um dicionário
        
        Args:
            data: Dicionário original
            sensitive_fields: Lista de campos sensíveis
            
        Returns:
            Dicionário com campos mascarados
        """
        masked_data = data.copy()
        
        for field in sensitive_fields:
            if field in masked_data and masked_data[field]:
                if isinstance(masked_data[field], str):
                    masked_data[field] = DataMasker.mask_api_key(masked_data[field])
                else:
                    masked_data[field] = '***'
        
        return masked_data

class SecurityValidator:
    """
    Sistema de validação de segurança
    """
    
    @staticmethod
    def validate_password_strength(password: str) -> dict:
        """
        Valida força da senha
        
        Args:
            password: Senha a ser validada
            
        Returns:
            Dicionário com resultado da validação
        """
        result = {
            'is_valid': True,
            'errors': [],
            'score': 0,
            'max_score': 5
        }
        
        # Verificar comprimento mínimo
        if len(password) < 8:
            result['is_valid'] = False
            result['errors'].append('Senha deve ter pelo menos 8 caracteres')
        
        # Verificar caracteres maiúsculos
        if not any(c.isupper() for c in password):
            result['is_valid'] = False
            result['errors'].append('Senha deve conter letras maiúsculas')
        
        # Verificar caracteres minúsculos
        if not any(c.islower() for c in password):
            result['is_valid'] = False
            result['errors'].append('Senha deve conter letras minúsculas')
        
        # Verificar números
        if not any(c.isdigit() for c in password):
            result['is_valid'] = False
            result['errors'].append('Senha deve conter números')
        
        # Verificar caracteres especiais
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
            result['is_valid'] = False
            result['errors'].append('Senha deve conter caracteres especiais')
        
        # Calcular score
        if result['is_valid']:
            result['score'] = 5
        elif len(password) >= 12:
            result['score'] = 3
        elif len(password) >= 8:
            result['score'] = 2
        
        return result
    
    @staticmethod
    def validate_api_format(api_key: str, api_type: str = 'okx') -> bool:
        """
        Valida formato de API key
        
        Args:
            api_key: API key a ser validada
            api_type: Tipo de API (okx, binance, etc.)
            
        Returns:
            True se formato é válido, False caso contrário
        """
        if not api_key:
            return False
        
        # Formato OKX: 32 caracteres alfanuméricos
        if api_type == 'okx':
            return len(api_key) == 32 and api_key.isalnum()
        
        # Adicionar outros formatos conforme necessário
        return True

# Instâncias globais para performance
encryption_instance = TokenEncryption()
password_hasher = PasswordHasher()
data_masker = DataMasker()
security_validator = SecurityValidator()

# Funções utilitárias
def get_encryption_instance() -> TokenEncryption:
    """Retorna instância global de criptografia"""
    return encryption_instance

def get_password_hasher() -> PasswordHasher:
    """Retorna instância global de hash de senha"""
    return password_hasher

def get_data_masker() -> DataMasker:
    """Retorna instância global de mascaramento"""
    return data_masker

def get_security_validator() -> SecurityValidator:
    """Retorna instância global de validação"""
    return security_validator