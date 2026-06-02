#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Versão simplificada da API de Autenticação 1Crypten
==================================================

Versão simplificada usando SQLite para testes locais.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uvicorn
from datetime import datetime, timedelta
import jwt
from typing import Optional, Dict, Any

# Configurações simples
SECRET_KEY = "1crypten-jwt-secret-key-2026-production-simplified"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 1 semana

# Banco de dados simples em memória
users_db = {
    "admin": {
        "username": "admin",
        "email": "admin@1crypten.com",
        "password_hash": "hashed_admin_password",
        "role": "admin",
        "is_active": True,
        "created_at": "2026-06-01 10:00:00"
    }
}

# Cache de tokens simples
token_cache = {}

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Cria token de acesso"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verifica token JWT"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.JWTError:
        return None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciador de ciclo de vida da aplicação"""
    logging.info("Iniciando API de Autenticação 1Crypten (Simplificada)...")
    
    # Criar usuário admin se não existir
    if "admin" not in users_db:
        users_db["admin"] = {
            "username": "admin",
            "email": "admin@1crypten.com",
            "password_hash": "hashed_admin_password",
            "role": "admin",
            "is_active": True,
            "created_at": "2026-06-01 10:00:00"
        }
    
    yield
    
    logging.info("API de Autenticação 1Crypten encerrada")

# Criar aplicação FastAPI
app = FastAPI(
    title="1Crypten - API de Autenticação (Simplificada)",
    version="1.0.0",
    description="API simplificada de autenticação para testes locais",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configurar middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Manipulador de erros global
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Manipulador de exceções HTTP"""
    logging.error(f"HTTP Error {exc.status_code}: {exc.detail}")
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
    logging.error(f"Erro não esperado: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "Ocorreu um erro interno no servidor",
            "path": str(request.url)
        }
    )

# Modelos
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: Dict[str, Any]

class RegisterRequest(BaseModel):
    username: str
    email: Optional[str] = None
    password: str
    confirm_password: str

# Rotas
@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: Request, login_data: LoginRequest):
    """Login de usuário"""
    try:
        # Verificar se o usuário existe
        user = users_db.get(login_data.username)
        if not user:
            logging.warning(f"Tentativa de login falha: usuário {login_data.username} não existe")
            raise HTTPException(
                status_code=401,
                detail="Usuário ou senha inválidos"
            )

        if not user["is_active"]:
            logging.warning(f"Tentativa de login falha: usuário {login_data.username} inativo")
            raise HTTPException(
                status_code=401,
                detail="Usuário inativo"
            )

        # Verificar senha (simplificado)
        if login_data.password != "admin123" and login_data.username != "admin":
            logging.warning(f"Tentativa de login falha: senha incorreta para {login_data.username}")
            raise HTTPException(
                status_code=401,
                detail="Usuário ou senha inválidos"
            )

        # Criar tokens
        user_data = {
            "sub": user["username"],
            "role": user["role"],
            "email": user["email"],
            "user_id": user["username"]
        }

        access_token = create_access_token(user_data)
        refresh_token = create_access_token(user_data, expires_delta=timedelta(days=7))

        # Registrar login bem sucedido
        logging.info(f"Login bem sucedido para usuário: {login_data.username}")

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Erro no login: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro interno no login"
        )

@app.post("/api/auth/register")
async def register(register_data: RegisterRequest):
    """Registro de novo usuário"""
    try:
        # Verificar se username já existe
        if register_data.username in users_db:
            raise HTTPException(
                status_code=400,
                detail="Username já existe"
            )

        # Criar novo usuário
        new_user = {
            "username": register_data.username,
            "email": register_data.email,
            "password_hash": "hashed_password",
            "role": "user",
            "is_active": True,
            "created_at": datetime.utcnow().isoformat()
        }

        users_db[register_data.username] = new_user

        logging.info(f"Novo usuário criado: {register_data.username}")

        return {
            "message": "Usuário criado com sucesso",
            "user": new_user
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Erro no registro: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro interno no registro"
        )

security = HTTPBearer()

@app.get("/api/auth/me")
async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Obtém perfil do usuário atual"""
    try:
        token = credentials.credentials
        payload = verify_token(token)
        if not payload:
            raise HTTPException(
                status_code=401,
                detail="Token inválido"
            )

        username = payload.get("sub")
        user = users_db.get(username)
        if not user:
            raise HTTPException(
                status_code=401,
                detail="Usuário não encontrado"
            )

        return user

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Erro ao obter perfil: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao obter perfil"
        )

@app.post("/api/auth/logout")
async def logout():
    """Logout de usuário"""
    try:
        logging.info("Logout realizado")
        return {"message": "Logout realizado com sucesso"}

    except Exception as e:
        logging.error(f"Erro no logout: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erro no logout"
        )

# Rotas de saúde
@app.get("/health")
async def health_check():
    """Verificação de saúde da API"""
    return {
        "status": "healthy",
        "service": "1Crypten Authentication API (Simplificada)",
        "version": "1.0.0",
        "timestamp": "2026-06-01T10:00:00Z"
    }

# Rota raiz
@app.get("/")
async def root():
    """Rota raiz da aplicação"""
    return {
        "message": "Bem-vindo à API de Autenticação 1Crypten (Simplificada)",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    uvicorn.run(
        "auth_main_simple:app",
        host="0.0.0.0",
        port=8086,  # Usar porta diferente para não conflitar
        reload=False,
        log_level="info"
    )