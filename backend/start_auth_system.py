#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inicializador do Sistema de Autenticação 1Crypten
=================================================

Script principal para iniciar o sistema de autenticação completo.

Author: Sistema 1Crypten
Version: 1.0
"""

import os
import sys
import logging
import argparse
from pathlib import Path

# Adicionar o diretório atual ao path
sys.path.append(str(Path(__file__).parent))

def setup_environment():
    """Configura ambiente e variáveis necessárias"""
    # Garantir que .env exista
    env_path = Path(__file__).parent / ".." / ".env"
    if not env_path.exists():
        print(f"⚠️  Arquivo .env não encontrado em {env_path}")
        print("Criando arquivo .env com configurações padrão...")
        
        env_content = """# Configurações do Sistema 1Crypten
# ================================

# Configurações de Autenticação
ENCRYPTION_PASSWORD=1crypten-encryption-password-2026
ENCRYPTION_SALT=1crypten-encryption-salt-2026
JWT_SECRET_KEY=1crypten-jwt-secret-key-2026-production

# Configurações de Banco de Dados
DATABASE_URL=postgresql://postgres:password@localhost:5432/1crypten

# Configurações de OKX
OKX_API_KEY_MASTER=sua-api-key-okx
OKX_API_SECRET_MASTER=sua-secret-key-okx
OKX_PASSPHRASE_MASTER=sua-passphrase-okx

# Configurações Gerais
DEBUG=true
APP_NAME=1Crypten
APP_VERSION=1.0.0
PORT=8085
LOG_LEVEL=INFO
"""
        
        try:
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(env_content)
            print(f"✅ Arquivo .env criado em {env_path}")
            print("📝 Por favor, edite o arquivo .env com suas configurações reais")
        except Exception as e:
            print(f"❌ Erro ao criar arquivo .env: {e}")
            return False
    
    return True

def setup_logging():
    """Configura logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('auth_system.log', encoding='utf-8')
        ]
    )
    return logging.getLogger(__name__)

def check_dependencies():
    """Verifica dependências necessárias"""
    try:
        import fastapi
        import sqlalchemy
        import psycopg2
        import bcrypt
        import jwt
        print("✅ Todas as dependências principais estão instaladas")
        return True
    except ImportError as e:
        print(f"❌ Dependência ausente: {e}")
        print("Instale as dependências com: pip install -r requirements.txt")
        return False

def run_migrations():
    """Executa migrações do banco de dados"""
    try:
        from database.migrations.create_auth_tables import migrate_database
        print("Executando migracoes do banco de dados...")
        
        if migrate_database():
            print("Migracoes concluidas com sucesso")
            return True
        else:
            print("Falha nas migracoes")
            return False
    except Exception as e:
        print(f"❌ Erro ao executar migrações: {e}")
        return False

def start_server(mode="production"):
    """Inicia o servidor"""
    try:
        if mode == "development":
            print("Iniciando servidor em modo desenvolvimento...")
            os.system("python auth_main.py")
        else:
            print("Iniciando servidor em modo producao...")
            os.system("python auth_main.py")
    except KeyboardInterrupt:
        print("\n Servidor encerrado pelo usuário")
    except Exception as e:
        print(f"❌ Erro ao iniciar servidor: {e}")

def main():
    """Função principal"""
    parser = argparse.ArgumentParser(description="Sistema de Autenticação 1Crypten")
    parser.add_argument("action", choices=["setup", "migrate", "start"], 
                       help="Ação a ser executada")
    parser.add_argument("--mode", choices=["development", "production"], 
                       default="production", help="Modo de execução")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Modo verbose")
    
    args = parser.parse_args()
    
    # Configurar logging
    logger = setup_logging()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("Sistema de Autenticação 1Crypten")
    print("=" * 40)
    
    if args.action == "setup":
        print("Configurando ambiente...")
        
        if not setup_environment():
            print("Falha na configuracao do ambiente")
            sys.exit(1)
        
        if not check_dependencies():
            print("Dependencias faltando")
            sys.exit(1)
        
        print("Configuracao concluida")
        print("Execute 'python start_auth_system.py migrate' para criar as tabelas do banco de dados")
        
    elif args.action == "migrate":
        print("Executando migracoes...")
        
        if not check_dependencies():
            print("Dependencias faltando")
            sys.exit(1)
        
        if run_migrations():
            print("Migracoes concluidas")
            print("Execute 'python start_auth_system.py start' para iniciar o servidor")
        else:
            print("Falha nas migracoes")
            sys.exit(1)
            
    elif args.action == "start":
        print("Iniciando servidor...")
        start_server(args.mode)

if __name__ == "__main__":
    main()