#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API de Autenticação do Sistema 1Crypten
======================================

Aplicação FastAPI dedicada ao sistema de autenticação e usuários.

Author: Sistema 1Crypten
Version: 1.0
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import uvicorn

# Importar configurações
from config import settings

# Importar rotas
from routes.auth import router as auth_router
from routes.tokens import router as tokens_router

# Importar middlewares
from auth.middleware import setup_middleware

# Configurar logging
log_level = getattr(logging, getattr(settings, 'log_level', 'INFO').upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerenciador de ciclo de vida da aplicação
    """
    logger.info("Iniciando API de Autenticação 1Crypten...")
    
    # Verificar configurações críticas
    try:
        settings.validate_environment()
        logger.info("Configurações validadas com sucesso")
    except Exception as e:
        logger.error(f"Erro de configuração: {e}")
        raise
    
    # Inicializar banco de dados e criar tabelas se não existirem
    try:
        from database.database_service_secure import get_engine, Base
        from database import models_auth  # noqa: F401 - garante que os modelos sejam registrados
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        logger.info("Banco de dados inicializado com sucesso")
    except Exception as e:
        logger.warning(f"Não foi possível inicializar banco de dados: {e}")
    
    yield
    
    logger.info("API de Autenticação 1Crypten encerrada")

# Criar aplicação FastAPI
app = FastAPI(
    title="1Crypten - API de Autenticação",
    version="1.0.0",
    description="API segura de autenticação e gerenciamento de usuários do Sistema 1Crypten",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configurar middlewares
setup_middleware(app)

# Adicionar middlewares adicionais
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if settings.DEBUG else ["1crypten.com", "localhost"]
)

# Manipulador de erros global
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Manipulador de exceções HTTP"""
    logger.error(f"HTTP Error {exc.status_code}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url)
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Manipulador de exceções gerais"""
    logger.error(f"Erro não esperado: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "Ocorreu um erro interno no servidor",
            "path": str(request.url)
        }
    )

# Rotas principais
app.include_router(auth_router, prefix="/api/auth")
app.include_router(tokens_router, prefix="/api")

# Rotas de saúde
@app.get("/health")
async def health_check():
    """Verificação de saúde da API"""
    return {
        "status": "healthy",
        "service": "1Crypten Authentication API",
        "version": "1.0.0",
        "timestamp": "2026-06-01T10:00:00Z"
    }

# Rota raiz
@app.get("/")
async def root():
    """Rota raiz da aplicação"""
    return {
        "message": "Bem-vindo à API de Autenticação 1Crypten",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    uvicorn.run(
        "auth_main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=getattr(settings, 'LOG_LEVEL', 'INFO').lower()
    )