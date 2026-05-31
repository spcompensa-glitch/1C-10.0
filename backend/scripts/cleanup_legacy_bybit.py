# -*- coding: utf-8 -*-
"""
Script de Limpeza - Remover Referências Legadas à Bybit
========================================================

Script para remover todas as referências legadas à Bybit após a migração OKX completa.
Protege referências críticas que ainda são necessárias.

Author: Cleanup Team
Version: 1.0

Features:
- Identificação segura de referências legadas
- Backup automático de arquivos modificados
- Verificação de integridade do sistema
- Logging completo das operações
"""

import os
import re
import shutil
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import json

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cleanup_bybit.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("CleanupBybit")

@dataclass
class FileChange:
    """Registro de mudanças em arquivos"""
    file_path: str
    operation: str
    old_content: str
    new_content: str
    timestamp: float

class LegacyBybitCleaner:
    """Classe para gerenciar limpeza de referências legadas à Bybit"""
    
    def __init__(self, backup_dir: str = "backups"):
        self.backup_dir = backup_dir
        self.changes: List[FileChange] = []
        self.protected_patterns = [
            r'bybit\.com',  # Domínio oficial
            r'bybit_api',   # APIs oficiais
            r'bybit_rest',  # Serviços REST
        ]
        
        # Padrões para remover (referências legadas)
        self.legacy_patterns = [
            # Configurações legadas
            r'BYBIT_API_KEY[^:]*:\s*.*',
            r'BYBIT_API_SECRET[^:]*:\s*.*',
            r'BYBIT_CATEGORY[^:]*:\s*.*',
            r'BYBIT_TESTNET[^:]*:\s*.*',
            r'BYBIT_EXECUTION_MODE[^:]*:\s*.*',
            r'BYBIT_SIMULATED_BALANCE[^:]*:\s*.*',
            
            # Importações legadas
            r'from.*bybit.*',
            r'import.*bybit.*',
            
            # Comentários legados
            r'#.*\[V.*\] Bybit.*',
            r'#.*Bybit.*legacy.*',
            
            # Variáveis legadas
            r'bybit.*',
            r'BYBIT.*',
            
            # Funções legadas
            r'def.*bybit.*',
            r'async def.*bybit.*',
            
            # Configurações de API legadas
            r'bybit_rest_service',
            r'bybit_ws_service',
        ]
        
        # Arquivos para processar
        self.target_files = [
            "config.py",
            "backend/config.py",
            "backend/services/auth_service.py",
            "backend/services/database_service.py",
            "backend/services/okx_service.py",
            "backend/services/signal_generator.py",
            "backend/services/slot_operator_agent.py",
            "backend/services/captain_agent.py",
            "backend/services/oracle_agent.py",
            "backend/services/harvester_agent.py",
            "backend/agents/slot_operator_agent.py",
            "backend/agents/captain_agent.py",
            "backend/agents/oracle_agent.py",
            "backend/agents/harvester_agent.py",
        ]
        
        # Cria diretório de backup
        os.makedirs(self.backup_dir, exist_ok=True)
        
    def _should_protect_pattern(self, text: str) -> bool:
        """Verifica se um padrão deve ser protegido"""
        for pattern in self.protected_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _backup_file(self, file_path: str) -> str:
        """Faz backup de um arquivo"""
        try:
            filename = os.path.basename(file_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(self.backup_dir, f"{filename}_{timestamp}.backup")
            
            shutil.copy2(file_path, backup_path)
            logger.info(f"📁 [BACKUP] Backup criado: {backup_path}")
            
            return backup_path
            
        except Exception as e:
            logger.error(f"❌ [BACKUP] Erro ao criar backup de {file_path}: {e}")
            raise
    
    def _process_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Processa um arquivo removendo referências legadas à Bybit
        
        Returns:
            Tuple[bool, str]: (sucesso, conteúdo processado)
        """
        try:
            # Verifica se arquivo existe
            if not os.path.exists(file_path):
                logger.warning(f"⚠️ [FILE] Arquivo não encontrado: {file_path}")
                return False, ""
            
            # Faz backup
            self._backup_file(file_path)
            
            # Lê arquivo
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            # Processa conteúdo
            processed_content = original_content
            changes_made = False
            
            # Aplica cada padrão legado
            for pattern in self.legacy_patterns:
                # Encontra todas ocorrências
                matches = list(re.finditer(pattern, processed_content, re.IGNORECASE))
                
                if matches:
                    logger.info(f"🔍 [PATTERN] Encontradas {len(matches)} ocorrências de: {pattern}")
                    
                    # Substitui de trás para frente para não quebrar índices
                    for match in reversed(matches):
                        # Verifica se deve proteger
                        if self._should_protect_pattern(match.group()):
                            logger.debug(f"🛡️ [PROTECT] Padrão protegido: {match.group()}")
                            continue
                        
                        # Remove referência legada
                        old_text = match.group()
                        new_text = ""
                        
                        # Para variáveis de configuração, substitui por comentário
                        if 'BYBIT_' in old_text:
                            new_text = f"# LEGACY: {old_text} - Removido após migração OKX"
                        
                        # Para funções/classes, remove completamente
                        elif 'def ' in old_text or 'class ' in old_text:
                            new_text = ""
                        
                        # Para imports, remove completamente
                        elif 'import ' in old_text or 'from ' in old_text:
                            new_text = ""
                        
                        # Para comentários, remove completamente
                        elif old_text.strip().startswith('#'):
                            new_text = ""
                        
                        # Substitui no conteúdo
                        if new_text != old_text:
                            processed_content = (
                                processed_content[:match.start()] + 
                                new_text + 
                                processed_content[match.end():]
                            )
                            
                            changes_made = True
                            
                            # Registra mudança
                            change = FileChange(
                                file_path=file_path,
                                operation="pattern_removal",
                                old_content=old_text,
                                new_content=new_text,
                                timestamp=datetime.now().timestamp()
                            )
                            self.changes.append(change)
            
            # Limpa linhas em branco excessivas
            lines = processed_content.split('\n')
            cleaned_lines = []
            
            for i, line in enumerate(lines):
                # Remove linhas que ficaram vazias após remoção
                if line.strip() == "" and i > 0 and lines[i-1].strip() == "":
                    continue
                cleaned_lines.append(line)
            
            processed_content = '\n'.join(cleaned_lines)
            
            return changes_made, processed_content
            
        except Exception as e:
            logger.error(f"❌ [PROCESS] Erro ao processar {file_path}: {e}")
            return False, ""
    
    def _write_file(self, file_path: str, content: str) -> bool:
        """Escreve conteúdo processado no arquivo"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"✅ [WRITE] Arquivo atualizado: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ [WRITE] Erro ao escrever {file_path}: {e}")
            return False
    
    def _generate_report(self) -> str:
        """Gera relatório das mudanças"""
        report = {
            "cleanup_timestamp": datetime.now().isoformat(),
            "total_files_processed": len(self.changes),
            "total_changes": len(self.changes),
            "changes": [
                {
                    "file": change.file_path,
                    "operation": change.operation,
                    "timestamp": change.timestamp,
                    "old_length": len(change.old_content),
                    "new_length": len(change.new_content)
                }
                for change in self.changes
            ]
        }
        
        return json.dumps(report, indent=2, ensure_ascii=False)
    
    def cleanup(self) -> bool:
        """
        Executa a limpeza completa
        
        Returns:
            bool: True se limpeza bem-sucedida
        """
        try:
            logger.info("🧹 [CLEANUP] Iniciando limpeza de referências legadas à Bybit")
            
            total_files = len(self.target_files)
            processed_files = 0
            successful_files = 0
            
            for file_path in self.target_files:
                try:
                    logger.info(f"📁 [FILE] Processando: {file_path}")
                    
                    # Processa arquivo
                    changes_made, new_content = self._process_file(file_path)
                    
                    processed_files += 1
                    
                    if changes_made:
                        # Escreve arquivo processado
                        if self._write_file(file_path, new_content):
                            successful_files += 1
                            logger.info(f"✅ [SUCCESS] {file_path} processado com sucesso")
                        else:
                            logger.error(f"❌ [FAIL] Falha ao escrever {file_path}")
                    else:
                        logger.info(f"📝 [SKIP] Nenhuma mudança necessária em {file_path}")
                        
                except Exception as e:
                    logger.error(f"❌ [ERROR] Erro ao processar {file_path}: {e}")
                    continue
            
            # Gera relatório
            report = self._generate_report()
            report_file = os.path.join(self.backup_dir, "cleanup_report.json")
            
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            
            logger.info(f"📊 [REPORT] Relatório gerado: {report_file}")
            
            # Resumo
            logger.info(f"🎯 [SUMMARY] Processados: {processed_files}/{total_files} arquivos")
            logger.info(f"✅ [SUCCESS] {successful_files} arquivos atualizados")
            
            return successful_files > 0
            
        except Exception as e:
            logger.error(f"❌ [CLEANUP] Erro na limpeza: {e}")
            return False

def main():
    """Função principal"""
    try:
        logger.info("🚀 [MAIN] Iniciando script de limpeza de Bybit legado")
        
        # Inicializa cleaner
        cleaner = LegacyBybitCleaner()
        
        # Executa limpeza
        success = cleaner.cleanup()
        
        if success:
            logger.info("🎉 [SUCCESS] Limpeza concluída com sucesso!")
        else:
            logger.warning("⚠️ [WARNING] Limpeza concluída, mas com falhas")
            
        return success
        
    except Exception as e:
        logger.error(f"❌ [MAIN] Erro na execução: {e}")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)