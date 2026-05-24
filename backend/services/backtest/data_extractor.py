import os
import sys
import sqlite3
import time
import urllib.request
import json
import logging

# Adiciona o diretório backend ao PATH para permitir importações de config e outros serviços
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataExtractor")

# Ensure DB is created in backend folder
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "backtest_data.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Create klines table
    c.execute('''
        CREATE TABLE IF NOT EXISTS klines (
            symbol TEXT,
            interval TEXT,
            start_time INTEGER,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, turnover REAL,
            PRIMARY KEY (symbol, interval, start_time)
        )
    ''')
    # Create eligible pairs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS eligible_pairs (
            symbol TEXT PRIMARY KEY,
            max_leverage INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def get_last_timestamp(symbol: str, interval: str) -> int:
    """Retorna o timestamp da última vela salva para um par/intervalo."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT MAX(start_time) FROM klines WHERE symbol = ? AND interval = ?", (symbol, interval))
        res = c.fetchone()
        conn.close()
        return res[0] if res and res[0] else 0
    except:
        return 0

def get_monitored_from_db():
    """Retorna todos os símbolos que já possuem algum dado no banco local."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT DISTINCT symbol FROM klines")
        symbols = [row[0] for row in c.fetchall()]
        conn.close()
        return symbols
    except:
        return []

def get_eligible_pairs():
    """Fetches eligible pairs from OKX Mainnet that match max leverage >= 50 and are not in blocklist."""
    try:
        url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if data.get("code") != "0":
            logger.error(f"Error fetching instruments from OKX: {data}")
            return []

        blocklist = settings.ASSET_BLOCKLIST
        eligible = []

        for item in data["data"]:
            inst_id = item["instId"]
            state = item["state"]
            if state != "live":
                continue
            
            # Filtra apenas futuros lineares em USDT
            if not inst_id.endswith("-USDT-SWAP"):
                continue

            # Converter para símbolo formato limpo/bybit (e.g. BTCUSDT)
            symbol = inst_id.replace("-SWAP", "").replace("-", "")

            # Check blocklist
            if symbol in blocklist:
                continue

            max_leverage = float(item.get("lever", 0))

            if max_leverage >= 50:
                eligible.append((symbol, int(max_leverage)))

        logger.info(f"Retrieved {len(eligible)} eligible pairs from OKX.")
        
        # Save to DB
        conn = get_db_connection()
        c = conn.cursor()
        c.executemany("REPLACE INTO eligible_pairs (symbol, max_leverage) VALUES (?, ?)", eligible)
        conn.commit()
        conn.close()
        
        return eligible
    except Exception as e:
        logger.error(f"Failed to get eligible pairs from OKX: {e}")
        return []

def download_klines(symbol: str, interval: str, limit: int = 1000, start_time: int = None):
    """
    Downloads klines from OKX public API. Mapped to match local DB kline schema.
    Intervals: 5m, 15m, 1h, 2h, 4h.
    """
    try:
        # Rate limit safety (0.05s sleep)
        time.sleep(0.05)
        
        # Mapeamento do intervalo Bybit/Local -> OKX
        okx_interval = interval
        if interval == "1h": okx_interval = "1H"
        elif interval == "2h": okx_interval = "2H"
        elif interval == "4h": okx_interval = "4H"
        elif interval == "15m": okx_interval = "15m"
        elif interval == "5m": okx_interval = "5m"
        
        # Formatar símbolo para formato OKX (e.g. BTCUSDT -> BTC-USDT-SWAP)
        if symbol.endswith("USDT"):
            inst_id = f"{symbol[:-4]}-USDT-SWAP"
        elif symbol.endswith("USDC"):
            inst_id = f"{symbol[:-4]}-USDC-SWAP"
        else:
            inst_id = f"{symbol}-USDT-SWAP"

        # OKX pública para candles (/candles)
        # Retorna até 100 candles de forma sã e veloz
        limit_request = min(limit, 100)
        
        url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={okx_interval}&limit={limit_request}"

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if data.get("code") != "0":
            logger.error(f"Error fetching klines for {symbol} {interval} from OKX: {data}")
            return 0

        kline_list = data.get("data", [])
        if not kline_list:
            return 0

        records = []
        for k in kline_list:
            # OKX retorna: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
            records.append((
                symbol, 
                interval, 
                int(k[0]), # ts
                float(k[1]), # o
                float(k[2]), # h
                float(k[3]), # l
                float(k[4]), # c
                float(k[5]), # vol
                float(k[6]) if len(k) > 6 else 0.0 # volCcy
            ))
            
        conn = get_db_connection()
        c = conn.cursor()
        c.executemany('''
            INSERT OR IGNORE INTO klines 
            (symbol, interval, start_time, open, high, low, close, volume, turnover) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', records)
        conn.commit()
        conn.close()
        
        logger.info(f"Saved {len(records)} klines from OKX for {symbol} ({interval})")
        return len(records)

    except Exception as e:
        logger.error(f"Failed to download OKX klines: {e}")
        return 0

if __name__ == "__main__":
    init_db()
    # Test execution
    pairs = get_eligible_pairs()
    if pairs:
        test_symbol = pairs[0][0]
        download_klines(test_symbol, "1h", limit=50)
