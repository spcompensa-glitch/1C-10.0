from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import sqlite3
import os
import logging
from typing import List, Optional

from services.backtest import data_extractor
from services.backtest.engine import backtest_engine
from services.agents.librarian import librarian_agent

logger = logging.getLogger("BacktestRoutes")
router = APIRouter(prefix="/api/backtest", tags=["Backtest"])

class DownloadRequest(BaseModel):
    symbols: Optional[List[str]] = None  # If None, download all eligible
    timeframes: List[str] = ["4h", "2h", "1h", "15m", "5m"]
    limit: int = 1000

def run_download_task(symbols: List[str], timeframes: List[str], limit: int):
    logger.info(f"Starting background download task for {len(symbols)} symbols")
    data_extractor.init_db()
    for sym in symbols:
        for tf in timeframes:
            try:
                data_extractor.download_klines(sym, tf, limit=limit)
            except Exception as e:
                logger.error(f"Error downloading {sym} {tf}: {e}")
    logger.info("Background download task finished.")

@router.post("/download")
async def trigger_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    """Triggers a background download for historical data."""
    try:
        data_extractor.init_db()
        if not req.symbols:
            eligible = data_extractor.get_eligible_pairs()
            targets = [s[0] for s in eligible]
        else:
            targets = req.symbols
            
        background_tasks.add_task(run_download_task, targets, req.timeframes, req.limit)
        return {"status": "success", "message": f"Started background download for {len(targets)} pairs", "targets": targets}
    except Exception as e:
        logger.error(f"Download trigger failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_db_status():
    """Returns the amount of records stored in the local SQLite DB."""
    try:
        data_extractor.init_db()
        conn = data_extractor.get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT count(*) FROM eligible_pairs")
        eligible_count = c.fetchone()[0]
        
        c.execute("SELECT count(*) FROM klines")
        kline_count = c.fetchone()[0]
        
        c.execute("SELECT symbol, interval, count(*) as c FROM klines GROUP BY symbol, interval")
        details = [{"symbol": row["symbol"], "interval": row["interval"], "count": row["c"]} for row in c.fetchall()]
        
        conn.close()
        
        return {
            "eligible_pairs": eligible_count,
            "total_klines": kline_count,
            "details": details
        }
    except Exception as e:
        return {"error": str(e), "eligible_pairs": 0, "total_klines": 0}

@router.get("/eligible")
async def get_eligible():
    """Returns the list of pairs with >= 50x leverage not in blocklist."""
    try:
        data_extractor.init_db()
        pairs = data_extractor.get_eligible_pairs()
        return [{"symbol": p[0], "max_leverage": p[1]} for p in pairs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class BacktestRunRequest(BaseModel):
    symbol: str
    timeframes: List[str]
    initial_balance: float = 100.0
    strategy_toggles: dict = {
        "lateral_guillotine": True,
        "sentinel": False
    }

@router.post("/run")
async def run_backtest(req: BacktestRunRequest):
    """Run a simulated backtest using local DB klines"""
    try:
        # Pega a primeira timeframe da lista (V1.0)
        interval = req.timeframes[0] if req.timeframes else "1h"
        
        # [AUTO-DOWNLOAD OKX] Se o banco de dados tem menos de 50 klines para o par/intervalo,
        # fazemos o download na hora a partir da OKX Mainnet pública de forma síncrona
        try:
            symbol_clean = req.symbol.replace('.P', '').replace('.p', '').replace('-SWAP', '').replace('-', '').upper()
            data_extractor.init_db()
            conn = data_extractor.get_db_connection()
            c = conn.cursor()
            c.execute("SELECT count(*) FROM klines WHERE symbol = ? AND interval = ?", (symbol_clean, interval))
            count = c.fetchone()[0]
            conn.close()
            
            if count < 50:
                logger.info(f"Dados insuficientes no banco SQLite ({count} klines) para {symbol_clean} ({interval}). Baixando na hora da OKX...")
                data_extractor.download_klines(symbol_clean, interval, limit=100)
        except Exception as ex:
            logger.error(f"Falha ao executar auto-download de klines para {req.symbol}: {ex}")

        results = backtest_engine.simulate(
            symbol=req.symbol,
            interval=interval,
            initial_balance=req.initial_balance,
            toggles=req.strategy_toggles
        )
        
        if "error" in results:
            raise HTTPException(status_code=400, detail=results["error"])
            
        return {
            "status": "success",
            "message": f"Backtest completo para {req.symbol} ({interval})",
            "results": results
        }
    except Exception as e:
        logger.error(f"Backtest run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/rankings")
async def get_librarian_rankings():
    """Returns the latest rankings from the Librarian Agent."""
    # V110.33.0: Se o ranking final estiver vazio, retorna o progresso 'ao vivo'
    rankings = librarian_agent.rankings
    if not rankings and librarian_agent.live_rankings:
        rankings = sorted(librarian_agent.live_rankings.values(), key=lambda x: x.get('win_rate', 0), reverse=True)

    return {
        "status": "success",
        "rankings": rankings,
        "sector_analysis": librarian_agent.sector_insights,
        "last_study": librarian_agent.last_study_time
    }
