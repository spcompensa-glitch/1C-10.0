#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reset Direto do Sistema Paper Mode
=================================

Script direto para limpar o sistema 1Crypten no modo paper.
Executa reset nuclear sem depender do servidor FastAPI.

Author: Sistema 1Crypten
Version: 1.0
"""

import os
import sys
import json
import asyncio
from datetime import datetime

# Adiciona backend ao path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.append(backend_path)

# Importação direta dos serviços necessários
try:
    from backend.services.okx_rest import OKXRest
    from backend.services.firebase_service import FirebaseService
    from backend.config import settings
    print("✅ Importações bem sucedidas")
except ImportError as e:
    print(f"❌ Falha nas importações: {e}")
    print("Executando modo simplificado...")
    sys.exit(1)

async def reset_paper_direct():
    """Executa reset direto do sistema paper mode"""
    
    print("🧹 INICIANDO RESET NUCLEAR DIRETO DO SISTEMA PAPER MODE")
    print("=" * 60)
    
    cleared = []
    timestamp = datetime.now().isoformat()
    
    try:
        # 1. Inicializar serviços
        print("🔧 Inicializando serviços...")
        
        # OKX Service
        okx_service = OKXRest()
        okx_service.execution_mode = "PAPER"
        okx_service.paper_balance = 100.0
        
        # Firebase Service
        firebase_service = FirebaseService()
        
        # 2. Limpar posições paper
        print("🗑️  Limpando posições paper...")
        if hasattr(okx_service, 'paper_positions'):
            okx_service.paper_positions.clear()
            cleared.append("paper_positions")
        
        # 3. Limpar moonbags paper
        print("🌙 Limpando moonbags paper...")
        if hasattr(okx_service, 'paper_moonbags'):
            okx_service.paper_moonbags.clear()
            cleared.append("paper_moonbags")
        
        # 4. Limpar histórico de ordens
        print("📋 Limpando histórico de ordens...")
        if hasattr(okx_service, 'paper_orders_history'):
            okx_service.paper_orders_history.clear()
            cleared.append("paper_orders_history")
        
        # 5. Limpar estruturas pendentes
        print("⏳ Limpando estruturas pendentes...")
        if hasattr(okx_service, 'pending_closures'):
            okx_service.pending_closures.clear()
            cleared.append("pending_closures")
        
        if hasattr(okx_service, 'emancipating_symbols'):
            okx_service.emancipating_symbols.clear()
            cleared.append("emancipating_symbols")
        
        # 6. Resetar saldo para $100
        print("💰 Resetando saldo para $100...")
        okx_service.paper_balance = 100.0
        cleared.append("paper_balance_reset")
        
        # 7. Salvar estado
        print("💾 Salvando estado do sistema...")
        if hasattr(okx_service, '_save_paper_state'):
            okx_service._save_paper_state()
            cleared.append("paper_state_saved")
        
        # 8. Resetar slots no Firebase
        print("🔄 Resetando slots no Firebase...")
        for i in range(1, 5):
            try:
                await firebase_service.hard_reset_slot(i, "NUKE_PAPER_DIRECT", pnl=0.0)
                cleared.append(f"slot_{i}_reset")
            except Exception as e:
                print(f"   ⚠️  Slot {i}: {e}")
                cleared.append(f"slot_{i}_error")
        
        # 9. Resetar status da banca
        print("🏦 Resetando status da banca...")
        try:
            await firebase_service.update_bankroll(100.0)
            cleared.append("bankroll_firestore")
        except Exception as e:
            print(f"   ⚠️  Banca Firestore: {e}")
            cleared.append("bankroll_firestore_error")
        
        try:
            await asyncio.to_thread(
                firebase_service.rtdb.child("banca_status/status").update,
                {
                    "saldo_total": 100.0,
                    "lucro_acumulado": 0.0,
                    "base_capital": 100.0,
                    "reset_timestamp": timestamp
                }
            )
            cleared.append("bankroll_rtdb")
        except Exception as e:
            print(f"   ⚠️  Banca RTDB: {e}")
            cleared.append("bankroll_rtdb_error")
        
        # 10. Resetar histórico de trades
        print("📊 Resetando histórico de trades...")
        try:
            # Limpar histórico de trades local
            if hasattr(okx_service, 'trade_history'):
                okx_service.trade_history.clear()
                cleared.append("trade_history")
            
            # Limpar coleção de trades no Firebase
            trades_ref = firebase_service.db.collection("trades")
            docs = trades_ref.stream()
            deleted_count = 0
            for doc in docs:
                try:
                    await asyncio.to_thread(doc.reference.delete)
                    deleted_count += 1
                except:
                    pass
            if deleted_count > 0:
                cleared.append(f"firebase_trades_{deleted_count}_deleted")
            
        except Exception as e:
            print(f"   ⚠️  Histórico de trades: {e}")
            cleared.append("trade_history_error")
        
        print(f"\n🎉 RESET CONCLUÍDO COM SUCESSO!")
        print(f"📊 Items limpos: {len(cleared)}")
        print(f"📋 Detalhes:")
        for item in cleared:
            print(f"   ✅ {item}")
        
        # Relatório
        report = {
            "timestamp": timestamp,
            "action": "NUKE_PAPER_DIRECT",
            "cleared_items": cleared,
            "items_count": len(cleared),
            "status": "SUCCESS"
        }
        
        # Salvar relatório
        report_file = f"reset_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Relatório salvo: {report_file}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERRO DURANTE O RESET: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Função principal"""
    print("🚀 Iniciando reset direto...")
    
    # Executar reset assíncrono
    success = asyncio.run(reset_paper_direct())
    
    if success:
        print("\n🎉 Reset nuclear concluído com sucesso!")
        print("💰 Banca resetada para $100")
        print("🗑️  Posições, moonbags e histórico limpos")
        print("🚀 Sistema pronto para operar em paper mode")
    else:
        print("\n💥 Falha ao executar o reset")
        print("🔍 Verifique os logs e tente novamente")

if __name__ == "__main__":
    main()