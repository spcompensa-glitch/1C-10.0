#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modelos de Banco de Dados para Sistema de Autenticação
======================================================

Modelos SQLAlchemy para sistema de usuários, tokens OKX e auditoria.

Author: Sistema 1Crypten
Version: 1.0
"""

import sqlalchemy as sa
from sqlalchemy.orm import relationship
from datetime import datetime
from .database_service_secure import Base

class User(Base):
    """Modelo de Usuário do Sistema"""
    
    __tablename__ = 'users'
    
    # Campos básicos
    id = sa.Column(sa.Integer, primary_key=True)
    username = sa.Column(sa.String(50), unique=True, nullable=False, index=True)
    email = sa.Column(sa.String(100), unique=True, nullable=True, index=True)
    password_hash = sa.Column(sa.String(255), nullable=False)
    
    # Configuração de conta
    role = sa.Column(sa.String(10), default='user', nullable=False, index=True)
    is_active = sa.Column(sa.Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = sa.Column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = sa.Column(sa.DateTime, nullable=True)
    
    # Relacionamentos
    okx_tokens = relationship("UserOKXTokens", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
    
    @property
    def permissions(self):
        """Retorna lista de permissões baseado no role"""
        from auth.permissions import PERMISSIONS
        return PERMISSIONS.get(self.role, [])
    
    def has_permission(self, permission: str) -> bool:
        """Verifica se usuário tem permissão específica"""
        return permission in self.permissions
    
    def to_dict(self):
        """Converte usuário para dicionário (sem dados sensíveis)"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'permissions': self.permissions
        }

class UserOKXTokens(Base):
    """Modelo de Tokens OKX Criptografados"""
    
    __tablename__ = 'user_okx_tokens'
    
    # Campos básicos
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Dados do token
    exchange_name = sa.Column(sa.String(20), default='okx', nullable=False)
    api_key_encrypted = sa.Column(sa.Text, nullable=False)
    secret_key_encrypted = sa.Column(sa.Text, nullable=False)
    passphrase_encrypted = sa.Column(sa.Text, nullable=True)
    
    # Status e auditoria
    is_active = sa.Column(sa.Boolean, default=True, nullable=False)
    ip_address = sa.Column(sa.String(45), nullable=True)
    user_agent = sa.Column(sa.Text, nullable=True)
    
    # Timestamps
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = sa.Column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relacionamentos
    user = relationship("User", back_populates="okx_tokens")
    
    def __repr__(self):
        return f"<UserOKXTokens(id={self.id}, user_id={self.user_id}, active={self.is_active})>"
    
    def to_dict(self):
        """Converte token para dicionário (sem dados sensíveis)"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'exchange_name': self.exchange_name,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent
        }

class AuditLog(Base):
    """Modelo de Auditoria do Sistema"""
    
    __tablename__ = 'audit_log'
    
    # Campos básicos
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.Integer, sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    
    # Ação e recurso
    action = sa.Column(sa.String(50), nullable=False, index=True)
    resource = sa.Column(sa.String(100), nullable=True, index=True)
    details = sa.Column(sa.JSON, nullable=True)
    
    # Auditoria de acesso
    ip_address = sa.Column(sa.String(45), nullable=True)
    user_agent = sa.Column(sa.Text, nullable=True)
    
    # Timestamp
    timestamp = sa.Column(sa.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relacionamentos
    user = relationship("User", back_populates="audit_logs")
    
    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}', user_id={self.user_id})>"
    
    def to_dict(self):
        """Converte log de auditoria para dicionário"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'resource': self.resource,
            'details': self.details,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

class UserSession(Base):
    """Modelo de Sessões de Usuário (para refresh tokens)"""
    
    __tablename__ = 'user_sessions'
    
    # Campos básicos
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Tokens
    refresh_token_hash = sa.Column(sa.String(255), nullable=False, unique=True)
    access_token_hash = sa.Column(sa.String(255), nullable=True)
    
    # Status
    is_active = sa.Column(sa.Boolean, default=True, nullable=False)
    expires_at = sa.Column(sa.DateTime, nullable=False)
    revoked_at = sa.Column(sa.DateTime, nullable=True)
    
    # Auditoria
    ip_address = sa.Column(sa.String(45), nullable=True)
    user_agent = sa.Column(sa.Text, nullable=True)
    
    # Timestamps
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = sa.Column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relacionamentos
    user = relationship("User")
    
    def __repr__(self):
        return f"<UserSession(id={self.id}, user_id={self.user_id}, active={self.is_active})>"
    
    def is_valid(self) -> bool:
        """Verifica se sessão é válida"""
        return (self.is_active and 
                self.expires_at > datetime.utcnow() and 
                self.revoked_at is None)
    
    def to_dict(self):
        """Converte sessão para dicionário"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'is_active': self.is_active,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'revoked_at': self.revoked_at.isoformat() if self.revoked_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }