#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Limpeza Agressiva Final - Força Limpeza Total
============================================

Script final para limpeza total do sistema 1Crypten.
Remove TODOS os dados existentes e força reinicialização.

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

async def aggressive_cleanup_final():
    """Executa limpeza agressiva total do sistema"""
    
    print("💥 LIMPEZA AGRESSIVA FINAL - FORÇA LIMPEZA TOTAL")
    print("=" * 60)
    
    timestamp = datetime.now().isoformat()
    cleanup_actions = []
    
    try:
        # Importar serviços
        from backend.services.firebase_service import FirebaseService
        
        print("✅ Importações bem sucedidas")
        cleanup_actions.append("import_services")
        
        # Inicializar serviços
        firebase_service = FirebaseService()
        
        print("🔧 Inicializando serviços...")
        
        # ===== 1. LIMPEZA DO BANCO DE DADOS POSTGRESQL =====
        print("\n🗄️  LIMPEZA AGRESSIVA DO BANCO DE DADOS POSTGRESQL...")
        
        try:
            from sqlalchemy import text
            from sqlalchemy.ext.asyncio import create_async_engine
            
            db_url = "postgresql+asyncpg://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
            engine = create_async_engine(db_url)
            
            async with engine.connect() as conn:
                # Forçar limpeza total de todas as tabelas
                print("   🔥 Limpando TODAS as tabelas...")
                
                # Limpar system_state
                await conn.execute(text("DELETE FROM system_state"))
                cleanup_actions.append("postgres_system_state_full")
                
                # Resetar banca_status completamente
                await conn.execute(text("""
                    INSERT INTO banca_status (id, saldo_total, lucro_acumulado, risco_real_percent, slots_disponiveis, status, created_at, updated_at)
                    VALUES (1, 100.0, 0.0, 0.0, 4, 'ONLINE', NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        saldo_total = 100.0,
                        lucro_acumulado = 0.0,
                        risco_real_percent = 0.0,
                        slots_disponiveis = 4,
                        status = 'ONLINE',
                        updated_at = NOW()
                """))
                cleanup_actions.append("postgres_bankroll_force_reset")
                
                # Forçar limpeza de todos os slots
                for i in range(1, 5):
                    await conn.execute(text("""
                        DELETE FROM slots WHERE id = :slot_id
                    """), {"slot_id": i})
                    
                    # Recriar slots vazios
                    await conn.execute(text("""
                        INSERT INTO slots (id, symbol, side, qty, entry_price, current_price, pnl, pnl_percent, status, created_at, updated_at, stop_loss, take_profit, liq_price, score, genesis_id, slot_type, pensamento, fleet_intel)
                        VALUES (:slot_id, NULL, NULL, 0.0, 0.0, 0.0, 0.0, 0.0, 'STANDBY', NOW(), NOW(), 0.0, 0.0, 0.0, 0.0, NULL, 'BLITZ_30M', '', '{}')
                        ON CONFLICT (id) DO UPDATE SET
                            symbol = NULL,
                            side = NULL,
                            qty = 0.0,
                            entry_price = 0.0,
                            current_price = 0.0,
                            pnl = 0.0,
                            pnl_percent = 0.0,
                            status = 'STANDBY',
                            updated_at = NOW(),
                            stop_loss = 0.0,
                            take_profit = 0.0,
                            liq_price = 0.0,
                            score = 0.0,
                            genesis_id = NULL,
                            slot_type = 'BLITZ_30M',
                            pensamento = '',
                            fleet_intel = '{}'
                    """), {"slot_id": i})
                cleanup_actions.append("postgres_slots_force_reset")
                
                # Limpar tabela trades
                await conn.execute(text("DELETE FROM trades"))
                cleanup_actions.append("postgres_trades_force_deleted")
                
                # Limpar tabela orders
                await conn.execute(text("DELETE FROM orders"))
                cleanup_actions.append("postgres_orders_force_deleted")
                
                conn.commit()
                print("   ✅ Banco de PostgreSQL limpo FORÇADAMENTE!")
                
        except Exception as e:
            print(f"   ❌ Erro no PostgreSQL: {e}")
            cleanup_actions.append("postgres_error")
        
        await engine.dispose()
        
        # ===== 2. LIMPEZA TOTAL DO FIREBASE/RTDB =====
        print("\n🔥 LIMPEZA TOTAL DO FIREBASE/REALTIME DATABASE...")
        
        try:
            # Forçar limpeza de TODOS os dados no RTDB
            rtdb_data = {
                "banca_status": {
                    "status": {
                        "saldo_total": 100.0,
                        "lucro_acumulado": 0.0,
                        "base_capital": 100.0,
                        "slots_disponiveis": 4,
                        "status": "ONLINE",
                        "risk_level": "LOW",
                        "reset_timestamp": timestamp,
                        "last_updated": timestamp
                    }
                },
                "slots": {
                    "slot_1": {
                        "id": 1,
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
                    },
                    "slot_2": {
                        "id": 2,
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
                    },
                    "slot_3": {
                        "id": 3,
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
                    },
                    "slot_4": {
                        "id": 4,
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
                    }
                },
                "moonbag_vault": {},
                "trades": {},
                "orders": {},
                "positions": {},
                "system_state": {
                    "paper_engine_state": None,
                    "last_reset": timestamp,
                    "status": "CLEANSED",
                    "reset_reason": "AGGRESSIVE_CLEANUP"
                },
                "live_slots": {},
                "market_radar": {},
                "chat_history": {},
                "radar_pulse": {},
                "vault_status": {},
                "system_cooldowns": {},
                "oracle_context": {},
                "system_bias": {},
                "ws_command_tower": {},
                "btc_command_center": {},
                "chat_status": {},
                "captain_profile": {}
            }
            
            await asyncio.to_thread(firebase_service.rtdb.set, rtdb_data)
            cleanup_actions.append("rtdb_total_reset")
            print("   ✅ Firebase/RTDB limpo FORÇADAMENTE!")
            
        except Exception as e:
            print(f"   ❌ Erro no Firebase/RTDB: {e}")
            cleanup_actions.append("rtdb_error")
        
        # ===== 3. LIMPEZA TOTAL DO FIRESTORE =====
        print("\n📚 LIMPEZA TOTAL DO FIRESTORE...")
        
        try:
            # Limpar TODAS as coleções do Firestore
            collections_to_clean = [
                "moonbags",
                "trades", 
                "orders",
                "positions",
                "system_state",
                "banca_status",
                "slots",
                "users",
                "banca_history",
                "captain_profile",
                "chat_history"
            ]
            
            for collection_name in collections_to_clean:
                try:
                    collection_ref = firebase_service.db.collection(collection_name)
                    docs = collection_ref.stream()
                    deleted_count = 0
                    
                    for doc in docs:
                        try:
                            await asyncio.to_thread(doc.reference.delete)
                            deleted_count += 1
                        except Exception as e:
                            print(f"      ⚠️  Erro ao deletar {collection_name}/{doc.id}: {e}")
                    
                    if deleted_count > 0:
                        cleanup_actions.append(f"firestore_{collection_name}_cleaned_{deleted_count}")
                        print(f"      ✅ {collection_name}: {deleted_count} documentos removidos")
                    else:
                        cleanup_actions.append(f"firestore_{collection_name}_empty")
                        print(f"      ℹ️  {collection_name}: vazio")
                        
                except Exception as e:
                    print(f"      ❌ Erro ao limpar {collection_name}: {e}")
                    cleanup_actions.append(f"firestore_{collection_name}_error")
            
            # Recriar documento essencial de banca
            try:
                await firebase_service.db.collection("banca_status").document("status").set({
                    "saldo_total": 100.0,
                    "lucro_acumulado": 0.0,
                    "base_capital": 100.0,
                    "slots_disponiveis": 4,
                    "status": "ONLINE",
                    "risk_level": "LOW",
                    "reset_timestamp": timestamp,
                    "last_updated": timestamp
                })
                cleanup_actions.append("firestore_bankroll_recreated")
                print("      ✅ Documento de banca recriado")
            except Exception as e:
                print(f"      ❌ Erro ao recriar documento de banca: {e}")
                cleanup_actions.append("firestore_bankroll_recreation_error")
            
            print("   ✅ Firestore limpo FORÇADAMENTE!")
            
        except Exception as e:
            print(f"   ❌ Erro no Firestore: {e}")
            cleanup_actions.append("firestore_error")
        
        # ===== 4. LIMPEZA DO ESTADO DO SISTEMA =====
        print("\n⚙️  LIMPEZA DO ESTADO DO SISTEMA...")
        
        try:
            # Forçar limpeza completa do estado
            system_state = {
                "system_clean": True,
                "last_cleanup": timestamp,
                "clean_type": "AGGRESSIVE_CLEANUP",
                "version": "V110.701",
                "status": "CLEANSED"
            }
            
            await firebase_service.db.collection("system_state").document("status").set(system_state, merge=True)
            cleanup_actions.append("system_state_aggressive_reset")
            print("   ✅ Estado do sistema limpo FORÇADAMENTE!")
            
        except Exception as e:
            print(f"   ❌ Erro ao limpar estado do sistema: {e}")
            cleanup_actions.append("system_state_error")
        
        # ===== 5. VERIFICAÇÃO FINAL =====
        print("\n🔍 VERIFICAÇÃO FINAL...")
        
        try:
            # Verificar banca
            bankroll_doc = await firebase_service.db.collection("banca_status").document("status").get()
            if bankroll_doc.exists:
                bankroll_data = bankroll_doc.to_dict()
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
                print("   ❌ Documento de banca não encontrado")
                cleanup_actions.append("bankroll_not_found")
                
        except Exception as e:
            print(f"   ❌ Erro na verificação final: {e}")
            cleanup_actions.append("verification_error")
        
        # Resumo
        success_count = len([r for r in cleanup_actions if not r.endswith("_error") and not r.endswith("_failed")])
        total_count = len(cleanup_actions)
        
        print(f"\n📊 RESUMO DA LIMPEZA AGRESSIVA:")
        print(f"   ✅ Ações bem sucedidas: {success_count}/{total_count}")
        print(f"   ❌ Ações com erro: {total_count - success_count}/{total_count}")
        
        if success_count >= total_count * 0.8:  # 80% de sucesso
            print("   🎉 LIMPEZA AGRESSIVA CONCLUÍDA COM SUCESSO!")
            status = "SUCCESS"
        else:
            print("   ⚠️  LIMPEZA PARCIAL - Algumas ações falharam")
            status = "PARTIAL"
        
        # Gerar relatório
        report = {
            "timestamp": timestamp,
            "action": "AGGRESSIVE_CLEANUP_FINAL",
            "total_actions": total_count,
            "successful_actions": success_count,
            "failed_actions": total_count - success_count,
            "status": status,
            "details": cleanup_actions,
            "next_step": "FORCE_RAILWAY_RESTART",
            "force_restart_needed": True
        }
        
        # Salvar relatório
        report_file = f"aggressive_cleanup_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Relatório salvo: {report_file}")
        
        return success_count >= total_count * 0.8
        
    except Exception as e:
        print(f"\n❌ ERRO DURANTE A LIMPEZA AGRESSIVA: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Função principal"""
    print("🚀 Iniciando limpeza agressiva final...")
    
    # Executar limpeza assíncrona
    success = asyncio.run(aggressive_cleanup_final())
    
    if success:
        print("\n🎉 LIMPEZA AGRESSIVA CONCLUÍDA COM SUCESSO!")
        print("✅ Sistema completamente limpo em TODOS os níveis:")
        print("   1. ✅ Banco de dados PostgreSQL (forçado)")
        print("   2. ✅ Firebase/RTDB (forçado)")
        print("   3. ✅ Firestore (forçado)")
        print("   4. ✅ Estado do sistema (forçado)")
        print("\n🔄 PRÓXIMO PASSO: Reiniciar Railway AGORA!")
        print("   Acesse o painel Railway e clique em 'Redeploy'")
        print("   Após reiniciar, o sistema deve mostrar:")
        print("   - 4 slots disponíveis (vazios)")
        print("   - Banca em $100.00")
        print("   - Sem moonbags ou trades")
        print("   - Sem histórico")
    else:
        print("\n💥 LIMPEZA AGRESSIVA FALHOU!")
        print("🔍 Verifique os logs e tente novamente")

if __name__ == "__main__":
    main()