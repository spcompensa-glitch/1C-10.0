"""
Cleanup Script: Remove 4 ghost positions blocking the Captain
- OPNUSDT (Slot 1)
- MONUSDT (Slot 2)  
- DOTUSDT (Slot 3)
- SUIUSDT (Slot 4)

These positions have negative ROIs (-173% to -250%) and are blocking
the BankrollManager's can_open_new_slot() check.
"""
import asyncio
import logging
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GHOST_CLEANUP")

async def cleanup():
    # 1. Load services
    from services.database_service import database_service
    from services.okx_rest import okx_rest_service

    # Initialize database if needed
    if not database_service.is_active:
        logger.info("🔧 Initializing database service...")
        await database_service.initialize()
    
    # Initialize OKXRest if needed
    if not okx_rest_service.is_initialized:
        logger.info("🔧 Initializing OKXRest...")
        await okx_rest_service.initialize()

    # 2. Show current state
    slots = await database_service.get_active_slots()
    logger.info(f"📊 Current slots state ({len(slots)} slots):")
    for s in slots:
        sym = s.get("symbol") or "EMPTY"
        status = s.get("status_risco") or "LIVRE"
        pnl = s.get("pnl_percent", 0)
        logger.info(f"   Slot {s.get('id')}: {sym} | Status: {status} | PnL: {pnl}%")

    # 3. Track ghost symbols
    ghost_symbols = {s.get("symbol") for s in slots if s.get("symbol") and float(s.get("pnl_percent", 0)) < -100}
    logger.info(f"👻 Ghost symbols detected: {ghost_symbols}")

    # 4. Reset each slot in database_service (Postgres/SQLite)
    reset_data = {
        "symbol": None,
        "side": None,
        "qty": 0.0,
        "entry_price": 0.0,
        "entry_margin": 0.0,
        "current_stop": 0.0,
        "initial_stop": 0.0,
        "target_price": 0.0,
        "liq_price": 0.0,
        "pnl_percent": 0.0,
        "status_risco": "LIVRE",
        "order_id": None,
        "genesis_id": None,
        "slot_type": None,
        "opened_at": None,
        "pensamento": "🧹 GHOST CLEANUP",
        "score": 0,
        "sentinel_first_hit_at": 0.0,
    }

    for slot_id in range(1, 5):
        await database_service.update_slot(slot_id, reset_data)
        logger.info(f"✅ Slot {slot_id} resetado para LIVRE no banco de dados.")

    # 5. Remove ghost symbols from in-memory paper_positions
    initial_count = len(okx_rest_service.paper_positions)
    okx_rest_service.paper_positions = [
        p for p in okx_rest_service.paper_positions
        if (p.get("symbol") or "").upper().replace(".P", "") not in {
            s.replace(".P", "").upper() for s in ghost_symbols
        }
    ]
    removed = initial_count - len(okx_rest_service.paper_positions)
    logger.info(f"🧹 Removidas {removed} posições fantasmas da memória paper_positions.")

    # 6. Also clean moonbags for same symbols
    moon_initial = len(okx_rest_service.paper_moonbags)
    okx_rest_service.paper_moonbags = [
        m for m in okx_rest_service.paper_moonbags
        if (m.get("symbol") or "").upper().replace(".P", "") not in {
            s.replace(".P", "").upper() for s in ghost_symbols
        }
    ]
    moon_removed = moon_initial - len(okx_rest_service.paper_moonbags)
    if moon_removed > 0:
        logger.info(f"🧹 Removidas {moon_removed} moonbags fantasmas da memória.")

    # 7. Reset paper_balance to configured simulated balance
    from config import settings
    okx_rest_service.paper_balance = settings.OKX_SIMULATED_BALANCE
    logger.info(f"💰 Paper balance resetado para ${okx_rest_service.paper_balance:.2f}")

    # 8. Save state to Firestore/Postgres
    await okx_rest_service._save_paper_state()
    logger.info("💾 Estado paper persistido.")

    # 9. Also sync banca status to Firebase/RTDB
    from services.firebase_service import firebase_service
    # Update banca to force $20
    update_data = {
        "configured_balance": settings.OKX_SIMULATED_BALANCE,
        "saldo_total": settings.OKX_SIMULATED_BALANCE,
        "slots_disponiveis": 4,
        "risco_real_percent": 0.0,
        "status": "ONLINE",
    }
    await firebase_service.update_banca_status(update_data)
    logger.info("💰 Banca status sincronizado no Firebase.")

    # 10. Verify final state
    slots_after = await database_service.get_active_slots()
    logger.info(f"\n📊 Slots após limpeza:")
    all_empty = True
    for s in slots_after:
        sym = s.get("symbol") or "EMPTY"
        logger.info(f"   Slot {s.get('id')}: {sym}")
        if s.get("symbol"):
            all_empty = False
    
    positions_after = len(okx_rest_service.paper_positions)
    logger.info(f"\n📊 Posições em memória após limpeza: {positions_after}")
    
    if all_empty and positions_after == 0:
        logger.info("\n✅✅✅ LIMPEZA COMPLETA! Todos os slots estão LIVRES. O Capitão deve começar a abrir ordens agora.")
    else:
        logger.warning(f"\n⚠️ Limpeza parcial. Slots vazios: {all_empty}, Posições memória: {positions_after}")

    return all_empty and positions_after == 0

if __name__ == "__main__":
    success = asyncio.run(cleanup())
    sys.exit(0 if success else 1)
