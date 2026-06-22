import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional
from dotenv import load_dotenv

# V110.42.1: Robust .env loading
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(env_path, override=False)

class Settings(BaseSettings):
    # Firebase (Google)
    FIREBASE_CREDENTIALS_PATH: str = "serviceAccountKey.json"
    FIREBASE_DATABASE_URL: Optional[str] = None
    ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "1crypten-admin-key-2026-production")

    # OKX (Única exchange integrada — V110.701: OKX Portfolio Margin)
    OKX_API_KEY: Optional[str] = None
    OKX_API_SECRET: Optional[str] = None
    OKX_INST_TYPE: str = "SWAP" # OKX API: SPOT / MARGIN / SWAP / FUTURES
    OKX_EXECUTION_MODE: str = os.getenv("OKX_EXECUTION_MODE", "PAPER") # "PAPER" = Simulated Execution
    OKX_SIMULATED_BALANCE: float = 100.0 # Padrão
    FACTORY_RESET_V110: bool = False # [V110.29.0] Reset atômico do sistema

    @field_validator('OKX_SIMULATED_BALANCE', mode='before')
    @classmethod
    def parse_simulated_balance(cls, v):
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean in ('false', 'none', 'null', ''):
                return 100.0
            try:
                return float(v_clean)
            except ValueError:
                return 100.0
        return float(v or 100.0)

    # [V28.3] Strip whitespace from critical env vars to prevent 'PAPER ' != 'PAPER' bugs
    @field_validator('OKX_EXECUTION_MODE', mode='before')
    @classmethod
    def strip_execution_mode(cls, v):
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @field_validator('FACTORY_RESET_V110', 'SERVE_STATIC_FRONTEND', 'OKX_TESTNET', mode='before')
    @classmethod
    def parse_testnet(cls, v):
        if isinstance(v, str):
            v_clean = v.strip().lower()
            return v_clean in ('true', '1', 't', 'y', 'yes')
        return bool(v)

    @field_validator('OKX_API_KEY', 'OKX_API_SECRET', 'OKX_API_KEY_MASTER', 'OKX_API_SECRET_MASTER', 'OKX_PASSPHRASE_MASTER', mode='before')
    @classmethod
    def strip_api_keys(cls, v):
        if isinstance(v, str):
            return v.strip() or None
        return v

    # Gemini
    GEMINI_API_KEY: Optional[str] = None
    
    # GLM (ZhipuAI)
    GLM_API_KEY: Optional[str] = None
    
    # OpenRouter (New Primary)
    OPENROUTER_API_KEY: Optional[str] = None
    
    # [HERMES] DeepSeek (Primary Hermes Brain)
    DEEPSEEK_API_KEY: Optional[str] = None
    
    # [V56.0] On-Chain
    ETHERSCAN_API_KEY: str = os.getenv("ETHERSCAN_API_KEY", "YourApiKeyToken")

    # App Logic
    PORT: int = int(os.getenv("PORT", 8085))
    HOST: str = "0.0.0.0"
    SERVE_STATIC_FRONTEND: bool = True
    BACKEND_CORS_ORIGINS: str = ""
    cors_allow_credentials: bool = True
    cors_allow_methods: list = ["*"]
    cors_allow_headers: list = ["*"]

    # JWT Security Configuration
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "1crypten-jwt-secret-2026-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 1 semana

    # [V110.550] OKX Master Account Credentials
    OKX_API_KEY_MASTER: Optional[str] = os.getenv("OKX_API_KEY_MASTER", None)
    OKX_API_SECRET_MASTER: Optional[str] = os.getenv("OKX_API_SECRET_MASTER", os.getenv("OKX_SECRET_KEY", None))
    OKX_PASSPHRASE_MASTER: Optional[str] = os.getenv("OKX_PASSPHRASE_MASTER", os.getenv("OKX_PASSPHRASE", None))

    # NVIDIA AI Configuration - Hermes-Crypten
    NVAPI_KEY: Optional[str] = os.getenv("NVAPI_KEY", None)
    OKX_TESTNET: bool = False

    # User Authentication & Security Configuration
    ENCRYPTION_PASSWORD: str = os.getenv("ENCRYPTION_PASSWORD", "1crypten-encryption-password-2026")
    ENCRYPTION_SALT: str = os.getenv("ENCRYPTION_SALT", "1crypten-encryption-salt-2026")
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_MAX_LENGTH: int = 64
    BCRYPT_ROUNDS: int = 12
    SESSION_TIMEOUT_MINUTES: int = 120

    # [V110.550] MQTT Broker Configs (HiveMQ Cloud / Broker em nuvem gratuito)
    MQTT_BROKER_URL: str = os.getenv("MQTT_BROKER_URL", "broker.hivemq.com")
    MQTT_BROKER_PORT: int = int(os.getenv("MQTT_BROKER_PORT", 1883))
    MQTT_USERNAME: Optional[str] = os.getenv("MQTT_USERNAME", None)
    MQTT_PASSWORD: Optional[str] = os.getenv("MQTT_PASSWORD", None)
    MQTT_TOPIC_PREFIX: str = os.getenv("MQTT_TOPIC_PREFIX", "1crypten/sinal")

    # [V110.550] gRPC Server Settings
    GRPC_SERVER_PORT: int = int(os.getenv("GRPC_SERVER_PORT", 50051))

    # [V110.550] Portfolio Guardian (Master Mirroring & Knife-Drop)
    GUARDIAN_ACTIVATION_TRIGGER: float = float(os.getenv("GUARDIAN_ACTIVATION_TRIGGER", 70.0))
    GUARDIAN_TRAILING_MARGIN: float = float(os.getenv("GUARDIAN_TRAILING_MARGIN", 15.0))

    # [V110.550] Anti-Slippage Engine (Random Jitter)
    ANTI_SLIPPAGE_MAX_JITTER_MS: int = int(os.getenv("ANTI_SLIPPAGE_MAX_JITTER_MS", 350))
    # [V111.2] Máximo de posições simultâneas
    MAX_SLOTS: int = 16
    MAX_SLOTS_LATERAL: int = 16    # [V111.0] Reduzido para banca real de $20.00 (até 16 ordens com margem de 0.50)
    MAX_SLOTS_TRENDING: int = 16   # [V111.0] Reduzido para banca real de $20.00 (até 16 ordens)
    MARGIN_PER_TRADE_LATERAL: float = 0.50   # [V111.0] $0.50 por par para banca de $20.00
    MARGIN_PER_TRADE_TRENDING: float = 0.50  # [V111.0] $0.50 por par para banca de $20.00
    RISK_CAP_PERCENT: float = 0.40  # 40% da banca alocada no total (invariante)
    LEVERAGE: int = 50
    LEVERAGE_RANGING: int = 50    # [V111.0] 50x em todos os cenários (margem pequena)
    LEVERAGE_TRENDING: int = 50   # [V111.0] 50x em todos os cenários
    INITIAL_SLOTS: int = 1
    BREAKEVEN_TRIGGER_PERCENT: float = 5.0 # Increased to 5% ROI to avoid premature exits
    WIN_ROI_THRESHOLD: float = 80.0 # V11.0: ROI mínimo para contar como WIN no ciclo 1/10
    
    # [V111.2] MARKET REGIME FILTER — Filtro de Regime e Direção
    # ADX mínimo para permitir novas entradas (mercado morto = bloqueio total)
    ADX_MIN_ENTRY: float = 22.0
    # ADX mínimo para considerar mercado em tendência (entradas liberadas)
    ADX_TRENDING_THRESHOLD: float = 25.0
    # ADX mínimo para bloquear trades contra-tendência (proteção de SHORTs em bull markets)
    ADX_STRONG_TREND_THRESHOLD: float = 30.0
    # ROI máximo permitido para stop inicial (proteção de banca pequena)
    MAX_INITIAL_STOP_ROI: float = 30.0

    # [DECOR_HUNTER 2.0] Configuração do sistema de pares desgrudados do BTC
    # Número máximo de slots dedicados exclusivamente a sinais DECOR_HUNTER
    DECOR_HUNTER_MAX_SLOTS: int = 8
    # Confiança mínima para um par desgrudado ser considerado com "gás" real
    DECOR_HUNTER_MIN_CONFIDENCE: float = 70.0
    # Intervalo entre varreduras da watchlist (em segundos)
    DECOR_HUNTER_SCAN_INTERVAL: int = 30
    
    # Redis
    REDIS_HOST: str = os.getenv("REDISHOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDISPORT", 6379))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDISPASSWORD", os.getenv("REDIS_PASSWORD", None))
    REDIS_DB: int = 0
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)
    
    # [V110.701] OFFICIAL 40 ELITE MATRIX
    ELITE_40_MATRIX: list = [
        "AVAXUSDT", "PYTHUSDT", "APTUSDT", "SUIUSDT", "OPUSDT", 
        "ARBUSDT", "RENDERUSDT", "NEARUSDT", "INJUSDT", "TIAUSDT", 
        "LINKUSDT", "DOTUSDT", "ADAUSDT", "POLUSDT", "ATOMUSDT", 
        "LTCUSDT", "BCHUSDT", "XLMUSDT", "XRPUSDT", "TRXUSDT",
        "SEIUSDT", "FILUSDT", "FTMUSDT", "AAVEUSDT", "ALGOUSDT", 
        "IMXUSDT", "GALAUSDT", "GRTUSDT", "CRVUSDT", "EGLDUSDT",
        "ONDOUSDT", "FETUSDT", "JUPUSDT", "DYDXUSDT", "LDOUSDT", 
        "ICPUSDT", "STXUSDT", "THETAUSDT", "VETUSDT", "SANDUSDT"
    ]
    
    # [V111.4] RADAR WATCHLIST REDUZIDA (36 pares)
    # Removidos por performance Sandbox negativa: ICPUSDT (-1475%), APTUSDT (-1078%),
    # PYTHUSDT (-977%), LDOUSDT (-734%), RENDERUSDT (-550%). Mantidos apenas pares com ROI > -600% ou WR > 48%.
    RADAR_WATCHLIST: list = [
        "AVAXUSDT", "SUIUSDT", "OPUSDT",
        "ARBUSDT", "NEARUSDT", "INJUSDT", "TIAUSDT",
        "LINKUSDT", "DOTUSDT", "ADAUSDT", "POLUSDT", "ATOMUSDT",
        "LTCUSDT", "BCHUSDT", "XLMUSDT", "XRPUSDT", "TRXUSDT",
        "SEIUSDT", "FILUSDT", "FTMUSDT", "AAVEUSDT", "ALGOUSDT",
        "IMXUSDT", "GALAUSDT", "GRTUSDT", "CRVUSDT", "EGLDUSDT",
        "ONDOUSDT", "FETUSDT", "JUPUSDT", "DYDXUSDT",
        "STXUSDT", "THETAUSDT", "VETUSDT", "SANDUSDT",
        "SOLUSDT"
    ]
    
    # [V111.4] SHORT BIAS — SHORT signals outperform LONG in Sandbox
    # SHORT WR 49.12% vs LONG 47.18%, SHORT PnL -969% vs LONG -2797%
    SHORT_BIAS_ACTIVE: bool = True
    SHORT_BIAS_BOOST: int = 8
    
    # [DECOR_HUNTER 2.0] WATCHLIST EXPANDIDA (94 pares)
    # Usada exclusivamente pelo DECOR_HUNTER para scan de pares desgrudados do BTC.
    # Inclui os 36 da RADAR_WATCHLIST + 58 mid-caps com potencial de desgrude.
    # Removidos ICP, APT, PYTH, LDO, RENDER, CHZ (Sandbox: péssima performance).
    # O scan é feito em batches de 25 para não sobrecarregar a API.
    DECOR_WATCHLIST: list = [
        "AVAXUSDT", "SUIUSDT", "OPUSDT",
        "ARBUSDT", "NEARUSDT", "INJUSDT", "TIAUSDT",
        "LINKUSDT", "DOTUSDT", "ADAUSDT", "POLUSDT", "ATOMUSDT",
        "LTCUSDT", "BCHUSDT", "XLMUSDT", "XRPUSDT", "TRXUSDT",
        "SEIUSDT", "FILUSDT", "FTMUSDT", "AAVEUSDT", "ALGOUSDT",
        "IMXUSDT", "GALAUSDT", "GRTUSDT", "CRVUSDT", "EGLDUSDT",
        "ONDOUSDT", "FETUSDT", "JUPUSDT", "DYDXUSDT",
        "STXUSDT", "THETAUSDT", "VETUSDT", "SANDUSDT",
        "SOLUSDT",
        "UNIUSDT", "SUSHIUSDT", "CAKEUSDT", "COMPUSDT", "MKRUSDT",
        "SNXUSDT", "RUNEUSDT", "DODOUSDT", "GMXUSDT", "WOOUSDT",
        "PERPUSDT", "FXSUSDT", "BALUSDT",
        "EOSUSDT", "HBARUSDT", "MINAUSDT", "KAVAUSDT", "OSMOUSDT",
        "CFXUSDT", "ZILUSDT", "WAVESUSDT", "NEOUSDT", "IOSTUSDT",
        "CELOUSDT", "SKLUSDT", "METISUSDT", "BOBAUSDT",
        "AGIXUSDT", "OCEANUSDT", "LPTUSDT", "BANDUSDT", "API3USDT",
        "TRBUSDT", "AKTUSDT", "NKNUSDT",
        "ARUSDT", "STRKUSDT", "ZROUSDT", "ENAUSDT", "ETHFIUSDT",
        "ALTUSDT", "ZETAUSDT", "WUSDT", "PENDLEUSDT",
        "MANAUSDT", "AXSUSDT", "ENJUSDT",
        "ANKRUSDT", "STORJUSDT", "CVCUSDT", "BATUSDT",
        "KNCUSDT", "ZRXUSDT", "UMAUSDT", "RLCUSDT",
        "BADGERUSDT", "ALPACAUSDT", "CVXUSDT",
    ]

    # [V110.400] MASTER CONTEXT
    MASTER_CONTEXT_ASSETS: list = ["BTCUSDT", "ETHUSDT"]
    
    # [V111] Official Asset Blocklist - Memecoins & Low Liquidity
    # BTCUSDT e ETHUSDT sao apenas monitorados (Master Context), nao operados.
    # SOLUSDT foi removido — esta na RADAR_WATCHLIST e pode ser operado.
    # Adicionados RENDER, ICP e CHZ por performance Sandbox extremamente negativa.
    ASSET_BLOCKLIST: set = {
        'BTCUSDT', 'ETHUSDT',  # Master Context Assets (Monitoring only)
        'PAXGUSDT', 'XAUTUSDT', 'TAOUSDT', 
        'PIPPINUSDT', '1000PEPEUSDT', '1000LUNCUSDT',
        'DOGEUSDT', 'SHIBUSDT', 'FLOKIUSDT', 'BONKUSDT', 'WIFUSDT', 
        'MEMEUSDT', 'PEOPLEUSDT', 'TURBOUSDT', 'POPCATUSDT', 'BRETTUSDT', 
        'MOGUSDT', 'MEWUSDT', 'BOMEUSDT', 'MYROUSDT', 'COQUSDT', 
        'JOEUSDT', 'AIDOGEUSDT', 'SLERFUSDT', 'NPCUSDT', 'NEIROUSDT',
        '1000SHIBUSDT', '1000BONKUSDT', '1000FLOKIUSDT', 'LUNCUSDT', 'USTCUSDT',
        'XAUUSDT', 'XAGUSDT', 'XPDUSDT', 'XPTUSDT', 'WTIUSDT', 'BRENTUSDT',
        'USDEUSDT', 'USDCUSDT', 'EURSUSDT', 'DAIUSDT', 'FDUSDUSDT',
        'BNBUSDT', 'ICPUSDT', 'RENDERUSDT', 'CHZUSDT',
        'DYDXUSDT', 'FILUSDT', 'ALGOUSDT', 'LTCUSDT'
    }

    # Fast API context
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Configurações de Banco de Dados para Autenticação
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./auth.db")

    # Configurações Gerais da API
    APP_NAME: str = os.getenv("APP_NAME", "1Crypten")
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "t", "yes", "y")
    PORT: int = int(os.getenv("PORT", 8085))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO") or "INFO"
    
    def get_cors_origins(self):
        """Obtém origens CORS configuradas"""
        origins = []
        if self.BACKEND_CORS_ORIGINS:
            origins = [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",")]
        # Adicionar origens padrão
        if "localhost" not in origins:
            origins.append("http://localhost:3000")
        if "127.0.0.1" not in origins:
            origins.append("http://127.0.0.1:3000")
        return origins
    
    def validate_environment(self):
        """Valida configurações críticas do ambiente"""
        # Verificar chaves de API necessárias
        required_keys = [
            'JWT_SECRET_KEY',
            'ENCRYPTION_PASSWORD',
            'ENCRYPTION_SALT'
        ]
        
        missing_keys = []
        for key in required_keys:
            if not getattr(self, key, None):
                missing_keys.append(key)
        
        if missing_keys:
            raise ValueError(f"Chaves de ambiente obrigatórias ausentes: {', '.join(missing_keys)}")
        
        # Verificar configurações de segurança
        if len(self.JWT_SECRET_KEY) < 32:
            raise ValueError("JWT_SECRET_KEY deve ter pelo menos 32 caracteres")
        
        if len(self.ENCRYPTION_PASSWORD) < 8:
            raise ValueError("ENCRYPTION_PASSWORD deve ter pelo menos 8 caracteres")
        
        if len(self.ENCRYPTION_SALT) < 8:
            raise ValueError("ENCRYPTION_SALT deve ter pelo menos 8 caracteres")

settings = Settings()
