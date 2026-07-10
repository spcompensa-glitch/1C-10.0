# migrate_db.py
import asyncio
import os
import sys
import logging
from sqlalchemy import text

# Adicionar o diretório backend ao sys.path para poder importar database_service
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = current_dir
services_dir = os.path.join(backend_dir, "services")
sys.path.append(backend_dir)
sys.path.append(services_dir)

import database_service
from database_service import DatabaseService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Migration")

async def migrate():
    # Garantir que a DATABASE_URL do Railway seja usada se estiver disponível no .env
    env_path = os.path.join(backend_dir, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    db_url = line.split("=", 1)[1].strip()
                    os.environ["DATABASE_URL"] = db_url
                    logger.info("📍 Usando DATABASE_URL do arquivo .env")
                    break

    db = DatabaseService()
    
    # Define columns to add
    # Format: (table, column, type)
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
        ("moonbags", "opened_at", "DOUBLE PRECISION"),
        ("banca_status", "configured_balance", "DOUBLE PRECISION"),
        ("slots", "sentinel_first_hit_at", "DOUBLE PRECISION"),
        ("moonbags", "sentinel_first_hit_at", "DOUBLE PRECISION"),
        ("sandbox_swing_trades", "mirror_order_id", "TEXT"),
        ("sandbox_swing_trades", "swing_tf", "TEXT"),
        ("sandbox_swing_trades", "explosion_score", "DOUBLE PRECISION"),
        ("sandbox_swing_trades", "explosion_signals", "JSONB")
    ]


    async with db.engine.begin() as conn:
        for table, col, col_type in migrations:
            try:
                logger.info(f"Adding column {col} to table {table}...")
                # PostgreSQL syntax for ADD COLUMN IF NOT EXISTS
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type};"))
                logger.info(f"✅ Column {col} added or already exists in {table}.")
            except Exception as e:
                logger.error(f"❌ Error adding {col} to {table}: {e}")

    logger.info("🚀 Migration completed.")

if __name__ == "__main__":
    asyncio.run(migrate())
