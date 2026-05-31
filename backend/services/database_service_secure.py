# -*- coding: utf-8 -*-
"""
Database Service Secure - Versão com Proteção contra SQL Injection
=================================================================

Módulo responsável por garantir todas as operações de banco de dados
usam parametrização adequada para prevenir SQL Injection.

Author: Security Team
Version: 1.0

Security Features:
- Validação automática de inputs
- Parametrização obrigatória de queries
- Sanitização de dados
- Logging de tentativas de injeção
"""

import logging
import re
import asyncio
from typing import List, Optional, Dict, Any, Union
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean, desc, select, update, delete, text
from sqlalchemy.exc import SQLAlchemyError
import json

logger = logging.getLogger("DatabaseServiceSecure")

# Validação de inputs contra SQL Injection
class SQLInjectionValidator:
    """Valida inputs para prevenir SQL Injection"""
    
    # Padrões de SQL Injection comuns
    SQL_PATTERNS = [
        r"(?i)(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION|INTO)",
        r"(?i)(OR|AND|1=1|--|#|\/\*|\*\/)",
        r"(?i)(WAITFOR|DELAY|SLEEP|BENCHMARK)",
        r"(?i)(LOAD_FILE|INTO OUTFILE|DUMPFILE)",
        r"(?i)(XP_|SP_|EXECUTE)",
        r"(?i)(SCRIPT|JAVASCRIPT|VBSCRIPT)",
        r"(?i)(\\x|\\\\u|\\0)",
        r"(?i)(<script|</script|javascript:)",
    ]
    
    @classmethod
    def is_safe_input(cls, value: str, context: str = "general") -> bool:
        """
        Verifica se o input é seguro contra SQL Injection
        
        Args:
            value: Valor a ser validado
            context: Contexto do uso (query, column, table)
        
        Returns:
            bool: True se seguro, False se potencialmente inseguro
        """
        if not isinstance(value, str):
            return True  # Non-string values are considered safe
            
        # Remove whitespace e conver para lowercase para verificação
        clean_value = value.strip()
        
        # Verifica padrões de SQL Injection
        for pattern in cls.SQL_PATTERNS:
            if re.search(pattern, clean_value):
                logger.warning(f"🚫 [SQL-INJECTION-DETECTED] Padrão suspeito detectado: {pattern} em valor: {value[:50]}...")
                return False
        
        # Validação específica por contexto
        if context == "column":
            # Nomes de coluna não devem conter caracteres especiais
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', clean_value):
                logger.warning(f"🚫 [INVALID-COLUMN-NAME] Nome de coluna inválido: {value}")
                return False
                
        elif context == "table":
            # Nomes de tabela não devem conter caracteres especiais
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', clean_value):
                logger.warning(f"🚫 [INVALID-TABLE-NAME] Nome de tabela inválido: {value}")
                return False
                
        return True
    
    @classmethod
    def sanitize_value(cls, value: Any) -> Any:
        """Sanitiza valores para uso seguro"""
        if isinstance(value, str):
            # Remove caracteres potencialmente perigosos
            value = re.sub(r'[\'"\\;]', '', value)
            value = re.sub(r'--', '', value)
            value = re.sub(r'/\*.*?\*/', '', value, flags=re.DOTALL)
        return value

