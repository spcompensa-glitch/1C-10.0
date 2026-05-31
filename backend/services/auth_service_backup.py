import os
import time
import asyncio
import jwt
from datetime import datetime, timedelta
from typing import Optional, Union, Any
from passlib.context import CryptContext
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from services.firebase_service import firebase_service
import logging

logger = logging.getLogger("AuthService")

# Configurações de Segurança
from services.secrets import secrets_manager

SECRET_KEY = secrets_manager.get_jwt_secret()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 Semana de sessão

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

# Cache de Sessão Efêmera (Em Memória RAM apenas)
# Guarda a chave do cofre do usuário enquanto ele está logado.
VAULT_SESSIONS = {} # {username: vault_password_hash}

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

class User(BaseModel):
    username: str # Este será o handle @nome.10d
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    role: str = "user"

class UserInDB(User):
    hashed_password: str

class AuthService:
    def verify_password(self, plain_password, hashed_password):
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password):
        return pwd_context.hash(password)

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    def set_vault_session(self, username: str, vault_password: str):
        """Armazena a chave de descriptografia temporariamente na RAM"""
        VAULT_SESSIONS[username] = {
            "key": vault_password,
            "expires": time.time() + (60 * 60 * 24) # 24h
        }

    def get_vault_session(self, username: str) -> Optional[str]:
        session = VAULT_SESSIONS.get(username)
        if session and session["expires"] > time.time():
            return session["key"]
        return None

    async def get_user(self, username: str) -> Optional[UserInDB]:
        """Busca usuário no Firestore pelo handle (@nome.10d)"""
        if not firebase_service.is_active:
            await firebase_service.initialize()
            
        try:
            # Buscamos na coleção 'users' onde o ID é o username (ou um campo handle)
            user_doc = await asyncio.to_thread(firebase_service.db.collection("users").document(username).get)
            if user_doc.exists:
                return UserInDB(**user_doc.to_dict())
        except Exception as e:
            logger.error(f"Erro ao buscar usuário {username}: {e}")
        return None

    async def register_user(self, user_data: dict):
        """Registra novo usuário no Firestore"""
        username = user_data.get("username")
        if await self.get_user(username):
            raise HTTPException(status_code=400, detail="Handle já registrado.")
            
        hashed = self.get_password_hash(user_data["password"])
        del user_data["password"]
        user_data["hashed_password"] = hashed
        user_data["created_at"] = time.time()
        user_data["role"] = user_data.get("role", "user")
        
        try:
            await asyncio.to_thread(firebase_service.db.collection("users").document(username).set, user_data)
            return True
        except Exception as e:
            logger.error(f"Erro no registro: {e}")
            return False

auth_service = AuthService()

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)):
    from config import settings
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # [V110.140] SOVEREIGN BYPASS PROTOCOL - Restore Legacy UI Access
    # Allows access from localhost/DEBUG without JWT Token or with invalid tokens
    if settings.DEBUG:
        SOVEREIGN_USER = User(username="Sovereign", role="admin", email="admin@1crypten.space")
        try:
            # Caso 1: Sem token ou token explicitamente nulo da UI
            if not token or token in ["undefined", "null", "None"]:
                logger.info("🔑 [SOVEREIGN-BYPASS] No token found. Granting access to Sovereign.")
                return SOVEREIGN_USER
                
            # Caso 2: Tenta validar o token se ele existir
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username:
                user = await auth_service.get_user(username=username)
                if user: 
                    return user
            
            # Caso 3: Token decodificado mas usuário não existe no banco
            logger.warning(f"🔑 [SOVEREIGN-BYPASS] Token valid but user '{username}' not found. Using Sovereign.")
            return SOVEREIGN_USER
            
        except Exception as e:
            # Caso 4: Token inválido ou expirado
            logger.info(f"🔑 [SOVEREIGN-BYPASS] JWT Error ({str(e)}). Granting access to Sovereign.")
            return SOVEREIGN_USER

    # Standard Production Auth Flow
    try:
        if not token:
            raise credentials_exception
            
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except Exception:
        raise credentials_exception
        
    user = await auth_service.get_user(username=token_data.username)
    if user is None:
        raise credentials_exception
    return user
