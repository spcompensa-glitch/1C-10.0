#!/usr/bin/env python3
"""
Script para corrigir templates problemáticos
"""
import re

def fix_templates():
    """Corrige templates problemáticos"""
    try:
        with open('frontend/cockpit.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Lista de templates problemáticos identificados
        problematic_templates = [
            (r'span className={`text-\[8px\] font-black tracking-widest uppercase ${\n                                            isTsunami \? \'text-red-400\' :\n                                            oracleStatus === \'STABILIZING\' \? \'text-amber-400\' : \'text-green-400\'\n                                        }`}', 
             'span className={`text-[8px] font-black tracking-widest uppercase ${isTsunami ? \'text-red-400\' : oracleStatus === \'STABILIZING\' ? \'text-amber-400\' : \'text-green-400\'}`}'),
            
            (r'span className={`w-1.5 h-1.5 rounded-full animate-pulse ${\n                                            isTsunami \? \'bg-red-500 shadow-\[0_0_8px_rgba\(239,68,68,0.8\)\]\' :\n                                            oracleStatus === \'STABILIZING\' \? \'bg-amber-400 shadow-\[0_0_8px_rgba\(251,191,36,0.6\)\]\' : \'bg-green-500 shadow-\[0_0_8px_rgba\(34,197,94,0.6\)\]\'\n                                        }`}',
             'span className={`w-1.5 h-1.5 rounded-full animate-pulse ${isTsunami ? \'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]\' : oracleStatus === \'STABILIZING\' ? \'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)]\' : \'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]`}}'),
        ]
        
        print("🔍 Corrigindo templates...")
        
        for old_pattern, new_pattern in problematic_templates:
            if old_pattern in content:
                content = content.replace(old_pattern, new_pattern)
                print(f"✅ Template corrigido")
            else:
                print(f"⚠️ Template não encontrado")
        
        # Salvar o arquivo corrigido
        with open('frontend/cockpit.html', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("🎉 Templates corrigidos!")
        
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    fix_templates()