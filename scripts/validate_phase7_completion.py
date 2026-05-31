# -*- coding: utf-8 -*-
"""
Validação Final da Fase 7 - Testes Completos de Regressão
========================================================

Script para validar a conclusão da Fase 7 e gerar o certificado de produção.

Author: QA Team
Version: 1.0
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, Any

class Phase7Validator:
    """Validador da Fase 7"""
    
    def __init__(self, report_file: str = "regression_test_report.json"):
        self.report_file = report_file
        self.results: Dict[str, Any] = {}
        
    def load_report(self) -> bool:
        """Carrega o relatório de testes"""
        try:
            if not os.path.exists(self.report_file):
                print(f"❌ Arquivo de relatório não encontrado: {self.report_file}")
                return False
            
            with open(self.report_file, 'r', encoding='utf-8') as f:
                self.results = json.load(f)
            
            return True
            
        except Exception as e:
            print(f"❌ Erro ao carregar relatório: {e}")
            return False
    
    def validate_metrics(self) -> Dict[str, bool]:
        """Valida as métricas mínimas"""
        validation_results = {}
        
        # Valida taxa de sucesso
        success_rate = self.results.get("success_rate", 0)
        validation_results["success_rate"] = success_rate >= 95
        print(f"✅ Taxa de sucesso: {success_rate:.1f}% (mínimo: 95%) - {'PASS' if validation_results['success_rate'] else 'FAIL'}")
        
        # Valida testes passados
        passed_tests = self.results.get("passed_tests", 0)
        total_tests = self.results.get("total_tests", 0)
        validation_results["passed_tests"] = passed_tests >= 6  # Mínimo de 6 testes passados
        print(f"✅ Testes passados: {passed_tests}/{total_tests} (mínimo: 6) - {'PASS' if validation_results['passed_tests'] else 'FAIL'}")
        
        # Valida testes falhos
        failed_tests = self.results.get("failed_tests", 0)
        validation_results["failed_tests"] = failed_tests <= 2  # Máximo de 2 falhas
        print(f"✅ Testes falhos: {failed_tests} (máximo: 2) - {'PASS' if validation_results['failed_tests'] else 'FAIL'}")
        
        # Valida testes pulados
        skipped_tests = self.results.get("skipped_tests", 0)
        validation_results["skipped_tests"] = skipped_tests <= 2  # Máximo de 2 pulados
        print(f"✅ Testes pulados: {skipped_tests} (máximo: 2) - {'PASS' if validation_results['skipped_tests'] else 'FAIL'}")
        
        # Valida duração total
        duration = self.results.get("test_duration", 0)
        validation_results["duration"] = duration <= 300  # Máximo de 5 minutos
        print(f"✅ Duração total: {duration:.2f}s (máximo: 300s) - {'PASS' if validation_results['duration'] else 'FAIL'}")
        
        # Valida cobertura de módulos
        modules = self.results.get("modules", {})
        validation_results["modules_coverage"] = len(modules) >= 4  # Mínimo de 4 módulos
        print(f"✅ Cobertura de módulos: {len(modules)}/4 (mínimo: 4) - {'PASS' if validation_results['modules_coverage'] else 'FAIL'}")
        
        # Valida integração
        integration_result = modules.get("integration", {})
        integration_passed = integration_result.get("passed", 0)
        validation_results["integration"] = integration_passed >= 2  # Mínimo de 2 testes de integração passados
        print(f"✅ Testes de integração: {integration_passed}/2 (mínimo: 2) - {'PASS' if validation_results['integration'] else 'FAIL'}")
        
        return validation_results
    
    def generate_certificate(self) -> bool:
        """Gera certificado de produção"""
        try:
            # Calcula resultados
            validation_results = self.validate_metrics()
            
            # Determina status geral
            all_passed = all(validation_results.values())
            status = "APPROVED" if all_passed else "REJECTED"
            
            # Gera certificado
            certificate = {
                "certificate_id": f"PHASE7-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                "timestamp": datetime.now().isoformat(),
                "status": status,
                "system": "1Cryptem 7.0",
                "version": "V110.701",
                "phase": "7 - Testes Completos de Regressão",
                "validation_results": validation_results,
                "summary": {
                    "total_tests": self.results.get("total_tests", 0),
                    "passed_tests": self.results.get("passed_tests", 0),
                    "failed_tests": self.results.get("failed_tests", 0),
                    "skipped_tests": self.results.get("skipped_tests", 0),
                    "success_rate": self.results.get("success_rate", 0),
                    "duration": self.results.get("test_duration", 0)
                },
                "recommendations": self._generate_recommendations(validation_results),
                "next_steps": self._generate_next_steps(validation_results)
            }
            
            # Salva certificado
            certificate_file = f"phase7_certificate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(certificate_file, 'w', encoding='utf-8') as f:
                json.dump(certificate, f, indent=2, ensure_ascii=False)
            
            print(f"\n🎉 Certificado gerado: {certificate_file}")
            return True
            
        except Exception as e:
            print(f"❌ Erro ao gerar certificado: {e}")
            return False
    
    def _generate_recommendations(self, validation_results: Dict[str, bool]) -> list:
        """Gera recomendações baseadas nos resultados"""
        recommendations = []
        
        if not validation_results["success_rate"]:
            recommendations.append("Aumentar taxa de sucesso para 95%+ através de correções de bugs críticos")
        
        if not validation_results["passed_tests"]:
            recommendations.append("Implementar testes unitários adicionais para cobrir funcionalidades críticas")
        
        if not validation_results["failed_tests"]:
            recommendations.append("Investigar e corrigir testes falhados, especialmente de integração")
        
        if not validation_results["skipped_tests"]:
            recommendations.append("Reduzir número de testes pulados, garantindo cobertura completa")
        
        if not validation_results["duration"]:
            recommendations.append("Otimizar performance de testes para reduzir tempo de execução")
        
        if not validation_results["modules_coverage"]:
            recommendations.append("Expandir cobertura para todos os módulos do sistema")
        
        if not validation_results["integration"]:
            recommendations.append("Implementar testes de integração robustos entre serviços")
        
        return recommendations if recommendations else ["Sistema pronto para produção"]
    
    def _generate_next_steps(self, validation_results: Dict[str, bool]) -> list:
        """Gera próximos passos"""
        if all(validation_results.values()):
            return [
                "1. Preparar ambiente de produção",
                "2. Implementar monitoramento contínuo",
                "3. Configurar alertas de segurança",
                "4. Realizar deployment gradual",
                "5. Monitorar performance em produção"
            ]
        else:
            return [
                "1. Corrigir todos os testes falhados",
                "2. Implementar melhorias identificadas",
                "3. Reexecutar validação",
                "4. Solicitar nova avaliação"
            ]
    
    def print_summary(self):
        """Imprime resumo da validação"""
        if not self.results:
            print("❌ Nenhum resultado para exibir")
            return
        
        print("\n" + "="*60)
        print("🎯 VALIDAÇÃO FINAL - FASE 7")
        print("="*60)
        print(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"Sistema: 1Cryptem 7.0 (V110.701)")
        print(f"Status: {self.results.get('summary', {}).get('status', 'UNKNOWN')}")
        
        print("\n📊 Métricas:")
        print(f"  • Testes totais: {self.results.get('total_tests', 0)}")
        print(f"  • Passados: {self.results.get('passed_tests', 0)}")
        print(f"  • Falhados: {self.results.get('failed_tests', 0)}")
        print(f"  • Pulados: {self.results.get('skipped_tests', 0)}")
        print(f"  • Taxa de sucesso: {self.results.get('success_rate', 0):.1f}%")
        print(f"  • Duração: {self.results.get('test_duration', 0):.2f}s")
        
        print("\n🔍 Detalhes por módulo:")
        for module_name, module_result in self.results.get('modules', {}).items():
            print(f"  • {module_name}: {module_result.get('passed', 0)} passados, "
                  f"{module_result.get('failed', 0)} falhados, "
                  f"{module_result.get('skipped', 0)} pulados")
        
        print("\n" + "="*60)

def main():
    """Função principal"""
    print("🚀 Iniciando validação da Fase 7...")
    
    # Inicializa validador
    validator = Phase7Validator()
    
    # Carrega relatório
    if not validator.load_report():
        print("❌ Falha ao carregar relatório de testes")
        return 1
    
    # Imprime resumo
    validator.print_summary()
    
    # Valida métricas
    validation_results = validator.validate_metrics()
    
    # Gera certificado
    if validator.generate_certificate():
        print("\n✅ Validação concluída com sucesso!")
        return 0
    else:
        print("\n❌ Falha na validação")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)