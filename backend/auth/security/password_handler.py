#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Handler de Senha Segura
========================

Gerenciamento de hash e verificação de senha com bcrypt.

Author: Sistema 1Crypten
Version: 1.0
"""

import bcrypt
import secrets
import string
import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class PasswordHandler:
    """
    Sistema seguro de gerenciamento de senhas
    """
    
    @staticmethod
    def hash_password(password: str, salt: Optional[bytes] = None, rounds: int = 12) -> str:
        """
        Gera hash de senha com bcrypt
        
        Args:
            password: Senha em texto plano
            salt: Salt personalizado (gerado automaticamente se None)
            rounds: Número de rounds do bcrypt (12 = segurança alta)
            
        Returns:
            Hash da senha em formato string
        """
        try:
            # Gerar salt aleatório se não fornecido
            if salt is None:
                salt = bcrypt.gensalt(rounds=rounds)
            
            # Gerar hash
            password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
            
            # Retornar como string
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
            # Verificar senha
            return bcrypt.checkpw(
                plain_password.encode('utf-8'),
                hashed_password.encode('utf-8')
            )
            
        except Exception as e:
            logger.error(f"Erro ao verificar senha: {e}")
            return False
    
    @staticmethod
    def generate_secure_password(length: int = 12) -> str:
        """
        Gera senha segura aleatória
        
        Args:
            length: Comprimento da senha
            
        Returns:
            Segura aleatória
        """
        try:
            # Definir caracteres permitidos
            lowercase = string.ascii_lowercase
            uppercase = string.ascii_uppercase
            digits = string.digits
            symbols = '!@#$%^&*()_+-=[]{}|;:,.<>?'
            
            # Garantir pelo menos um de cada tipo
            password = [
                secrets.choice(lowercase),
                secrets.choice(uppercase),
                secrets.choice(digits),
                secrets.choice(symbols)
            ]
            
            # Preencher o resto com caracteres aleatórios
            all_chars = lowercase + uppercase + digits + symbols
            for _ in range(length - 4):
                password.append(secrets.choice(all_chars))
            
            # Embaralhar
            secrets.SystemRandom().shuffle(password)
            
            return ''.join(password)
            
        except Exception as e:
            logger.error(f"Erro ao gerar senha segura: {e}")
            # Fallback para senha simples
            return secrets.token_urlsafe(length // 2)
    
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
            'warnings': [],
            'score': 0,
            'max_score': 5,
            'strength': 'fraca'
        }
        
        # Verificar comprimento mínimo
        if len(password) < 8:
            result['is_valid'] = False
            result['errors'].append('Senha deve ter pelo menos 8 caracteres')
        
        # Verificar comprimento ideal
        if len(password) < 12:
            result['warnings'].append('Senha com menos de 12 caracteres é considerada fraca')
        
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
        special_chars = set('!@#$%^&*()_+-=[]{}|;:,.<>?')
        if not any(c in special_chars for c in password):
            result['warnings'].append('Senha não contém caracteres especiais')
        
        # Calcular score
        if result['is_valid']:
            score = 0
            
            # Comprimento
            if len(password) >= 12:
                score += 1
            elif len(password) >= 8:
                score += 0.5
            
            # Variedade de caracteres
            char_types = 0
            if any(c.isupper() for c in password):
                char_types += 1
            if any(c.islower() for c in password):
                char_types += 1
            if any(c.isdigit() for c in password):
                char_types += 1
            if any(c in special_chars for c in password):
                char_types += 1
            
            score += min(char_types - 1, 2)  # Até 2 pontos por variedade
            
            # Sequências comuns
            common_sequences = ['123', 'abc', 'qwerty', 'password', 'letmein']
            password_lower = password.lower()
            if any(seq in password_lower for seq in common_sequences):
                score -= 1
                result['warnings'].append('Senha contém sequência comum')
            
            result['score'] = max(0, score)
        
        # Determinar força
        if result['score'] >= 4:
            result['strength'] = 'muito forte'
        elif result['score'] >= 3:
            result['strength'] = 'forte'
        elif result['score'] >= 2:
            result['strength'] = 'média'
        elif result['score'] >= 1:
            result['strength'] = 'fraca'
        else:
            result['strength'] = 'muito fraca'
        
        return result
    
    @staticmethod
    def is_password_compromised(password: str) -> bool:
        """
        Verifica se senha está em listas de senhas comprometidas
        
        Args:
            password: Senha a ser verificada
            
        Returns:
            True se senha estiver comprometida, False caso contrário
        """
        try:
            # Em uma implementação real, consultar API de senhas comprometidas
            # Para agora, verificar contra algumas senhas comuns
            common_passwords = [
                'password', '123456', '12345678', '123456789', '1234567890',
                'qwerty', 'abc123', 'letmein', 'welcome', 'monkey',
                'password1', 'admin', 'login', 'user', 'root'
            ]
            
            password_lower = password.lower()
            return password_lower in common_passwords
            
        except Exception as e:
            logger.error(f"Erro ao verificar senha comprometida: {e}")
            return False
    
    @staticmethod
    def compare_passwords(password1: str, password2: str) -> bool:
        """
        Compara duas senhas (ignorando case e espaços extras)
        
        Args:
            password1: Primeira senha
            password2: Segunda senha
            
        Returns:
            True se senhas forem iguais, False caso contrário
        """
        try:
            # Normalizar senhas (remover espaços extras, ignorar case)
            normalized1 = password1.strip().lower()
            normalized2 = password2.strip().lower()
            
            return normalized1 == normalized2
            
        except Exception as e:
            logger.error(f"Erro ao comparar senhas: {e}")
            return False
    
    @staticmethod
    def get_password_entropy(password: str) -> float:
        """
        Calcula entropia da senha
        
        Args:
            password: Senha a ser analisada
            
        Returns:
            Valor de entropia em bits
        """
        try:
            # Calcular entropia baseada no tamanho e variedade de caracteres
            length = len(password)
            
            # Estimar tamanho do conjunto de caracteres
            char_set = set()
            for char in password:
                if char.islower():
                    char_set.update(string.ascii_lowercase)
                elif char.isupper():
                    char_set.update(string.ascii_uppercase)
                elif char.isdigit():
                    char_set.update(string.digits)
                else:
                    char_set.update('!@#$%^&*()_+-=[]{}|;:,.<>?')
            
            # Calcular entropia
            char_set_size = len(char_set)
            if char_set_size == 0:
                return 0
            
            entropy = length * (char_set_size ** (1/length) * 8)
            return entropy
            
        except Exception as e:
            logger.error(f"Erro ao calcular entropia: {e}")
            return 0

# Instância global
password_handler = PasswordHandler()

# Funções utilitárias
def hash_password(password: str, salt: Optional[bytes] = None, rounds: int = 12) -> str:
    """Retorna hash de senha"""
    return password_handler.hash_password(password, salt, rounds)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica senha"""
    return password_handler.verify_password(plain_password, hashed_password)

def generate_secure_password(length: int = 12) -> str:
    """Gera senha segura"""
    return password_handler.generate_secure_password(length)

def validate_password_strength(password: str) -> dict:
    """Valida força da senha"""
    return password_handler.validate_password_strength(password)