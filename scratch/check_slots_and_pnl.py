import asyncio
import asyncpg
import os
import sys

# DATABASE_URL do Railway
DATABASE_URL = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"

async def check_slots_and_pnl():
    print("=" * 70)
    print("🛰️ AUDITORIA EM TEMPO REAL DOS SLOTS - 1CRYPTEN SPACE")
    print("=" * 70)
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # 1. Banca Status
        banca = await conn.fetchrow("SELECT saldo_total, risco_real_percent, status FROM banca_status WHERE id = 1")
        if banca:
            print(f"\n📊 BANCA SIMULADA (PAPER MODE):")
            print(f"   Saldo Total: ${float(banca['saldo_total']):.2f}")
            print(f"   Risco Real: {float(banca['risco_real_percent']):.2f}%")
            print(f"   Status da Banca: {banca['status']}")
        
        # 2. Slots Ativos
        slots = await conn.fetch("""
            SELECT id, symbol, side, qty, entry_price, current_stop, 
                   target_price, pnl_percent, status_risco, pensamento, score, leverage
            FROM slots 
            ORDER BY id
        """)
        
        print(f"\n⚡ DETALHAMENTO DE SLOTS OPERACIONAIS:")
        for s in slots:
            slot_id = s['id']
            symbol = s['symbol']
            
            if symbol:
                print(f"\n🔴 [SLOT {slot_id}] - ATIVO: {symbol} ({s['side'].upper()})")
                print(f"   Score do Sinal: {s['score']}/100")
                print(f"   Alavancagem: {s['leverage']}x")
                print(f"   Quantidade: {float(s['qty']):.4f}")
                print(f"   Preço de Entrada: ${float(s['entry_price']):.4f}")
                print(f"   Stop Loss Dinâmico (Escadinha): ${float(s['current_stop']):.4f}")
                print(f"   Take Profit Alvo (R:R 2:1): ${float(s['target_price']):.4f}")
                print(f"   PnL / ROI em Tempo Real: {float(s['pnl_percent']):.2f}%")
                print(f"   Status de Risco na UI: {s['status_risco']}")
                print(f"   Pensamento do Capitão: {s['pensamento']}")
            else:
                print(f"\n🟢 [SLOT {slot_id}] - LIVRE")
                print(f"   Status de Risco na UI: {s['status_risco']}")
                
        print("\n" + "=" * 70)
        
    except Exception as e:
        print(f"\n❌ ERRO NA AUDITORIA: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_slots_and_pnl())
