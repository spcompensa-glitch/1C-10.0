"""
NUCLEAR RESET COMPLETO — V111.0
=================================
Script standalone para resetar TODO o sistema de produção:
  ✅ PostgreSQL   (trade_history, moonbags, slots, banca)
  ✅ Redis        (FLUSHDB — tickers, CVD, OI, LS ratios, locks)
  ✅ Firebase RTDB (active_slots, vault_history, banca)
  ✅ Firestore     (paper_engine)
  ✅ Memória RAM   (paper_positions, paper_moonbags, estado do Capitão, BankrollManager)

Uso:
    python backend/nuclear_reset_complete.py

Requer variáveis de ambiente no .env ou exportadas:
    DATABASE_URL              — PostgreSQL (Railway)
    REDIS_URL                 — Redis (opcional, fallback para MockRedis)
    FIREBASE_CREDENTIALS_PATH — caminho para serviceAccountKey.json
    FIREBASE_DATABASE_URL     — URL do Firebase RTDB
    OKX_SIMULATED_BALANCE     — valor da banca após reset (default: 100.0)
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("NUCLEAR_RESET")


async def reset_postgres(database_service) -> list:
    """Limpa PostgreSQL: trade_history, moonbags, slots, banca."""
    report = []
    try:
        await database_service.initialize()
        success = await database_service.reset_system_data()
        if success:
            report.append("✅ PostgreSQL: trade_history, moonbags, slots zerados. Banca resetada para $100.")
        else:
            report.append("⚠️ PostgreSQL: reset_system_data() retornou False.")
    except Exception as e:
        report.append(f"❌ PostgreSQL: erro — {e}")
    return report


async def reset_redis(redis_service) -> list:
    """Limpa Redis: FLUSHDB para limpar todos os caches."""
    report = []
    try:
        redis_client = redis_service.client
        if hasattr(redis_client, "flushdb") and callable(getattr(redis_client, "flushdb", None)):
            await redis_client.flushdb()
            report.append("✅ Redis FLUSHDB executado — todos os caches limpos.")
        else:
            # MockRedis fallback — limpa os caches em memória
            from services.redis_service import _LOCAL_CACHE, _LOCAL_EXPIRY
            _LOCAL_CACHE.clear()
            _LOCAL_EXPIRY.clear()
            report.append("✅ Redis (Mock/In-Memory) caches limpos.")
    except Exception as e:
        report.append(f"⚠️ Redis reset parcial: {e}")
    return report


async def reset_firebase(firebase_service, target_balance: float) -> list:
    """Limpa Firebase RTDB e Firestore."""
    report = []

    # --- Firestore: paper_engine ---
    try:
        if firebase_service.is_active:
            clean_state = {
                "positions": [],
                "moonbags": [],
                "balance": target_balance,
                "history": [],
            }
            # Tenta via update_paper_state se existir
            if hasattr(firebase_service, "update_paper_state") and callable(firebase_service.update_paper_state):
                await firebase_service.update_paper_state(clean_state)
                report.append("✅ Firestore paper_engine zerado.")
            else:
                # Fallback direto no Firestore
                await asyncio.to_thread(
                    firebase_service.db.collection("paper_engine").document("state").set, clean_state
                )
                report.append("✅ Firestore paper_engine zerado (fallback direto).")
        else:
            report.append("⚠️ Firestore não ativo — SDK Firebase não inicializado.")
    except Exception as e:
        report.append(f"⚠️ Firestore reset parcial: {e}")

    # --- RTDB: active_slots, vault_history, banca ---
    try:
        if firebase_service.rtdb:
            await asyncio.to_thread(firebase_service.rtdb.child("active_slots").delete)
            await asyncio.to_thread(firebase_service.rtdb.child("vault_history").delete)
            await asyncio.to_thread(
                firebase_service.rtdb.child("banca").update,
                {"configured_balance": target_balance, "pnl_realized": 0.0},
            )
            # Limpa também radar_pulse e system_state para garantir
            try:
                await asyncio.to_thread(firebase_service.rtdb.child("radar_pulse").delete)
                await asyncio.to_thread(firebase_service.rtdb.child("system_state").delete)
            except Exception:
                pass
            report.append(f"✅ Firebase RTDB zerado (banca=${target_balance:.2f}).")
        else:
            report.append("⚠️ Firebase RTDB não disponível.")
    except Exception as e:
        report.append(f"⚠️ Firebase RTDB reset parcial: {e}")

    return report


async def reset_memory(okx_rest_service, bankroll_manager, captain_agent, bankroll_guardian, target_balance: float) -> list:
    """Limpa toda a memória volátil dos agentes."""
    report = []

    # --- OKX REST Service ---
    old_pos = len(getattr(okx_rest_service, "paper_positions", []))
    old_moon = len(getattr(okx_rest_service, "paper_moonbags", []))
    okx_rest_service.paper_positions = []
    okx_rest_service.paper_moonbags = []
    okx_rest_service.paper_balance = target_balance
    report.append(f"✅ RAM: {old_pos} posições e {old_moon} moonbags removidas.")

    # --- Bankroll Manager ---
    bankroll_manager.pending_slots.clear()
    if hasattr(bankroll_manager, "recent_openings"):
        bankroll_manager.recent_openings.clear()
    if hasattr(bankroll_manager, "recently_closed"):
        bankroll_manager.recently_closed.clear()
    if hasattr(bankroll_manager, "last_seen_exchange"):
        bankroll_manager.last_seen_exchange.clear()
    if hasattr(bankroll_manager, "ghost_tracker"):
        bankroll_manager.ghost_tracker.clear()
    if hasattr(bankroll_manager, "active_slot_memory"):
        bankroll_manager.active_slot_memory.clear()
    report.append("✅ BankrollManager: pending_slots, recent_openings e ghost trackers limpos.")

    # --- Captain Agent ---
    try:
        snapshot = captain_agent.reset_runtime_state()
        report.append(f"✅ Capitão destravado: {snapshot}")
    except Exception as e:
        report.append(f"⚠️ Capitão runtime reset parcial: {e}")

    # --- Bankroll Guardian ---
    try:
        guardian_snapshot = bankroll_guardian.reset_runtime_state()
        report.append(f"✅ Guardião da Banca resetado: {guardian_snapshot}")
    except Exception as e:
        report.append(f"⚠️ Guardião da Banca reset parcial: {e}")

    # --- Signal Generator (cooldowns, daily trades) ---
    try:
        from services.signal_generator import signal_generator
        if hasattr(signal_generator, "asset_blocklist_permanent"):
            signal_generator.asset_blocklist_permanent.clear()
        if hasattr(signal_generator, "daily_trade_count"):
            signal_generator.daily_trade_count.clear()
        report.append("✅ SignalGenerator: blocklists e daily_trades limpos.")
    except Exception as e:
        report.append(f"⚠️ SignalGenerator reset parcial: {e}")

    return report


async def main():
    print("=" * 60)
    print("☢️  NUCLEAR RESET COMPLETO — V111.0")
    print("=" * 60)
    print()

    target_balance = float(os.getenv("OKX_SIMULATED_BALANCE", 100.0))
    print(f"💰 Banca alvo: ${target_balance:.2f}")
    print()

    all_reports = {
        "timestamp": datetime.utcnow().isoformat(),
        "target_balance": target_balance,
        "steps": [],
    }

    try:
        # 1. Inicializar Database Service (PostgreSQL)
        from config import settings
        logger.info("🔄 Inicializando Database Service...")
        from services.database_service import database_service
        pg_report = await reset_postgres(database_service)
        all_reports["steps"].extend(pg_report)
        for line in pg_report:
            print(f"  {line}")

        # 2. Inicializar Redis Service
        logger.info("🔄 Inicializando Redis Service...")
        from services.redis_service import redis_service
        await redis_service.connect()
        redis_report = await reset_redis(redis_service)
        all_reports["steps"].extend(redis_report)
        for line in redis_report:
            print(f"  {line}")

        # 3. Firebase
        logger.info("🔄 Inicializando Firebase...")
        firebase_report = []
        try:
            from services.firebase_service import firebase_service
            if not firebase_service.is_active:
                try:
                    await firebase_service.initialize()
                except Exception as e:
                    logger.warning(f"Firebase não pôde ser inicializado: {e}")
            firebase_report = await reset_firebase(firebase_service, target_balance)
        except Exception as e:
            firebase_report = [f"⚠️ Firebase não disponível: {e}"]
        all_reports["steps"].extend(firebase_report)
        for line in firebase_report:
            print(f"  {line}")

        # 4. Memória dos Agentes
        logger.info("🔄 Limpando memória dos agentes...")
        memory_report = []
        try:
            from services.okx_rest import okx_rest_service
            from services.bankroll import bankroll_manager
            from services.agents.captain import captain_agent
            from services.agents.bankroll_guardian import bankroll_guardian
            memory_report = await reset_memory(
                okx_rest_service, bankroll_manager, captain_agent, bankroll_guardian, target_balance
            )
        except Exception as e:
            memory_report = [f"⚠️ Memória reset parcial: {e}"]
        all_reports["steps"].extend(memory_report)
        for line in memory_report:
            print(f"  {line}")

        # 5. Resumo Final
        all_reports["status"] = "SUCCESS"
        print()
        print("=" * 60)
        print(f"✅ RESET NUCLEAR CONCLUÍDO COM SUCESSO!")
        print(f"  Banca: ${target_balance:.2f}")
        print(f"  Data: {all_reports['timestamp']}")
        print("=" * 60)

        # Salvar relatório
        import json
        report_path = os.path.join(os.path.dirname(__file__), f"reset_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_path, "w") as f:
            json.dump(all_reports, f, indent=2, default=str)
        print(f"📄 Relatório salvo em: {report_path}")

    except Exception as e:
        all_reports["status"] = "ERROR"
        all_reports["error"] = str(e)
        print()
        print("=" * 60)
        print(f"❌ RESET NUCLEAR FALHOU: {e}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
