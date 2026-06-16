# 1CRYPTEN_SPACE_V4.0 - V110.175 Database Service (Railway/Postgres)
import os
import logging
import asyncio
import time
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean, desc, select, update, delete, text

logger = logging.getLogger("DatabaseService")

Base = declarative_base()

class BancaStatus(Base):
    __tablename__ = "banca_status"
    id = Column(Integer, primary_key=True)
    saldo_total = Column(Float, default=0.0)
    saldo_real_okx = Column(Float, default=0.0)  # [V111.3] Saldo real da OKX em REAL mode
    risco_real_percent = Column(Float, default=0.0)
    slots_disponiveis = Column(Integer, default=4)
    configured_balance = Column(Float, default=100.0)
    status = Column(String, default="IDLE")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Slot(Base):
    __tablename__ = "slots"
    id = Column(Integer, primary_key=True) # 1, 2, 3, 4
    symbol = Column(String, nullable=True)
    side = Column(String, nullable=True)
    qty = Column(Float, default=0.0)
    entry_price = Column(Float, default=0.0)
    entry_margin = Column(Float, default=0.0)
    current_stop = Column(Float, default=0.0)
    initial_stop = Column(Float, default=0.0)
    order_id = Column(String, nullable=True)
    target_price = Column(Float, default=0.0)
    leverage = Column(Float, default=50.0)
    slot_type = Column(String, nullable=True)
    status_risco = Column(String, default="LIVRE")
    pnl_percent = Column(Float, default=0.0)
    strategy = Column(String, nullable=True)
    strategy_label = Column(String, nullable=True)
    genesis_id = Column(String, nullable=True)
    opened_at = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Metadados adicionais de auditoria, concorrência e UI
    pensamento = Column(String, nullable=True)
    liq_price = Column(Float, default=0.0)
    structural_target = Column(Float, default=0.0)
    target_extended = Column(Integer, default=0)
    is_ranging_sniper = Column(Boolean, default=False)
    v42_tag = Column(String, default="STANDARD")
    move_room_pct = Column(Float, default=0.0)
    pattern = Column(String, nullable=True)
    unified_confidence = Column(Float, default=50.0)
    fleet_intel = Column(JSON, nullable=True)
    execution_audit = Column(JSON, nullable=True)
    is_reverse_sniper = Column(Boolean, default=False)
    market_regime = Column(String, nullable=True)
    rescue_activated = Column(Boolean, default=False)
    rescue_resolved = Column(Boolean, default=False)
    is_shadow_strike = Column(Boolean, default=False)
    score = Column(Float, default=0.0)
    vision_url = Column(String, nullable=True)
    sentinel_first_hit_at = Column(Float, default=0.0)

class TradeHistory(Base):
    __tablename__ = "trade_history"
    id = Column(Integer, primary_key=True)
    order_id = Column(String, index=True)
    genesis_id = Column(String, index=True)
    symbol = Column(String)
    side = Column(String)
    pnl = Column(Float)
    pnl_percent = Column(Float)
    entry_price = Column(Float)
    exit_price = Column(Float)
    strategy = Column(String)
    close_reason = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    data = Column(JSON) # Metadados completos (Librarian, Oracle, etc)
    vision_url = Column(String, nullable=True)

