import asyncio
import httpx

async def main():
    coins = ["SOL", "AVAX", "LINK", "MATIC", "ADA", "XRP", "DOGE", "DOT", "INJ", "OP", "ARB", "GALA", "SAND", "MANA", "APT", "SUI"]
    
    print(f"{'Coin':<6} | {'Price':<8} | {'ctVal':<6} | {'minSz':<6} | {'Min Notional':<13} | {'Min Margin (50x)'}")
    print("-" * 65)
    
    async with httpx.AsyncClient() as client:
        for coin in coins:
            try:
                inst_id = f"{coin}-USDT-SWAP"
                
                # Get instrument specs
                url_inst = f"https://www.okx.com/api/v5/public/instruments?instType=SWAP&instId={inst_id}"
                res_inst = await client.get(url_inst)
                data_inst = res_inst.json().get("data", [])
                if not data_inst:
                    continue
                
                spec = data_inst[0]
                ct_val = float(spec["ctVal"])
                min_sz = float(spec["minSz"])
                
                # Get ticker
                url_tick = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
                res_tick = await client.get(url_tick)
                data_tick = res_tick.json().get("data", [])
                if not data_tick:
                    continue
                    
                price = float(data_tick[0]["last"])
                
                # Calculate
                min_notional = price * ct_val * min_sz
                min_margin = min_notional / 50.0
                
                print(f"{coin:<6} | ${price:<7.4f} | {ct_val:<6} | {min_sz:<6} | ${min_notional:<12.4f} | ${min_margin:.4f}")
                
            except Exception as e:
                pass

if __name__ == "__main__":
    asyncio.run(main())