class SecureQueryBuilder:
    """Construtor de queries com parametrização segura"""
    
    @staticmethod
    def build_select(table: str, columns: List[str], conditions: Optional[Dict] = None, 
                     order_by: Optional[str] = None, limit: Optional[int] = None) -> tuple:
        """Constrói query SELECT parametrizada"""
        
        # Valida tabela e colunas
        if not SQLInjectionValidator.is_safe_input(table, "table"):
            raise ValueError(f"Tabela inválida: {table}")
            
        for col in columns:
            if not SQLInjectionValidator.is_safe_input(col, "column"):
                raise ValueError(f"Coluna inválida: {col}")
        
        # Monta query base
        query = f"SELECT {', '.join(columns)} FROM {table}"
        params = {}
        
        # Adiciona condições WHERE seguras
        if conditions:
            where_clauses = []
            for key, value in conditions.items():
                if not SQLInjectionValidator.is_safe_input(key, "column"):
                    raise ValueError(f"Coluna inválida no WHERE: {key}")
                
                where_clauses.append(f"{key} = :{key}")
                params[key] = SQLInjectionValidator.sanitize_value(value)
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
        
        # Adiciona ORDER BY
        if order_by and SQLInjectionValidator.is_safe_input(order_by, "column"):
            query += f" ORDER BY {order_by}"
        
        # Adiciona LIMIT
        if limit:
            query += f" LIMIT {limit}"
        
        return query, params
    
    @staticmethod
    def build_update(table: str, data: Dict, conditions: Dict) -> tuple:
        """Constrói query UPDATE parametrizada"""
        
        # Validações
        if not SQLInjectionValidator.is_safe_input(table, "table"):
            raise ValueError(f"Tabela inválida: {table}")
        
        set_clauses = []
        params = {}
        
        # Monta SET clauses
        for key, value in data.items():
            if not SQLInjectionValidator.is_safe_input(key, "column"):
                raise ValueError(f"Coluna inválida no SET: {key}")
            
            param_name = f"set_{key}"
            set_clauses.append(f"{key} = :{param_name}")
            params[param_name] = SQLInjectionValidator.sanitize_value(value)
        
        # Monta WHERE clauses
        where_clauses = []
        for key, value in conditions.items():
            if not SQLInjectionValidator.is_safe_input(key, "column"):
                raise ValueError(f"Coluna inválida no WHERE: {key}")
            
            param_name = f"where_{key}"
            where_clauses.append(f"{key} = :{param_name}")
            params[param_name] = SQLInjectionValidator.sanitize_value(value)
        
        query = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {' AND '.join(where_clauses)}"
        
        return query, params
    
    @staticmethod
    def build_delete(table: str, conditions: Dict) -> tuple:
        """Constrói query DELETE parametrizada"""
        
        # Validações
        if not SQLInjectionValidator.is_safe_input(table, "table"):
            raise ValueError(f"Tabela inválida: {table}")
        
        where_clauses = []
        params = {}
        
        # Monta WHERE clauses
        for key, value in conditions.items():
            if not SQLInjectionValidator.is_safe_input(key, "column"):
                raise ValueError(f"Coluna inválida no WHERE: {key}")
            
            param_name = f"where_{key}"
            where_clauses.append(f"{key} = :{param_name}")
            params[param_name] = SQLInjectionValidator.sanitize_value(value)
        
        query = f"DELETE FROM {table} WHERE {' AND '.join(where_clauses)}"
        
        return query, params

class DatabaseServiceSecure:
    """Versão segura do DatabaseService com proteção contra SQL Injection"""
    
    def __init__(self, original_database_service):
        self.original = original_database_service
        self.validator = SQLInjectionValidator()
        self.query_builder = SecureQueryBuilder()
        
    async def execute_safe_query(self, query: str, params: Dict = None, 
                               operation: str = "select") -> List[Dict]:
        """
        Executa query com parametrização segura
        
        Args:
            query: Query SQL parametrizada
            params: Parâmetros da query
            operation: Tipo de operação (select, insert, update, delete)
        
        Returns:
            Resultados da query (para select)
        """
        try:
            # Valida query básica
            if not query or len(query.strip()) == 0:
                raise ValueError("Query não pode ser vazia")
            
            # Valida parâmetros
            if params:
                for key, value in params.items():
                    if isinstance(value, str):
                        if not self.validator.is_safe_input(value):
                            raise ValueError(f"Parâmetro inválido: {key} = {value[:50]}...")
            
            logger.debug(f"🔒 [QUERY-SECURE] Executando query segura: {query[:100]}...")
            
            # Executa query usando o serviço original
            if operation == "select":
                result = await self.original.execute_raw_query(query, params or {})
                return result
            else:
                await self.original.execute_raw_query(query, params or {})
                return []
                
        except SQLAlchemyError as e:
            logger.error(f"❌ [DB-ERROR] Erro no banco: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ [SECURITY-ERROR] Erro de segurança: {e}")
            raise
    
    async def get_active_slots_safe(self) -> List[Dict]:
        """Versão segura de get_active_slots"""
        try:
            query, params = self.query_builder.build_select(
                table="slots",
                columns=["id", "symbol", "side", "qty", "entry_price", "current_stop", 
                        "status_risco", "pnl_percent", "leverage"],
                conditions={"status_risco": "ATIVO"},
                order_by="id"
            )
            
            return await self.execute_safe_query(query, params, "select")
            
        except Exception as e:
            logger.error(f"❌ [SLOTS-ERROR] Erro ao obter slots ativos: {e}")
            return []
    
    async def update_slot_status_safe(self, slot_id: int, status: str) -> bool:
        """Versão segura de atualização de status de slot"""
        try:
            if not self.validator.is_safe_input(status, "general"):
                raise ValueError(f"Status inválido: {status}")
            
            query, params = self.query_builder.build_update(
                table="slots",
                data={"status_risco": status},
                conditions={"id": slot_id}
            )
            
            await self.execute_safe_query(query, params, "update")
            return True
            
        except Exception as e:
            logger.error(f"❌ [SLOT-UPDATE-ERROR] Erro ao atualizar slot: {e}")
            return False

# Função de inicialização segura
def create_secure_database_service(original_database_service):
    """Cria wrapper seguro para o database service"""
    return DatabaseServiceSecure(original_database_service)

# Instância global (será inicializada depois)
secure_database_service = None