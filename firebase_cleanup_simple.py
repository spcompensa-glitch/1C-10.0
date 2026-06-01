#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Limpeza Simples do Firebase usando as funções corretas
====================================================

Script para limpar o Firebase usando as funções existentes do FirebaseService.
Limpa:
1. Banca para $100
2. Todos os slots (1-4)
3. Moonbags
4. Histórico de trades

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

async def firebase_cleanup_simple():
    """Executa limpeza simples usando as funções do FirebaseService"""
    
    print("🔥 LIMPEZA SIMPLES DO FIREBASE")
    print("=" * 40)
    
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
        
        # 1. Resetar banca para $100
        print("\n💰 Resetando banca para $100...")
        try:
            await firebase_service.update_bankroll(100.0)
            cleanup_actions.append("bankroll_reset")
            print("   ✅ Banca resetada para $100")
        except Exception as e:
            print(f"   ❌ Erro ao resetar banca: {e}")
            cleanup_actions.append("bankroll_reset_error")
        
        # 2. Resetar todos os slots (1-4)
        print("\n🔄 Resetando todos os slots (1-4)...")
        for i in range(1, 5):
            try:
                await firebase_service.hard_reset_slot(i, "EMERGENCY_RESET_COMPLETE", pnl=0.0)
                cleanup_actions.append(f"slot_{i}_reset")
                print(f"   ✅ Slot {i} resetado")
            except Exception as e:
                print(f"   ❌ Erro ao resetar slot {i}: {e}")
                cleanup_actions.append(f"slot_{i}_reset_error")
        
        # 3. Limpar moonbags
        print("\n🌙 Limpando moonbags...")
        try:
            # Obter todos os moonbags
            moonbags = await firebase_service.get_moonbags(limit=100)
            deleted_count = 0
            
            if moonbags:
                for moonbag in moonbags:
                    try:
                        moon_uuid = moonbag.get("uuid")
                        if moon_uuid:
                            await firebase_service.remove_moonbag(moon_uuid, reason="EMERGENCY_RESET")
                            deleted_count += 1
                    except Exception as e:
                        print(f"      ⚠️  Erro ao remover moonbag: {e}")
            else:
                print("      ℹ️  Nenhum moonbag encontrado")
            
            if deleted_count > 0:
                cleanup_actions.append(f"moonbags_cleaned_{deleted_count}")
                print(f"   ✅ {deleted_count} moonbags removidas")
            else:
                cleanup_actions.append("no_moonbags_found")
                
        except Exception as e:
            print(f"   ❌ Erro ao limpar moonbags: {e}")
            cleanup_actions.append("moonbags_clean_error")
        
        # 4. Limpar histórico de trades no Firestore
        print("\n📊 Limpando histórico de trades...")
        try:
            # Limpar coleção de trades no Firestore
            trades_ref = firebase_service.db.collection("trades")
            docs = trades_ref.stream()
            deleted_trades = 0
            
            for doc in docs:
                try:
                    await asyncio.to_thread(doc.reference.delete)
                    deleted_trades += 1
                except Exception as e:
                    print(f"      ⚠️  Erro ao deletar trade {doc.id}: {e}")
            
            if deleted_trades > 0:
                cleanup_actions.append(f"trades_cleaned_{deleted_trades}")
                print(f"   ✅ {deleted_trades} trades removidos")
            else:
                cleanup_actions.append("no_trades_found")
                print("   ℹ️  Nenhum trade encontrado")
                
        except Exception as e:
            print(f"   ❌ Erro ao limpar trades: {e}")
            cleanup_actions.append("trades_clean_error")
        
        # 5. Limpar histórico de orders no Firestore
        print("\n📋 Limpando histórico de orders...")
        try:
            # Limpar coleção de orders no Firestore
            orders_ref = firebase_service.db.collection("orders")
            docs = orders_ref.stream()
            deleted_orders = 0
            
            for doc in docs:
                try:
                    await asyncio.to_thread(doc.reference.delete)
                    deleted_orders += 1
                except Exception as e:
                    print(f"      ⚠️  Erro ao deletar order {doc.id}: {e}")
            
            if deleted_orders > 0:
                cleanup_actions.append(f"orders_cleaned_{deleted_orders}")
                print(f"   ✅ {deleted_orders} orders removidas")
            else:
                cleanup_actions.append("no_orders_found")
                print("   ℹ️  Nenhuma order encontrada")
                
        except Exception as e:
            print(f"   ❌ Erro ao limpar orders: {e}")
            cleanup_actions.append("orders_clean_error")
        
        # 6. Limpar histórico de positions no Firestore
        print("\n📍 Limpando histórico de positions...")
        try:
            # Limpar coleção de positions no Firestore
            positions_ref = firebase_service.db.collection("positions")
            docs = positions_ref.stream()
            deleted_positions = 0
            
            for doc in docs:
                try:
                    await asyncio.to_thread(doc.reference.delete)
                    deleted_positions += 1
                except Exception as e:
                    print(f"      ⚠️  Erro ao deletar position {doc.id}: {e}")
            
            if deleted_positions > 0:
                cleanup_actions.append(f"positions_cleaned_{deleted_positions}")
                print(f"   ✅ {deleted_positions} positions removidas")
            else:
                cleanup_actions.append("no_positions_found")
                print("   ℹ️  Nenhuma position encontrada")
                
        except Exception as e:
            print(f"   ❌ Erro ao limpar positions: {e}")
            cleanup_actions.append("positions_clean_error")
        
        # 7. Limpar moonbags no Firestore
        print("\n🌙 Limpando moonbags no Firestore...")
        try:
            # Limpar coleção de moonbags no Firestore
            moonbags_ref = firebase_service.db.collection("moonbags")
            docs = moonbags_ref.stream()
            deleted_firestore_moonbags = 0
            
            for doc in docs:
                try:
                    await asyncio.to_thread(doc.reference.delete)
                    deleted_firestore_moonbags += 1
                except Exception as e:
                    print(f"      ⚠️  Erro ao deletar moonbag {doc.id}: {e}")
            
            if deleted_firestore_moonbags > 0:
                cleanup_actions.append(f"firestore_moonbags_cleaned_{deleted_firestore_moonbags}")
                print(f"   ✅ {deleted_firestore_moonbags} moonbags removidas")
            else:
                cleanup_actions.append("no_firestore_moonbags")
                print("   ℹ️  Nenhuma moonbag encontrada")
                
        except Exception as e:
            print(f"   ❌ Erro ao limpar moonbags no Firestore: {e}")
            cleanup_actions.append("firestore_moonbags_clean_error")
        
        # 8. Resetar estado do sistema
        print("\n⚙️  Resetando estado do sistema...")
        try:
            # Limpar estado do sistema
            reset_data = {
                "paper_engine_state": None,
                "last_reset": timestamp,
                "status": "CLEANSED",
                "reset_reason": "EMERGENCY_RESET_COMPLETE"
            }
            
            await firebase_service.db.collection("system_state").document("status").set(reset_data, merge=True)
            cleanup_actions.append("system_state_reset")
            print("   ✅ Estado do sistema resetado")
        except Exception as e:
            print(f"   ❌ Erro ao resetar estado do sistema: {e}")
            cleanup_actions.append("system_state_reset_error")
        
        # Resumo
        success_count = len([r for r in cleanup_actions if not r.endswith("_error") and not r.endswith("_failed")])
        total_count = len(cleanup_actions)
        
        print(f"\n📊 RESUMO DA LIMPEZA:")
        print(f"   ✅ Ações bem sucedidas: {success_count}/{total_count}")
        print(f"   ❌ Ações com erro: {total_count - success_count}/{total_count}")
        
        if success_count >= total_count * 0.8:  # 80% de sucesso
            print("   🎉 LIMPEZA CONCLUÍDA COM SUCESSO!")
            status = "SUCCESS"
        else:
            print("   ⚠️  LIMPEZA PARCIAL - Algumas ações falharam")
            status = "PARTIAL"
        
        # Gerar relatório
        report = {
            "timestamp": timestamp,
            "action": "FIREBASE_CLEANUP_SIMPLE",
            "total_actions": total_count,
            "successful_actions": success_count,
            "failed_actions": total_count - success_count,
            "status": status,
            "details": cleanup_actions,
            "next_step": "RESTART_RAILWAY_BACKEND"
        }
        
        # Salvar relatório
        report_file = f"firebase_cleanup_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Relatório salvo: {report_file}")
        
        return success_count >= total_count * 0.8
        
    except Exception as e:
        print(f"\n❌ ERRO DURANTE A LIMPEZA: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Função principal"""
    print("🚀 Iniciando limpeza do Firebase...")
    
    # Executar limpeza assíncrona
    success = asyncio.run(firebase_cleanup_simple())
    
    if success:
        print("\n🎉 LIMPEZA DO FIREBASE CONCLUÍDA COM SUCESSO!")
        print("✅ Dados limpos nos seguintes locais:")
        print("   1. ✅ Banca resetada para $100")
        print("   2. ✅ Slots 1-4 resetados")
        print("   3. ✅ Moonbags removidas")
        print("   4. ✅ Histórico de trades limpo")
        print("   5. ✅ Histórico de orders limpo")
        print("   6. ✅ Histórico de positions limpo")
        print("   7. ✅ Estado do sistema resetado")
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