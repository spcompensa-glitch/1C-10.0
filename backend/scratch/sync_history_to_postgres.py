# -*- coding: utf-8 -*-
import sys
import os
import asyncio
import logging
from datetime import datetime

# Adiciona o diretório pai (backend) ao sys.path para carregar os módulos corretamente
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# Configura o logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SyncHistoryToPostgres")

from services.database_service import database_service, TradeHistory
from services.firebase_service import firebase_service
from sqlalchemy import select

async def main():
    logger.info("Initializing services...")
    # Inicializa Firebase
    await firebase_service.initialize()
    # Inicializa Postgres
    await database_service.initialize()

    if not firebase_service.is_active:
        logger.error("❌ Firebase is not active. Please check the configurations.")
        return

    logger.info("📡 Fetching trade history from Firebase Firestore...")
    # Busca os últimos 500 trades do Firebase
    trades = await firebase_service.get_trade_history(limit=500)
    logger.info(f"Retrieved {len(trades)} trades from Firebase.")

    if not trades:
        logger.warning("No trades found in Firebase.")
        return

    migrated_count = 0
    duplicate_count = 0

    async with database_service.AsyncSessionLocal() as session:
        for t in trades:
            order_id = t.get("order_id")
            symbol = t.get("symbol", "UNKNOWN")
            
            if not order_id:
                # Se não tem order_id, gera um determinístico para evitar duplicados
                open_ts = int(t.get("opened_at") or t.get("created_at") or 0)
                order_id = f"gen_{symbol.replace('.P','')}_{open_ts}"
                t["order_id"] = order_id

            # 1. Verifica se já existe no Postgres
            result = await session.execute(select(TradeHistory).where(TradeHistory.order_id == str(order_id)))
            existing = result.scalars().first()

            if existing:
                duplicate_count += 1
                logger.debug(f"Skipping duplicate trade: {symbol} (Order ID: {order_id})")
                continue

            # 2. Prepara o payload do Postgres
            ts_val = t.get("timestamp")
            if ts_val and isinstance(ts_val, str):
                try:
                    timestamp_dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
                except Exception:
                    timestamp_dt = datetime.utcnow()
            else:
                timestamp_dt = datetime.utcnow()

            try:
                new_trade = TradeHistory(
                    order_id=str(order_id),
                    genesis_id=t.get("genesis_id"),
                    symbol=symbol,
                    side=t.get("side"),
                    pnl=float(t.get("pnl", 0) or 0),
                    pnl_percent=float(t.get("pnl_percent", 0) or 0),
                    entry_price=float(t.get("entry_price", 0) or 0),
                    exit_price=float(t.get("exit_price", 0) or 0),
                    strategy=t.get("strategy") or t.get("slot_type", "SNIPER"),
                    close_reason=t.get("close_reason"),
                    timestamp=timestamp_dt,
                    data=t
                )
                session.add(new_trade)
                migrated_count += 1
                logger.info(f"✅ Migrating trade: {symbol} (Order ID: {order_id}) | PnL: ${new_trade.pnl:.2f}")
            except Exception as item_err:
                logger.error(f"❌ Error preparing trade {symbol} ({order_id}): {item_err}")

        if migrated_count > 0:
            logger.info("💾 Committing transaction to PostgreSQL...")
            await session.commit()
            logger.info("Transaction committed successfully!")
        else:
            logger.info("No new trades to commit.")

    logger.info(f"🏁 Sync Complete: {migrated_count} migrated, {duplicate_count} skipped as duplicates.")

if __name__ == "__main__":
    asyncio.run(main())
