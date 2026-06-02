import asyncio
import pandas as pd
import os
import sys
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.signal_generator import signal_generator
from services.chart_renderer import chart_renderer
from services.okx_rest import okx_rest_service

async def test_123():
    symbol = "BTCUSDT.P"
    print(f"Testing 1-2-3 for {symbol}...")
    
    # 1. Detect Pattern
    pattern = await signal_generator.detect_123_pattern(symbol, interval="1h", limit=100)
    print(f"Pattern detected: {pattern.get('detected')} (Side: {pattern.get('side')})")
    
    if pattern.get('detected'):
        # 2. Fetch Klines for rendering
        klines = await okx_rest_service.get_klines(symbol=symbol, interval="1h", limit=200)
        c = klines[::-1]
        df = pd.DataFrame(c, columns=['start_time', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        df['start_time'] = pd.to_datetime(df['start_time'].astype(float), unit='ms')
        df.set_index('start_time', inplace=True)
        df = df.astype(float)
        
        # 3. Render Chart
        path = chart_renderer.render_chart(
            symbol=symbol,
            df=df,
            pattern_123=pattern
        )
        print(f"Chart rendered at: {path}")
    else:
        print("No 1-2-3 pattern detected currently. Try another symbol or check logic.")

if __name__ == "__main__":
    asyncio.run(test_123())
