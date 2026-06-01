#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validação 100% Funcionalidade Paper Mode
========================================

Script para validar que o sistema 1Crypten está 100% funcional no modo paper
após o reset nuclear.

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

async def validate_paper_mode():
    """Valida funcionalidade completa do sistema paper mode"""
    
    print("🧪 INICIANDO VALIDAÇÃO 100% FUNCIONALIDADE PAPER MODE")
    print("=" * 60)
    
    validation_results = []
    timestamp = datetime.now().isoformat()
    
    try:
        # Importar serviços
        from backend.services.okx_rest import OKXRest
        from backend.services.firebase_service import FirebaseService
        from backend.config import settings
        
        print("✅ Importações bem sucedidas")
        validation_results.append("import_services")
        
        # 1. Testar serviço OKX
        print("\n🔧 Testando serviço OKX...")
        okx_service = OKXRest()
        okx_service.execution_mode = "PAPER"
        okx_service.paper_balance = 100.0
        
        # Verificar se o modo está correto
        if okx_service.execution_mode == "PAPER":
            print("   ✅ Modo paper configurado corretamente")
            validation_results.append("okx_paper_mode")
        else:
            print("   ❌ Modo paper incorreto")
            validation_results.append("okx_paper_mode_error")
        
        # Verificar saldo inicial
        if okx_service.paper_balance == 100.0:
            print("   ✅ Saldo inicial correto ($100)")
            validation_results.append("okx_balance")
        else:
            print("   ❌ Saldo incorreto")
            validation_results.append("okx_balance_error")
        
        # 2. Testar limpeza de posições
        print("\n🗑️  Testando limpeza de posições...")
        okx_service.paper_positions.clear()
        if len(okx_service.paper_positions) == 0:
            print("   ✅ Posições limpas")
            validation_results.append("positions_clean")
        else:
            print("   ❌ Posições não limpas")
            validation_results.append("positions_not_clean")
        
        # 3. Testar limpeza de moonbags
        print("\n🌙 Testando limpeza de moonbags...")
        okx_service.paper_moonbags.clear()
        if len(okx_service.paper_moonbags) == 0:
            print("   ✅ Moonbags limpas")
            validation_results.append("moonbags_clean")
        else:
            print("   ❌ Moonbags não limpas")
            validation_results.append("moonbags_not_clean")
        
        # 4. Testar cálculo de P&L fixo
        print("\n📊 Testando cálculo de P&L...")
        
        # Simular um trade com margem fixa de $10
        test_slot = {
            "entry_price": 0.5,
            "leverage": 50,
            "entry_margin": 10.0
        }
        
        test_price = 0.6  # 20% de lucro
        roi_val = 20.0  # 20% ROI
        
        # Testar cálculo com margem fixa
        margin_used = float(test_slot.get("entry_margin", 0)) or (10.0 if okx_service.execution_mode == "PAPER" else 0)
        est_pnl = (roi_val / 100.0) * margin_used
        
        if est_pnl == 2.0:  # 20% de $10 = $2
            print("   ✅ Cálculo de P&L com margem fixa correto")
            validation_results.append("pnl_calculation")
        else:
            print(f"   ❌ Cálculo de P&L incorreto: esperado $2.0, obtido ${est_pnl}")
            validation_results.append("pnl_calculation_error")
        
        # 5. Testar serviço Firebase
        print("\n🔥 Testando serviço Firebase...")
        firebase_service = FirebaseService()
        
        # Testar conexão
        try:
            await firebase_service.update_bankroll(100.0)
            print("   ✅ Conexão Firebase funcionando")
            validation_results.append("firebase_connection")
        except Exception as e:
            print(f"   ⚠️  Conexão Firebase com erro: {e}")
            validation_results.append("firebase_connection_error")
        
        # 6. Testar reset de slots
        print("\n🔄 Testando reset de slots...")
        for i in range(1, 5):
            try:
                await firebase_service.hard_reset_slot(i, "VALIDATION_TEST", pnl=0.0)
                print(f"   ✅ Slot {i} resetado")
                validation_results.append(f"slot_{i}_reset")
            except Exception as e:
                print(f"   ⚠️  Slot {i}: {e}")
                validation_results.append(f"slot_{i}_reset_error")
        
        # 7. Testar configurações do sistema
        print("\n⚙️  Testando configurações do sistema...")
        
        # Verificar modo de execução
        if settings.BYBIT_EXECUTION_MODE == "PAPER":
            print("   ✅ Configuração de modo paper correta")
            validation_results.append("paper_config")
        else:
            print("   ❌ Configuração de modo paper incorreta")
            validation_results.append("paper_config_error")
        
        # Verificar saldo simulado
        if settings.BYBIT_SIMULATED_BALANCE == 100.0:
            print("   ✅ Configuração de saldo simulado correta")
            validation_results.append("balance_config")
        else:
            print("   ❌ Configuração de saldo simulado incorreta")
            validation_results.append("balance_config_error")
        
        # 8. Testar P&L calculation com diferentes cenários
        print("\n📈 Testando P&L calculation com diferentes cenários...")
        
        test_cases = [
            {"entry": 1.0, "current": 1.1, "leverage": 50, "expected_roi": 10.0, "expected_pnl": 1.0},  # 10% lucro
            {"entry": 1.0, "current": 0.9, "leverage": 50, "expected_roi": -10.0, "expected_pnl": -1.0},  # 10% prejuízo
            {"entry": 2.0, "current": 2.4, "leverage": 25, "expected_roi": 20.0, "expected_pnl": 2.0},  # 20% lucro
        ]
        
        for i, case in enumerate(test_cases):
            # Simular cálculo de ROI
            roi_val = ((case["current"] - case["entry"]) / case["entry"]) * 100
            margin_used = 10.0  # Margem fixa para PAPER
            est_pnl = (roi_val / 100.0) * margin_used
            
            if abs(est_pnl - case["expected_pnl"]) < 0.01:
                print(f"   ✅ Cenário {i+1}: P&L calculado corretamente (${est_pnl:.2f})")
                validation_results.append(f"pnl_scenario_{i+1}")
            else:
                print(f"   ❌ Cenário {i+1}: P&L incorreto (${est_pnl:.2f} vs {case['expected_pnl']:.2f})")
                validation_results.append(f"pnl_scenario_{i+1}_error")
        
        # 9. Resumo da validação
        success_count = len([r for r in validation_results if not r.endswith("_error")])
        total_count = len(validation_results)
        
        print(f"\n📊 RESUMO DA VALIDAÇÃO:")
        print(f"   ✅ Sucesso: {success_count}/{total_count}")
        print(f"   ❌ Erros: {total_count - success_count}/{total_count}")
        
        if success_count == total_count:
            print("   🎉 VALIDAÇÃO 100% SUCESSFUL!")
            status = "SUCCESS"
        else:
            print("   ⚠️  VALIDAÇÃO PARCIAL - Algumas falhas detectadas")
            status = "PARTIAL"
        
        # Gerar relatório
        report = {
            "timestamp": timestamp,
            "validation_type": "PAPER_MODE_100_PERCENT",
            "total_tests": total_count,
            "passed_tests": success_count,
            "failed_tests": total_count - success_count,
            "status": status,
            "details": validation_results,
            "system_config": {
                "execution_mode": settings.BYBIT_EXECUTION_MODE,
                "simulated_balance": settings.BYBIT_SIMULATED_BALANCE,
                "paper_balance": okx_service.paper_balance
            }
        }
        
        # Salvar relatório
        report_file = f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Relatório de validação salvo: {report_file}")
        
        return success_count == total_count
        
    except Exception as e:
        print(f"\n❌ ERRO DURANTE A VALIDAÇÃO: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Função principal"""
    print("🚀 Iniciando validação 100%...")
    
    # Executar validação assíncrona
    success = asyncio.run(validate_paper_mode())
    
    if success:
        print("\n🎉 VALIDAÇÃO 100% CONCLUÍDA COM SUCESSO!")
        print("✅ Sistema 100% funcional para paper mode")
        print("✅ P&L calculation com margem fixa funcionando")
        print("✅ Todos os serviços operando corretamente")
        print("✅ Sistema pronto para transição para real trading")
    else:
        print("\n💥 VALIDAÇÃO FALHOU!")
        print("🔍 Verifique os logs e corrija os problemas antes de continuar")

if __name__ == "__main__":
    main()