class Moonbag(Base):
    __tablename__ = "moonbags"
    uuid = Column(String, primary_key=True)
    symbol = Column(String)
    side = Column(String)
    qty = Column(Float)
    entry_price = Column(Float)
    entry_margin = Column(Float, default=0.0)
    current_stop = Column(Float)
    initial_stop = Column(Float, default=0.0)
    target_price = Column(Float, default=0.0)
    leverage = Column(Float, default=50.0)
    order_id = Column(String, nullable=True)
    genesis_id = Column(String, nullable=True)
    slot_type = Column(String, nullable=True)
    strategy = Column(String, nullable=True)
    strategy_label = Column(String, nullable=True)
    opened_at = Column(Float, nullable=True)
    contract_meta = Column(JSON, nullable=True)
    flash_last_action = Column(String, nullable=True)
    flash_last_stop_roi = Column(Float, nullable=True)
    pnl_percent = Column(Float)
    sentinel_first_hit_at = Column(Float, default=0.0)
    promoted_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SandboxTrade(Base):
    __tablename__ = "sandbox_trades"
    id = Column(String, primary_key=True)
    symbol = Column(String, nullable=False)
    strategy = Column(String, nullable=True)
    direction = Column(String, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    max_roi = Column(Float, default=0.0)
    current_roi = Column(Float, default=0.0)
    pnl_pct = Column(Float, default=0.0)
    status = Column(String, default="ACTIVE")
    opened_at = Column(Float, nullable=False)
    closed_at = Column(Float, nullable=True)
    flash_state = Column(JSON, nullable=True)
    contract_meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class RadarPulse(Base):
    __tablename__ = "radar_pulse"
    id = Column(Integer, primary_key=True)
    data = Column(JSON)

class DatabaseService:
    def __init__(self):
        # Em Railway, DATABASE_URL é provido automaticamente (postgres://...)
        # Precisamos converter para postgresql+asyncpg://...
        db_url = os.getenv("DATABASE_URL")
        # V110.176: Ignorar placeholders inválidos do Windows que quebram o SQLAlchemy
        if db_url and ("<sua_url_do_postgres>" in db_url or ("postgres://" not in db_url and "postgresql://" not in db_url)):
            logger.warning(f"DATABASE_URL contains invalid placeholder or scheme '{db_url}'. Ignoring to force local fallback.")
            db_url = None

        if db_url:
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        # Fallback local para desenvolvimento
        if not db_url:
            db_url = "sqlite+aiosqlite:///local_sniper.db"
            logger.warning("DATABASE_URL not found or invalid. Using local SQLite.")

        self.engine = create_async_engine(db_url, echo=False)
        self.AsyncSessionLocal = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.is_active = False

    async def initialize(self):
        """Inicializa as tabelas no banco de dados."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                
                # Executar migrações auto-healing
                if "postgresql" in self.engine.url.drivername or "sqlite" in self.engine.url.drivername:
                    logger.info("🔧 Rodando migrações auto-healing...")
                    from sqlalchemy import text
                    # Definir colunas necessárias com tipos Postgres correspondentes
                    migrations = [
                        ("slots", "entry_margin", "DOUBLE PRECISION"),
                        ("slots", "initial_stop", "DOUBLE PRECISION"),
                        ("slots", "order_id", "TEXT"),
                        ("slots", "target_price", "DOUBLE PRECISION"),
                        ("slots", "leverage", "DOUBLE PRECISION"),
                        ("slots", "slot_type", "TEXT"),
                        ("slots", "strategy", "TEXT"),
                        ("slots", "strategy_label", "TEXT"),
                        ("slots", "genesis_id", "TEXT"),
                        ("slots", "pensamento", "TEXT"),
                        ("slots", "liq_price", "DOUBLE PRECISION"),
                        ("slots", "structural_target", "DOUBLE PRECISION"),
                        ("slots", "target_extended", "INTEGER"),
                        ("slots", "is_ranging_sniper", "BOOLEAN"),
                        ("slots", "v42_tag", "TEXT"),
                        ("slots", "move_room_pct", "DOUBLE PRECISION"),
                        ("slots", "pattern", "TEXT"),
                        ("slots", "unified_confidence", "DOUBLE PRECISION"),
                        ("slots", "fleet_intel", "JSONB"),
                        ("slots", "execution_audit", "JSONB"),
                        ("slots", "is_reverse_sniper", "BOOLEAN"),
                        ("slots", "market_regime", "TEXT"),
                        ("slots", "rescue_activated", "BOOLEAN"),
                        ("slots", "rescue_resolved", "BOOLEAN"),
                        ("slots", "is_shadow_strike", "BOOLEAN"),
                        ("slots", "score", "DOUBLE PRECISION"),
                        ("slots", "t1", "DOUBLE PRECISION"),
                        ("slots", "t2", "DOUBLE PRECISION"),
                        ("slots", "t3", "DOUBLE PRECISION"),
                        ("slots", "t4", "DOUBLE PRECISION"),
                        ("slots", "t5", "DOUBLE PRECISION"),
                        ("slots", "vision_url", "TEXT"),
                        ("trade_history", "vision_url", "TEXT"),
                        ("moonbags", "leverage", "DOUBLE PRECISION"),
                        ("moonbags", "order_id", "TEXT"),
                        ("moonbags", "genesis_id", "TEXT"),
                        ("moonbags", "entry_margin", "DOUBLE PRECISION"),
                        ("moonbags", "initial_stop", "DOUBLE PRECISION"),
                        ("moonbags", "target_price", "DOUBLE PRECISION"),
                        ("moonbags", "slot_type", "TEXT"),
                        ("moonbags", "strategy", "TEXT"),
                        ("moonbags", "strategy_label", "TEXT"),
                        ("moonbags", "opened_at", "DOUBLE PRECISION"),
                        ("moonbags", "contract_meta", "JSONB"),
                        ("moonbags", "flash_last_action", "TEXT"),
                        ("moonbags", "flash_last_stop_roi", "DOUBLE PRECISION"),
                        ("banca_status", "configured_balance", "DOUBLE PRECISION"),
                        ("banca_status", "saldo_real_okx", "DOUBLE PRECISION"),
                        ("slots", "sentinel_first_hit_at", "DOUBLE PRECISION"),
                        ("moonbags", "sentinel_first_hit_at", "DOUBLE PRECISION")
                    ]
                    for table, col, col_type in migrations:
                        try:
                            # SQLite doesn't support 'IF NOT EXISTS' in ALTER TABLE ADD COLUMN
                            if "sqlite" in self.engine.url.drivername:
                                # SQLite alternative: try to add directly, catch exception if it already exists
                                try:
                                    # Translate JSONB to TEXT for SQLite
                                    sqlite_type = "TEXT" if col_type == "JSONB" else col_type
                                    await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {sqlite_type};"))
                                    logger.info(f"✅ Coluna '{col}' adicionada na tabela '{table}' (SQLite).")
                                except Exception as sqlite_err:
                                    if "duplicate column name" in str(sqlite_err).lower() or "already exists" in str(sqlite_err).lower():
                                        pass
                                    else:
                                        raise sqlite_err
                            else:
                                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type};"))
                                logger.info(f"✅ Coluna '{col}' verificada/adicionada na tabela '{table}'.")
                        except Exception as migration_error:
                            logger.warning(f"Erro ao adicionar coluna {col} na tabela {table}: {migration_error}")
            
            self.is_active = True
            logger.info("✅ Database Service initialized successfully (Postgres/Railway).")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Database: {e}")

    async def get_session(self):
        return self.AsyncSessionLocal()

    # --- BANCA STATUS ---
    async def update_banca_status(self, data: dict):
        async with self.AsyncSessionLocal() as session:
            try:
                # Sempre ID 1 para banca única
                obj = await session.get(BancaStatus, 1)
                if not obj:
                    obj = BancaStatus(id=1, **data)
                    session.add(obj)
                else:
                    for key, value in data.items():
                        setattr(obj, key, value)
                await session.commit()
            except Exception as e:
                logger.error(f"Error updating banca status: {e}")

    async def get_banca_status(self):
        async with self.AsyncSessionLocal() as session:
            obj = await session.get(BancaStatus, 1)
            if obj:
                res = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
                # [V125 FIX] Força saldo_total e configured_balance no modo PAPER
                from config import settings
                if settings.OKX_EXECUTION_MODE == "PAPER":
                    res["saldo_total"] = 100.0
                    res["configured_balance"] = 100.0
                return res
            return {"saldo_total": 0, "risco_real_percent": 0, "slots_disponiveis": 4, "status": "UNKNOWN"}

    # --- SLOTS ---
    async def update_slot(self, slot_id: int, data: dict):
        async with self.AsyncSessionLocal() as session:
            try:
                # V110.176: Clean and convert date fields passed as floats/ints to datetime objects
                clean_data = data.copy()
                for key in ["updated_at"]:
                    if key in clean_data:
                        val = clean_data[key]
                        if isinstance(val, (int, float)):
                            if val > 0:
                                clean_data[key] = datetime.utcfromtimestamp(val)
                            else:
                                clean_data[key] = None

                obj = await session.get(Slot, slot_id)
                if not obj:
                    valid_keys = {c.name for c in Slot.__table__.columns}
                    filtered_data = {k: v for k, v in clean_data.items() if k in valid_keys}
                    obj = Slot(id=slot_id, **filtered_data)
                    session.add(obj)
                else:
                    for key, value in clean_data.items():
                        if hasattr(obj, key):
                            setattr(obj, key, value)
                await session.commit()
                
                # V110.175: Emitir update via WebSocket/Redis se disponível
                from .redis_service import redis_service
                await redis_service.publish_update("live_slots", {"slot_id": slot_id, "data": data})
                
            except Exception as e:
                logger.error(f"Error updating slot {slot_id}: {e}")

    async def get_active_slots(self):
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(select(Slot).order_by(Slot.id))
            slots = result.scalars().all()
            rows = [{c.name: getattr(s, c.name) for c in s.__table__.columns} for s in slots]
            return await self._attach_order_projections(rows, phase_hint="SLOT")

    async def get_slot(self, slot_id: int):
        async with self.AsyncSessionLocal() as session:
            obj = await session.get(Slot, slot_id)
            if obj:
                return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
            return None

    async def promote_to_moonbag(self, slot_id: int, emancipation_stop: float = None):
        """[V110.175] EMANCIPAÇÃO: Move slot ativo para tabela Moonbag."""
        slot = await self.get_slot(slot_id)
        if not slot or not slot.get("symbol"):
            return False
            
        # V110.704: UUID determinístico baseado no símbolo e timestamp de abertura para evitar duplicidades
        open_ts = int(slot.get("opened_at") or time.time())
        moon_uuid = f"{slot['symbol'].replace('.P','')}_{open_ts}"
        
        async with self.AsyncSessionLocal() as session:
            try:
                # [V110.704] Impedir duplicação atômica no Postgres
                existing = await session.get(Moonbag, moon_uuid)
                if existing:
                    logger.warning(f"🛡️ [V110.704] Moonbag {slot['symbol']} com UUID {moon_uuid} já existe no Postgres. Pulando inserção.")
                else:
                    current_stop = float(slot.get("current_stop", 0))
                    if emancipation_stop and float(emancipation_stop) > 0:
                        current_stop = float(emancipation_stop)
                    fleet_intel = slot.get("fleet_intel") or {}
                    contract_meta = (
                        fleet_intel.get("contract_info")
                        or fleet_intel.get("contract")
                        or None
                    )

                    moon = Moonbag(
                        uuid=moon_uuid,
                        symbol=slot["symbol"],
                        side=slot.get("side", "BUY"),
                        qty=float(slot.get("qty", 0)),
                        entry_price=float(slot.get("entry_price", 0)),
                        entry_margin=float(slot.get("entry_margin", 0)),
                        current_stop=current_stop,
                        initial_stop=float(slot.get("initial_stop", 0)),
                        target_price=float(slot.get("target_price", 0)),
                        leverage=float(slot.get("leverage") or 50.0),
                        order_id=slot.get("order_id"),
                        genesis_id=slot.get("genesis_id"),
                        slot_type=slot.get("slot_type"),
                        strategy=slot.get("strategy"),
                        strategy_label=slot.get("strategy_label"),
                        opened_at=slot.get("opened_at"),
                        contract_meta=contract_meta,
                        pnl_percent=float(slot.get("pnl_percent", 0)),
                        flash_last_action="EMANCIPACAO",
                        flash_last_stop_roi=110.0,
                    )
                    session.add(moon)
                    await session.commit()
                    logger.info(f"🚀 Moonbag criada para {slot['symbol']} no Postgres (UUID: {moon_uuid})")
                
                # [V110.183] Libera o slot no Postgres após emancipação
                reset_data = {
                    "symbol": None,
                    "side": None,
                    "qty": 0,
                    "entry_margin": 0,
                    "opened_at": None,
                    "order_id": None,
                    "genesis_id": None,
                    "fleet_intel": {},
                    "execution_audit": None,
                    "entry_price": 0,
                    "initial_stop": 0,
                    "current_stop": 0,
                    "target_price": 0,
                    "structural_target": 0,
                    "target_extended": 0,
                    "status_risco": "LIVRE",
                    "pnl_percent": 0,
                    "slot_type": None,
                    "strategy": None,
                    "strategy_label": None,
                    "pattern": None,
                    "unified_confidence": 50,
                    "is_reverse_sniper": False,
                    "market_regime": None,
                    "is_shadow_strike": False,
                    "move_room_pct": 0,
                    "score": 0,
                    "vision_url": None,
                    "pensamento": f"🔄 Emancipado: {slot['symbol']}",
                    "rescue_activated": False,
                    "rescue_resolved": False,
                }
                await self.update_slot(slot_id, reset_data)
                return True
            except Exception as e:
                logger.error(f"Erro ao promover {slot.get('symbol')} para moonbag: {e}")
                return False

    async def get_moonbags(self):
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(select(Moonbag).order_by(desc(Moonbag.promoted_at)))
            moons = result.scalars().all()
            rows = [{c.name: getattr(m, c.name) for c in m.__table__.columns} for m in moons]
            return await self._attach_order_projections(rows, phase_hint="MOONBAG")

    async def get_moonbag(self, moon_uuid: str):
        async with self.AsyncSessionLocal() as session:
            moon = await session.get(Moonbag, moon_uuid)
            if not moon:
                return None
            row = {c.name: getattr(moon, c.name) for c in moon.__table__.columns}
            enriched = await self._attach_order_projections([row], phase_hint="MOONBAG")
            return enriched[0] if enriched else row

    async def _attach_order_projections(self, orders: List[Dict[str, Any]], phase_hint: str):
        """Attach backend-official ROI/stop projection for UI rendering."""
        try:
            from services.okx_ws_public import okx_ws_public_service
            from services.order_projection_service import order_projection_service
        except Exception:
            return orders

        enriched = []
        for order in orders:
            symbol = order.get("symbol")
            entry_price = float(order.get("entry_price") or 0)
            if not symbol or entry_price <= 0:
                enriched.append(order)
                continue

            current_price = 0.0
            try:
                current_price = float(okx_ws_public_service.get_current_price(symbol) or 0)
            except Exception:
                current_price = 0.0

            order["projection"] = await order_projection_service.build_projection(
                order,
                current_price=current_price,
                phase_hint=phase_hint,
            )
            enriched.append(order)
        return enriched

    async def update_moonbag(self, moon_uuid: str, data: dict):
        """[V110.999] Atualiza os dados de uma Moonbag no Postgres."""
        async with self.AsyncSessionLocal() as session:
            try:
                moon = await session.get(Moonbag, moon_uuid)
                if moon:
                    valid_keys = {c.name for c in Moonbag.__table__.columns}
                    for key, value in data.items():
                        if key not in valid_keys:
                            continue
                        if key in {
                            "qty", "entry_price", "entry_margin", "current_stop",
                            "initial_stop", "target_price", "leverage",
                            "pnl_percent", "opened_at", "sentinel_first_hit_at",
                            "flash_last_stop_roi",
                        } and value is not None:
                            value = float(value)
                        setattr(moon, key, value)
                    moon.updated_at = datetime.utcnow()
                    await session.commit()
                    logger.info(f"🌔 Moonbag {moon_uuid} atualizada no Postgres.")
                    return True
                else:
                    logger.warning(f"⚠️ Moonbag {moon_uuid} não encontrada para atualização no Postgres.")
                    return False
            except Exception as e:
                logger.error(f"Erro ao atualizar Moonbag no Postgres: {e}")
                return False

    async def remove_moonbag(self, moon_uuid: str):
        """[V110.999] Remove uma Moonbag do Postgres."""
        async with self.AsyncSessionLocal() as session:
            try:
                moon = await session.get(Moonbag, moon_uuid)
                if moon:
                    await session.delete(moon)
                    await session.commit()
                    logger.info(f"🌔 Moonbag {moon_uuid} deletada do Postgres.")
                    return True
                return False
            except Exception as e:
                logger.error(f"Erro ao deletar Moonbag do Postgres: {e}")
                return False

    async def get_vault_cycle(self):
        return {}

    async def reset_system_data(self):
        """Purga total: limpa slots, moonbags, trade_history, order_genesis, banca=$100."""
        try:
            async with self.AsyncSessionLocal() as session:
                # 1. Limpar trade_history
                await session.execute(delete(TradeHistory))
                
                # 2. Limpar moonbags
                await session.execute(delete(Moonbag))
                
                # 3. Limpar order_genesis (se existir)
                try:
                    await session.execute(text("DELETE FROM order_genesis"))
                except:
                    pass
                
                # 4. Resetar slots para LIVRE
                now = datetime.utcnow()
                await session.execute(
                    update(Slot).values(
                        symbol=None,
                        side=None,
                        qty=0.0,
                        entry_price=0.0,
                        entry_margin=0.0,
                        current_stop=0.0,
                        initial_stop=0.0,
                        target_price=0.0,
                        liq_price=0.0,
                        structural_target=0.0,
                        target_extended=0,
                        pnl_percent=0.0,
                        status_risco='LIVRE',
                        order_id=None,
                        genesis_id=None,
                        slot_type=None,
                        strategy=None,
                        strategy_label=None,
                        pattern=None,
                        unified_confidence=50.0,
                        fleet_intel={},
                        execution_audit=None,
                        is_reverse_sniper=False,
                        market_regime=None,
                        rescue_activated=False,
                        rescue_resolved=False,
                        is_shadow_strike=False,
                        move_room_pct=0.0,
                        v42_tag='STANDARD',
                        vision_url=None,
                        pensamento='ZERO RESET',
                        score=0,
                        opened_at=None,
                        sentinel_first_hit_at=0.0,
                        updated_at=now
                    )
                )
                
                # 5. Resetar banca para a banca simulada configurada (default $20.00)
                from config import settings
                target_balance = getattr(settings, "OKX_SIMULATED_BALANCE", 20.0)
                banca = await session.get(BancaStatus, 1)
                if banca:
                    banca.saldo_total = target_balance
                    banca.configured_balance = target_balance
                    banca.status = 'ZERO_RESET'
                    banca.risco_real_percent = 0.0
                    banca.updated_at = now
                else:
                    session.add(BancaStatus(
                        id=1,
                        saldo_total=target_balance,
                        configured_balance=target_balance,
                        status='ZERO_RESET',
                        risco_real_percent=0.0,
                        slots_disponiveis=4
                    ))
                
                # 6. Resetar vault_cycles (se existir)
                try:
                    await session.execute(text("""
                        UPDATE vault_cycles 
                        SET sniper_wins = 0, cycle_profit = 0.0, cycle_losses = 0,
                            total_trades_cycle = 0, accumulated_vault = 0.0
                        WHERE id = 1
                    """))
                except:
                    pass
                
                await session.commit()
                logger.info(f"System data reset complete - all slots LIVRE, bank ${target_balance:.2f}, history cleared.")
                return True
        except Exception as e:
            logger.error(f"Error resetting system data: {e}")
            return False

    # --- TRADE HISTORY ---
    async def log_trade(self, trade_data: dict):
        async with self.AsyncSessionLocal() as session:
            try:
                # [V110.184] Converte qualquer datetime para string ISO no campo JSONB de metadados
                clean_data = {}
                for k, v in trade_data.items():
                    if hasattr(v, "isoformat"):
                        clean_data[k] = v.isoformat()
                    else:
                        clean_data[k] = v
                
                # Trata e converte o timestamp tipado para DateTime do SQLAlchemy
                ts_val = trade_data.get("timestamp")
                if isinstance(ts_val, str):
                    try:
                        from datetime import datetime as dt
                        ts_val = dt.fromisoformat(ts_val.replace("Z", "+00:00"))
                    except:
                        ts_val = None
                
                if isinstance(ts_val, datetime):
                    if ts_val.tzinfo is not None:
                        ts_val = ts_val.replace(tzinfo=None)
                else:
                    ts_val = datetime.utcnow()
                
                order_id = str(trade_data.get("order_id")) if trade_data.get("order_id") else None
                existing = None
                if order_id:
                    result = await session.execute(
                        select(TradeHistory).where(TradeHistory.order_id == order_id).limit(1)
                    )
                    existing = result.scalar_one_or_none()

                new_trade = existing or TradeHistory(
                    order_id=order_id,
                    genesis_id=trade_data.get("genesis_id"),
                    symbol=trade_data.get("symbol"),
                    side=trade_data.get("side"),
                    pnl=float(trade_data.get("pnl", 0)),
                    pnl_percent=float(trade_data.get("pnl_percent", 0)),
                    entry_price=float(trade_data.get("entry_price", 0)),
                    exit_price=float(trade_data.get("exit_price", 0)),
                    strategy=trade_data.get("strategy"),
                    close_reason=trade_data.get("close_reason"),
                    timestamp=ts_val,
                    data=clean_data,
                    vision_url=trade_data.get("vision_url")
                )
                if existing:
                    new_trade.genesis_id = trade_data.get("genesis_id")
                    new_trade.symbol = trade_data.get("symbol")
                    new_trade.side = trade_data.get("side")
                    new_trade.pnl = float(trade_data.get("pnl", 0))
                    new_trade.pnl_percent = float(trade_data.get("pnl_percent", 0))
                    new_trade.entry_price = float(trade_data.get("entry_price", 0))
                    new_trade.exit_price = float(trade_data.get("exit_price", 0))
                    new_trade.strategy = trade_data.get("strategy")
                    new_trade.close_reason = trade_data.get("close_reason")
                    new_trade.timestamp = ts_val
                    new_trade.data = clean_data
                    new_trade.vision_url = trade_data.get("vision_url")
                else:
                    session.add(new_trade)
                await session.commit()
                logger.info(f"✅ Trade logged in Postgres: {trade_data.get('symbol')}")
            except Exception as e:
                logger.error(f"Error logging trade: {e}")

    async def get_trade_history(self, limit: int = 50, page: int = 1, symbol: str = None, start_date: str = None, end_date: str = None):
        async with self.AsyncSessionLocal() as session:
            try:
                stmt = select(TradeHistory)
                if symbol:
                    stmt = stmt.where(TradeHistory.symbol == symbol.upper())
                if start_date:
                    try:
                        from datetime import datetime as dt
                        sd = dt.fromisoformat(start_date.replace("Z", "+00:00")).replace(tzinfo=None)
                        stmt = stmt.where(TradeHistory.timestamp >= sd)
                    except:
                        pass
                if end_date:
                    try:
                        from datetime import datetime as dt
                        ed = dt.fromisoformat(end_date.replace("Z", "+00:00")).replace(tzinfo=None)
                        stmt = stmt.where(TradeHistory.timestamp <= ed)
                    except:
                        pass
                
                offset = (page - 1) * limit
                stmt = stmt.order_by(desc(TradeHistory.timestamp)).offset(offset).limit(limit)
                result = await session.execute(stmt)
                trades = result.scalars().all()
                return [{c.name: getattr(t, c.name) for c in t.__table__.columns} for t in trades]
            except Exception as e:
                logger.error(f"Error fetching trade history from database: {e}")
                return []

    # --- RADAR PULSE PERSISTENCE ---
    async def update_radar_pulse(self, data: dict):
        async with self.AsyncSessionLocal() as session:
            try:
                obj = await session.get(RadarPulse, 1)
                if not obj:
                    obj = RadarPulse(id=1, data=data)
                    session.add(obj)
                else:
                    obj.data = data
                await session.commit()
                logger.info("📡 Radar pulse persisted in Postgres successfully.")
            except Exception as e:
                logger.error(f"Error updating radar pulse in database: {e}")

    async def get_radar_pulse(self):
        async with self.AsyncSessionLocal() as session:
            try:
                obj = await session.get(RadarPulse, 1)
                if obj:
                    return obj.data
            except Exception as e:
                logger.error(f"Error getting radar pulse from database: {e}")
            return None

    async def save_sandbox_trade(self, trade_data: dict):
        async with self.AsyncSessionLocal() as session:
            try:
                obj = await session.get(SandboxTrade, trade_data.get("id"))
                if not obj:
                    obj = SandboxTrade(**trade_data)
                    session.add(obj)
                    await session.commit()
                    logger.info(f"🧪 Sandbox trade {trade_data.get('id')} saved in Postgres.")
                    return True
            except Exception as e:
                logger.error(f"Error saving sandbox trade in database: {e}")
            return False

    async def get_sandbox_trades(self, active_only: bool = False):
        async with self.AsyncSessionLocal() as session:
            try:
                if active_only:
                    q = select(SandboxTrade).where(SandboxTrade.status == "ACTIVE").order_by(desc(SandboxTrade.opened_at))
                else:
                    q = select(SandboxTrade).order_by(desc(SandboxTrade.opened_at))
                res = await session.execute(q)
                return res.scalars().all()
            except Exception as e:
                logger.error(f"Error getting sandbox trades: {e}")
            return []

    async def get_sandbox_trade(self, trade_id: str):
        async with self.AsyncSessionLocal() as session:
            try:
                return await session.get(SandboxTrade, trade_id)
            except Exception as e:
                logger.error(f"Error getting sandbox trade {trade_id}: {e}")
            return None

    async def update_sandbox_trade(self, trade_id: str, data: dict):
        async with self.AsyncSessionLocal() as session:
            try:
                obj = await session.get(SandboxTrade, trade_id)
                if obj:
                    for k, v in data.items():
                        if hasattr(obj, k):
                            setattr(obj, k, v)
                    await session.commit()
                    return True
            except Exception as e:
                logger.error(f"Error updating sandbox trade {trade_id}: {e}")
            return False

    async def clear_sandbox_trades(self):
        async with self.AsyncSessionLocal() as session:
            try:
                q = delete(SandboxTrade)
                await session.execute(q)
                await session.commit()
                logger.info("🧪 Sandbox trades database table cleared.")
                return True
            except Exception as e:
                logger.error(f"Error clearing sandbox trades: {e}")
            return False

database_service = DatabaseService()
