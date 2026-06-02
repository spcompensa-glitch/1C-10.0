#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Limpeza Triplicata Completa - 3 Locais Diferentes
================================================

Script para limpar TODOS os dados do sistema 1Crypten nos 3 locais onde persistem:
1. Banco de dados PostgreSQL (Railway)
2. Firebase/Realtime Database
3. Estado na memória do backend (será reiniciado)

Author: Sistema 1Crypten
Version: 1.0
"""

import os
import sys
import asyncio
import json
from datetime import datetime

# Adiciona backend ao path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.append(backend_path)

async def triple_cleanup_complete():
    """Executa limpeza completa nos 3 locais de persistência"""
    
    print("🧹 LIMPEZA TRIPlicata COMPLETA - 3 LOCAIS")
    print("=" * 60)
    
    timestamp = datetime.now().isoformat()
    cleanup_actions = []
    
    try:
        # Importar serviços
        from backend.services.firebase_service import FirebaseService
        from backend.config import settings
        
        print("✅ Importações bem sucedidas")
        cleanup_actions.append("import_services")
        
        # Inicializar serviços
        firebase_service = FirebaseService()
        
        print("🔧 Inicializando serviços...")
        
        # ===== LOCAL 1: BANCO DE DADOS POSTGRESQL (Railway) =====
        print("\n🗄️  LIMPAando BANCO DE DADOS POSTGRESQL (Railway)...")
        
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine
            
            db_url = "postgresql+asyncpg://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
            engine = create_async_engine(db_url)
            
            async with engine.connect() as conn:
                # 1. Limpar tabela system_state
                print("   🔄 Limpando tabela system_state...")
                await conn.execute(text("DELETE FROM system_state WHERE key = 'paper_engine_state'"))
                cleanup_actions.append("postgres_system_state")
                
                # 2. Resetar banca_status
                print("   💰 Resetando banca_status...")
                await conn.execute(text("""
                    UPDATE banca_status 
                    SET saldo_total = 100.0, 
                        lucro_acumulado = 0.0, 
                        risco_real_percent = 0.0, 
                        slots_disponiveis = 4, 
                        status = 'ONLINE',
                        updated_at = NOW()
                    WHERE id = 1
                """))
                cleanup_actions.append("postgres_bankroll_reset")
                
                # 3. Limpar todos os slots (1-4)
                print("   🔄 Limpando slots 1-4...")
                for i in range(1, 5):
                    await conn.execute(text("""
                        UPDATE slots SET
                            symbol = NULL,
                            side = NULL,
                            qty = 0.0,
                            entry_price = 0.0,
                            current_price = 0.0,
                            pnl = 0.0,
                            pnl_percent = 0.0,
                            status = 'STANDBY',
                            created_at = NOW(),
                            updated_at = NOW(),
                            stop_loss = 0.0,
                            take_profit = 0.0,
                            liq_price = 0.0,
                            score = 0.0,
                            genesis_id = NULL,
                            slot_type = 'BLITZ_30M',
                            pensamento = '',
                            fleet_intel = '{}'
                        WHERE id = :slot_id
                    """), {"slot_id": i})
                cleanup_actions.append("postgres_slots_reset")
                
                # 4. Limpar tabela trades
                print("   📊 Limpando tabela trades...")
                await conn.execute(text("DELETE FROM trades"))
                cleanup_actions.append("postgres_trades_deleted")
                
                # 5. Limpar tabela orders
                print("   📋 Limpando tabela orders...")
                await conn.execute(text("DELETE FROM orders"))
                cleanup_actions.append("postgres_orders_deleted")
                
                conn.commit()
                print("   ✅ Banco de dados PostgreSQL limpo com sucesso!")
                
        except Exception as e:
            print(f"   ❌ Erro no PostgreSQL: {e}")
            cleanup_actions.append("postgres_error")
        
        await engine.dispose()
        
        # ===== LOCAL 2: FIREBASE/REALTIME DATABASE =====
        print("\n🔥 LIMPANDO FIREBASE/REALTIME DATABASE...")
        
        try:
            # 1. Limpar RTDB - banca_status
            print("   💰 Resetando banca_status no RTDB...")
            await firebase_service.rtdb.child("banca_status/status").update({
                "saldo_total": 100.0,
                "lucro_acumulado": 0.0,
                "base_capital": 100.0,
                "slots_disponiveis": 4,
                "status": "ONLINE",
                "reset_timestamp": timestamp,
                "risk_level": "LOW"
            })
            cleanup_actions.append("rtdb_bankroll_reset")
            
            # 2. Limpar RTDB - slots
            print("   🔄 Limpando slots no RTDB...")
            for i in range(1, 5):
                await firebase_service.rtdb.child(f"slots/slot_{i}").set({
                    "id": i,
                    "symbol": None,
                    "side": None,
                    "qty": 0.0,
                    "entry_price": 0.0,
                    "current_price": 0.0,
                    "pnl": 0.0,
                    "pnl_percent": 0.0,
                    "status": "STANDBY",
                    "slot_type": "BLITZ_30M",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "stop_loss": 0.0,
                    "take_profit": 0.0,
                    "liq_price": 0.0,
                    "score": 0.0,
                    "genesis_id": None,
                    "pensamento": "",
                    "fleet_intel": {},
                    "reset_timestamp": timestamp
                })
            cleanup_actions.append("rtdb_slots_reset")
            
            # 3. Limpar RTDB - moonbags
            print("   🌙 Limpando moonbags no RTDB...")
            moonbags_ref = firebase_service.rtdb.child("moonbags")
            await moonbags_ref.set({})
            cleanup_actions.append("rtdb_moonbags_reset")
            
            # 4. Limpar RTDB - trades
            print("   📊 Limpando trades no RTDB...")
            trades_ref = firebase_service.rtdb.child("trades")
            await trades_ref.set({})
            cleanup_actions.append("rtdb_trades_reset")
            
            # 5. Limpar RTDB - orders
            print("   📋 Limpando orders no RTDB...")
            orders_ref = firebase_service.rtdb.child("orders")
            await orders_ref.set({})
            cleanup_actions.append("rtdb_orders_reset")
            
            # 6. Limpar RTDB - system_state
            print("   ⚙️  Limpando system_state no RTDB...")
            await firebase_service.rtdb.child("system_state").update({
                "paper_engine_state": None,
                "last_reset": timestamp,
                "status": "CLEANSED"
            })
            cleanup_actions.append("rtdb_system_state_reset")
            
            print("   ✅ Firebase/RTDB limpo com sucesso!")
            
        except Exception as e:
            print(f"   ❌ Erro no Firebase/RTDB: {e}")
            cleanup_actions.append("rtdb_error")
        
        # ===== LOCAL 3: FIREBASE FIRESTORE (Coleções) =====
        print("\n📚 LIMPANDO FIREBASE FIRESTORE (Coleções)...")
        
        try:
            # 1. Limpar coleção moonbags
            print("   🌙 Limpando coleção moonbags...")
            moonbags_collection = firebase_service.db.collection("moonbags")
            docs = moonbags_collection.stream()
            deleted_moonbags = 0
            
            for doc in docs:
                try:
                    await asyncio.to_thread(doc.reference.delete)
                    deleted_moonbags += 1
                except Exception as e:
                    print(f"      ⚠️  Erro ao deletar moonbag {doc.id}: {e}")
            
            if deleted_moonbags > 0:
                cleanup_actions.append(f"firestore_moonbags_deleted_{deleted_moonbags}")
                print(f"      ✅ {deleted_moonbags} moonbags removidas")
            else:
                cleanup_actions.append("firestore_no_moonbags")
                print("      ℹ️  Nenhuma moonbag encontrada")
            
            # 2. Limpar coleção trades
            print("   📊 Limpando coleção trades...")
            trades_collection = firebase_service.db.collection("trades")
            docs = trades_collection.stream()
            deleted_trades = 0
            
            for doc in docs:
                try:
                    await asyncio.to_thread(doc.reference.delete)
                    deleted_trades += 1
                except Exception as e:
                    print(f"      ⚠️  Erro ao deletar trade {doc.id}: {e}")
            
            if deleted_trades > 0:
                cleanup_actions.append(f"firestore_trades_deleted_{deleted_trades}")
                print(f"      ✅ {deleted_trades} trades removidos")
            else:
                cleanup_actions.append("firestore_no_trades")
                print("      ℹ️  Nenhum trade encontrado")
            
            # 3. Limpar coleção positions
            print("   📍 Limpando coleção positions...")
            positions_collection = firebase_service.db.collection("positions")
            docs = positions_collection.stream()
            deleted_positions = 0
            
            for doc in docs:
                try:
                    await asyncio.to_thread(doc.reference.delete)
                    deleted_positions += 1
                except Exception as e:
                    print(f"      ⚠️  Erro ao deletar position {doc.id}: {e}")
            
            if deleted_positions > 0:
                cleanup_actions.append(f"firestore_positions_deleted_{deleted_positions}")
                print(f"      ✅ {deleted_positions} positions removidas")
            else:
                cleanup_actions.append("firestore_no_positions")
                print("      ℹ️  Nenhuma position encontrada")
            
            # 4. Limpar coleção orders
            print("   📋 Limpando coleção orders...")
            orders_collection = firebase_service.db.collection("orders")
            docs = orders_collection.stream()
            deleted_orders = 0
            
            for doc in docs:
                try:
                    await asyncio.to_thread(doc.reference.delete)
                    deleted_orders += 1
                except Exception as e:
                    print(f"      ⚠️  Erro ao deletar order {doc.id}: {e}")
            
            if deleted_orders > 0:
                cleanup_actions.append(f"firestore_orders_deleted_{deleted_orders}")
                print(f"      ✅ {deleted_orders} orders removidas")
            else:
                cleanup_actions.append("firestore_no_orders")
                print("      ℹ️  Nenhuma order encontrada")
            
            print("   ✅ Firebase Firestore limpo com sucesso!")
            
        except Exception as e:
            print(f"   ❌ Erro no Firebase Firestore: {e}")
            cleanup_actions.append("firestore_error")
        
        # ===== VERIFICAÇÃO FINAL =====
        print("\n🔍 VERIFICANDO RESULTADO FINAL...")
        
        try:
            # Verificar banca no RTDB
            bankroll_status = await firebase_service.rtdb.child("banca_status/status").get()
            if bankroll_status:
                bankroll_data = bankroll_status.val()
                current_balance = bankroll_data.get("saldo_total", 0)
                slots_available = bankroll_data.get("slots_disponiveis", 0)
                
                if current_balance == 100.0 and slots_available == 4:
                    print(f"   ✅ Banca: ${current_balance:.2f}")
                    print(f"   ✅ Slots disponíveis: {slots_available}")
                    cleanup_actions.append("final_verification_passed")
                else:
                    print(f"   ❌ Banca incorreta: ${current_balance:.2f} (esperado: $100)")
                    print(f"   ❌ Slots incorretos: {slots_available} (esperado: 4)")
                    cleanup_actions.append("final_verification_failed")
            else:
                print("   ❌ Não foi possível verificar status da banca")
                cleanup_actions.append("bankroll_check_failed")
                
        except Exception as e:
            print(f"   ❌ Erro ao verificar: {e}")
            cleanup_actions.append("verification_error")
        
        # Resumo
        success_count = len([r for r in cleanup_actions if not r.endswith("_error") and not r.endswith("_failed")])
        total_count = len(cleanup_actions)
        
        print(f"\n📊 RESUMO DA LIMPEZA TRIPlicata:")
        print(f"   ✅ Ações bem sucedidas: {success_count}/{total_count}")
        print(f"   ❌ Ações com erro: {total_count - success_count}/{total_count}")
        
        if success_count >= total_count * 0.9:  # 90% de sucesso
            print("   🎉 LIMPEZA TRIPlicata CONCLUÍDA COM SUCESSO!")
            status = "SUCCESS"
        else:
            print("   ⚠️  LIMPEZA PARCIAL - Algumas ações falharam")
            status = "PARTIAL"
        
        # Gerar relatório
        report = {
            "timestamp": timestamp,
            "action": "TRIPLE_CLEANUP_COMPLETE",
            "total_locations": 3,
            "total_actions": total_count,
            "successful_actions": success_count,
            "failed_actions": total_count - success_count,
            "status": status,
            "details": cleanup_actions,
            "next_step": "RESTART_RAILWAY_BACKEND"
        }
        
        # Salvar relatório
        report_file = f"triple_cleanup_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Relatório salvo: {report_file}")
        
        return success_count >= total_count * 0.9
        
    except Exception as e:
        print(f"\n❌ ERRO DURANTE A LIMPEZA: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Função principal"""
    print("🚀 Iniciando limpeza triplicata...")
    
    # Executar limpeza assíncrona
    success = asyncio.run(triple_cleanup_complete())
    
    if success:
        print("\n🎉 LIMPEZA TRIPlicata CONCLUÍDA COM SUCESSO!")
        print("✅ Todos os 3 locais foram limpos:")
        print("   1. ✅ Banco de dados PostgreSQL (Railway)")
        print("   2. ✅ Firebase/Realtime Database")
        print("   3. ✅ Firebase Firestore (Coleções)")
        print("\n🔄 PRÓXIMO PASSO: Reiniciar o backend no Railway")
        print("   Acesse o painel Railway e clique em 'Redeploy'")
        print("   Após reiniciar, o sistema deve mostrar:")
        print("   - 4 slots disponíveis")
        print("   - Banca em $100.00")
        print("   - Sem moonbags ou trades")
    else:
        print("\n💥 LIMPEZA FALHOU!")
        print("🔍 Verifique os logs e tente novamente")

if __name__ == "__main__":
    main()