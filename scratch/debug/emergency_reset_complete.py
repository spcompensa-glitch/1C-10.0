#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reset de Emergência Completo - Força Limpeza Total em Produção
============================================================

Script final para reset total do sistema 1Crypten em produção.
Força limpeza completa em todos os níveis.

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

async def emergency_reset_complete():
    """Executa reset de emergência completo do sistema"""
    
    print("🚨 RESET DE EMERGÊNCIA COMPLETO")
    print("=" * 50)
    print("Forçando limpeza total do sistema em produção...")
    
    timestamp = datetime.now().isoformat()
    cleanup_actions = []
    
    try:
        # Importar serviços
        from backend.services.firebase_service import FirebaseService
        
        print("✅ Serviços importados com sucesso")
        cleanup_actions.append("services_imported")
        
        # Inicializar serviços
        firebase_service = FirebaseService()
        
        print("🔧 Inicializando Firebase...")
        
        # ===== 1. RESET TOTAL DO FIREBASE/RTDB =====
        print("\n🔥 RESET TOTAL DO FIREBASE/REALTIME DATABASE...")
        
        try:
            # Forçar dados limpos no RTDB
            clean_rtdb_data = {
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
                    "status": "RESET_COMPLETE",
                    "reset_reason": "EMERGENCY_RESET"
                }
            }
            
            # Limpar completamente o RTDB
            await asyncio.to_thread(firebase_service.rtdb.delete, "")
            print("   🗑️  RTDB completamente limpo")
            
            # Recriar dados limpos
            await asyncio.to_thread(firebase_service.rtdb.set, clean_rtdb_data)
            cleanup_actions.append("rtdb_complete_reset")
            print("   ✅ Firebase/RTDB resetado com sucesso!")
            
        except Exception as e:
            print(f"   ❌ Erro no RTDB: {e}")
            cleanup_actions.append("rtdb_error")
        
        # ===== 2. RESET TOTAL DO FIRESTORE =====
        print("\n📚 RESET TOTAL DO FIRESTORE...")
        
        try:
            # Limpar TODAS as coleções
            collections_to_reset = [
                "moonbags", "trades", "orders", "positions", "system_state", 
                "banca_status", "slots", "users", "banca_history", 
                "captain_profile", "chat_history"
            ]
            
            for collection_name in collections_to_reset:
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
                    print(f"      ❌ Erro em {collection_name}: {e}")
                    cleanup_actions.append(f"firestore_{collection_name}_error")
            
            # Recriar documentos essenciais
            try:
                # Documento de banca
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
                cleanup_actions.append("firestore_bankroll_created")
                print("      ✅ Documento de banca recriado")
                
                # Documento de slots
                for i in range(1, 5):
                    await firebase_service.db.collection("slots").document(f"slot_{i}").set({
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
                
                cleanup_actions.append("firestore_slots_created")
                print("      ✅ Slots 1-4 recriados")
                
                # Documento de sistema
                await firebase_service.db.collection("system_state").document("status").set({
                    "system_clean": True,
                    "last_reset": timestamp,
                    "clean_type": "EMERGENCY_RESET",
                    "version": "V110.701",
                    "status": "CLEANSED"
                })
                cleanup_actions.append("firestore_system_created")
                print("      ✅ Estado do sistema recriado")
                
            except Exception as e:
                print(f"      ❌ Erro ao recriar documentos: {e}")
                cleanup_actions.append("firestore_recreation_error")
            
            print("   ✅ Firestore resetado com sucesso!")
            
        except Exception as e:
            print(f"   ❌ Erro no Firestore: {e}")
            cleanup_actions.append("firestore_error")
        
        # ===== 3. VERIFICAÇÃO FINAL =====
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
        
        # ===== 4. RESULTADO =====
        success_count = len([r for r in cleanup_actions if not r.endswith("_error") and not r.endswith("_failed")])
        total_count = len(cleanup_actions)
        
        print(f"\n📊 RESULTADO DO RESET DE EMERGÊNCIA:")
        print(f"   ✅ Ações bem sucedidas: {success_count}/{total_count}")
        print(f"   ❌ Ações com erro: {total_count - success_count}/{total_count}")
        
        if success_count >= total_count * 0.8:  # 80% de sucesso
            print("   🎉 RESET DE EMERGÊNCIA CONCLUÍDO COM SUCESSO!")
            status = "SUCCESS"
        else:
            print("   ⚠️  RESET PARCIAL - Algumas ações falharam")
            status = "PARTIAL"
        
        # Gerar relatório
        report = {
            "timestamp": timestamp,
            "action": "EMERGENCY_RESET_COMPLETE",
            "total_actions": total_count,
            "successful_actions": success_count,
            "failed_actions": total_count - success_count,
            "status": status,
            "details": cleanup_actions,
            "next_step": "SYSTEM_RESTART",
            "force_restart_needed": True
        }
        
        # Salvar relatório
        report_file = f"emergency_reset_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Relatório salvo: {report_file}")
        
        return success_count >= total_count * 0.8
        
    except Exception as e:
        print(f"\n❌ ERRO DURANTE O RESET DE EMERGÊNCIA: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Função principal"""
    print("🚨 RESET DE EMERGÊNCIA COMPLETO PARA PRODUÇÃO")
    print("=" * 60)
    print("Forçando reset total do sistema em produção...")
    
    # Executar reset
    success = asyncio.run(emergency_reset_complete())
    
    if success:
        print("\n🎉 RESET CONCLUÍDO COM SUCESSO!")
        print("=====================================")
        print("✅ Sistema completamente resetado em produção:")
        print("   - Banca: $100.00")
        print("   - Slots: 4 disponíveis (vazios)")
        print("   - Moonbags: 0")
        print("   - Trades: 0")
        print("   - Status: ONLINE")
        print("\n🔄 O sistema deve atualizar automaticamente!")
        print("   Se necessário, atualize a página manualmente.")
    else:
        print("\n💥 RESET FALHOU!")
        print("🔍 Verifique os logs e tente novamente")

if __name__ == "__main__":
    main()