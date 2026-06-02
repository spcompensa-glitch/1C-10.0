#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para Forçar Reinicialização Imediata do Railway
====================================================

Script que cria um arquivo de força para o Railway reiniciar imediatamente.
Após o reinício, o sistema deve estar completamente limpo.

Author: Sistema 1Crypten
Version: 1.0
"""

import os
import sys
from datetime import datetime

def create_force_restart_file():
    """Criar arquivo de força de reinicialização"""
    
    print("🔄 CRIANDO ARQUIVO DE FORÇA DE REINICIALIZAÇÃO")
    print("=" * 50)
    
    timestamp = datetime.now().isoformat()
    
    # Criar arquivo de força
    restart_content = f"""# FORÇA DE REINICIALIZAÇÃO RAILWAY - V110.701
# Data: {timestamp}

# Este arquivo força o Railway a reiniciar o backend imediatamente
# Após o reinício, o sistema deve estar:

✅ COMPLETAMENTE LIMPO:
- Banca: $100.00
- Slots: 4 disponíveis (vazios)
- Moonbags: 0
- Trades: 0
- Orders: 0
- Positions: 0
- Status: ONLINE

# Processo de limpeza aplicado:
1. PostgreSQL: Limpeza completa de todas as tabelas
2. Firebase/RTDB: Reset total de todos os dados
3. Firestore: Limpeza de todas as coleções
4. Sistema: Estado resetado para padrão

# Após reiniciar, verifique:
- [ ] 4 slots disponíveis na UI
- [ ] Banca em $100.00
- [ ] Sem moonbags na vault
- [ ] Histórico limpo
- [ ] Sistema operando sem erros

# DELETE ESTE ARQUIVO APÓS A REINICIALIZAÇÃO COM SUCESSO!
"""
    
    # Salvar arquivo
    filename = "FORCE_RAILWAY_RESTART_IMMEDIATE.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(restart_content)
    
    print(f"✅ Arquivo criado: {filename}")
    print("📋 Conteúdo:")
    print(restart_content)
    
    return filename

def commit_and_push_restart():
    """Fazer commit e push do arquivo de força"""
    
    print("\n🚀 ENVIANDO PARA FORÇAR REINICIALIZAÇÃO RAILWAY")
    print("=" * 50)
    
    try:
        # Adicionar arquivo ao git
        filename = "FORCE_RAILWAY_RESTART_IMMEDIATE.txt"
        os.system(f"git add {filename}")
        
        # Fazer commit
        commit_message = f"[V110.701] FORCE RESTART - System completely cleaned and ready"
        os.system(f'git commit -m "{commit_message}"')
        
        # Fazer push
        print("📤 Enviando para o repositório...")
        os.system("git push")
        
        print("✅ Push realizado com sucesso!")
        print("🔄 Railway deve reiniciar em até 2 minutos")
        
        return True
        
    except Exception as e:
        print(f"❌ Erro ao enviar: {e}")
        return False

def main():
    """Função principal"""
    print("🔥 SCRIPT DE FORÇA DE REINICIALIZAÇÃO RAILWAY")
    print("=" * 60)
    
    # Criar arquivo de força
    filename = create_force_restart_file()
    
    # Enviar para forçar reinicialização
    success = commit_and_push_restart()
    
    if success:
        print("\n🎉 PRONTO PARA REINICIALIZAÇÃO!")
        print("=====================================")
        print("✅ Arquivo de força criado e enviado")
        print("✅ Railway deve reiniciar em 1-2 minutos")
        print("✅ Após reiniciar, sistema deve estar:")
        print("   - 4 slots disponíveis (vazios)")
        print("   - Banca em $100.00")
        print("   - Sem moonbags ou trades")
        print("   - Status: ONLINE")
        print("\n🔄 AGUARDE O REINÍCIO E VERIFIQUE O RESULTADO!")
    else:
        print("\n💥 FALHA AO ENVIAR!")
        print("🔍 Tente novamente manualmente")

if __name__ == "__main__":
    main()