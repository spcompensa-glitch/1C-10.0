import asyncio
import numpy as np
import pandas as pd
import httpx

def calculate_rsi(prices, period=14):
    """Calcula o RSI (IFR) clássico usando Pandas"""
    df = pd.Series(prices)
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50).tolist()

def check_ifr_divergence(closes, highs, lows, period=14):
    """
    Detecta divergências clássicas no RSI(14)
    Retorna 'BULLISH', 'BEARISH' ou None
    """
    if len(closes) < 30:
        return None
        
    rsi = calculate_rsi(closes, period)
    last_idx = len(closes) - 1
    
    # Bullish Divergence: Preço caindo (fundos menores), RSI subindo (fundos maiores) na sobrevenda (< 35)
    fundos_preco = []
    for i in range(last_idx - 15, last_idx - 1):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            fundos_preco.append((i, lows[i], rsi[i]))
            
    if len(fundos_preco) >= 2:
        fundos_preco = fundos_preco[-2:]
        f1, f2 = fundos_preco[0], fundos_preco[1]
        if f2[1] < f1[1] and f2[2] > f1[2] and f2[2] < 45: # Aumentei o threshold para teste
            return "BULLISH"

    # Bearish Divergence: Preço subindo (topos maiores), RSI caindo (topos menores) na sobrecompra (> 65)
    topos_preco = []
    for i in range(last_idx - 15, last_idx - 1):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            topos_preco.append((i, highs[i], rsi[i]))
            
    if len(topos_preco) >= 2:
        topos_preco = topos_preco[-2:]
        t1, t2 = topos_preco[0], topos_preco[1]
        if t2[1] > t1[1] and t2[2] < t1[2] and t2[2] > 55: # Aumentei o threshold para teste
            return "BEARISH"
            
    return None

def check_volume_climax(volumes, period=20, std_multiplier=1.5): # Reduzido multiplicador para teste
    """
    Verifica se o volume recente (último candle fechado) foi climático
    """
    if len(volumes) < period:
        return False
        
    vol_series = pd.Series(volumes[:-1])
    mean_vol = vol_series.rolling(period).mean().iloc[-1]
    std_vol = vol_series.rolling(period).std().iloc[-1]
    
    threshold = mean_vol + (std_multiplier * std_vol)
    last_closed_volume = volumes[-2]
    
    return last_closed_volume > threshold

def find_pivots_30m(highs, lows, window=2):
    """
    Identifica Topos (Pivot High) e Fundos (Pivot Low) locais
    """
    length = len(highs)
    pivot_highs = []
    pivot_lows = []
    
    for i in range(window, length - window):
        is_high = True
        for w in range(1, window + 1):
            if highs[i] <= highs[i-w] or highs[i] <= highs[i+w]:
                is_high = False
                break
        if is_high:
            pivot_highs.append(highs[i])
            
        is_low = True
        for w in range(1, window + 1):
            if lows[i] >= lows[i-w] or lows[i] >= lows[i+w]:
                is_low = False
                break
        if is_low:
            pivot_lows.append(lows[i])
            
    last_high = pivot_highs[-1] if pivot_highs else highs[-2]
    last_low = pivot_lows[-1] if pivot_lows else lows[-2]
    
    return last_high, last_low

async def test_dvap_simulation(symbol="SOLUSDT"):
    print(f"Iniciando simulacao DVAP direta para {symbol}...")
    try:
        url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}-USDT-SWAP&bar=30m&limit=100"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10)
            if response.status_code != 200:
                print(f"Erro na requisicao: {response.status_code}")
                return
            
            data = response.json()
            list_candles = data.get("result", {}).get("list", [])
            if not list_candles:
                print("Nenhuma kline obtida na resposta.")
                return
                
            candles = list_candles[::-1] # Ordem cronologica (antigas para recentes)
            
            closes = [float(c[4]) for c in candles]
            highs = [float(c[2]) for c in candles]
            lows = [float(c[3]) for c in candles]
            volumes = [float(c[5]) for c in candles]
            
            div = check_ifr_divergence(closes, highs, lows)
            print(f"Divergencia IFR (RSI 14): {div}")
            
            climax = check_volume_climax(volumes)
            print(f"Volume Climax: {climax}")
            
            p_high, p_low = find_pivots_30m(highs, lows)
            print(f"Ultimo Pivot High: {p_high}")
            print(f"Ultimo Pivot Low: {p_low}")
            
            current_close = closes[-1]
            prev_close = closes[-2]
            print(f"Preco Fechamento Atual: {current_close} | Anterior: {prev_close}")
            
            choch_buy = current_close > p_high and prev_close <= p_high
            choch_sell = current_close < p_low and prev_close >= p_low
            print(f"Gatilho CHoCH COMPRA (Cruzar Pivot High {p_high}): {choch_buy}")
            print(f"Gatilho CHoCH VENDA (Cruzar Pivot Low {p_low}): {choch_sell}")
            
            if choch_buy:
                amplitude = abs(current_close - p_low)
                tp1 = current_close + (amplitude * 1.618)
                tp2 = current_close + (amplitude * 2.618)
                print(f"SINAL GERADO: COMPRA | Entrada = {current_close} | SL = {p_low} | TP1 = {tp1:.4f} | TP2 = {tp2:.4f}")
            elif choch_sell:
                amplitude = abs(current_close - p_high)
                tp1 = current_close - (amplitude * 1.618)
                tp2 = current_close - (amplitude * 2.618)
                print(f"SINAL GERADO: VENDA | Entrada = {current_close} | SL = {p_high} | TP1 = {tp1:.4f} | TP2 = {tp2:.4f}")
            else:
                print("Aguardando gatilho de CHoCH...")
                
    except Exception as e:
        print(f"Erro na simulacao: {e}")

if __name__ == "__main__":
    asyncio.run(test_dvap_simulation())
