#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para corrigir URLs hardcoded no frontend
"""

import os
import re
from pathlib import Path

def fix_frontend_urls():
    """Substitui URLs hardcoded por window.location.origin"""
    
    frontend_dir = Path("frontend")
    if not frontend_dir.exists():
        print("❌ Diretório frontend não encontrado")
        return False
    
    # Padrões para substituir
    patterns = [
        (r"'https://1crypten.space'", "window.location.origin"),
        (r'"https://1crypten.space"', 'window.location.origin'),
    ]
    
    files_changed = 0
    
    # Processar arquivos JavaScript
    for js_file in frontend_dir.rglob("*.js"):
        try:
            with open(js_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Aplicar substituições
            for pattern, replacement in patterns:
                content = re.sub(pattern, replacement, content)
            
            # Se houve mudanças, salvar o arquivo
            if content != original_content:
                with open(js_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"✅ Corrigido: {js_file}")
                files_changed += 1
                
        except Exception as e:
            print(f"❌ Erro ao processar {js_file}: {e}")
    
    # Processar arquivos HTML
    for html_file in frontend_dir.rglob("*.html"):
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            
            # Aplicar substituições
            for pattern, replacement in patterns:
                content = re.sub(pattern, replacement, content)
            
            # Se houve mudanças, salvar o arquivo
            if content != original_content:
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"✅ Corrigido: {html_file}")
                files_changed += 1
                
        except Exception as e:
            print(f"❌ Erro ao processar {html_file}: {e}")
    
    print(f"\n🎉 Total de arquivos corrigidos: {files_changed}")
    return files_changed > 0

if __name__ == "__main__":
    fix_frontend_urls()