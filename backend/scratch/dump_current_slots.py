import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean, select
from datetime import datetime
from dotenv import load_dotenv

# Load .env do diretório correto
load_dotenv("c:\\Users\\spcom\\Desktop\\1C-7.0\\backend\\.env", override=True)

Base = declarative_base()

class Slot(Base):
    __tablename__ = "slots"
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    side = Column(String)
    qty = Column(Float)
    entry_price = Column(Float)
    status_risco = Column(String)
    slot_type = Column(String)
    order_id = Column(String)

class BancaStatus(Base):
    __tablename__ = "banca_status"
    id = Column(Integer, primary_key=True)
    saldo_total = Column(Float)
    slots_disponiveis = Column(Integer)
    status = Column(String)

async def dump_postgres_slots():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found in .env")
        return

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    print(f"Connecting to: {db_url}")
    engine = create_async_engine(db_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        print("--- DATABASE SLOTS (POSTGRES) ---")
        result = await session.execute(select(Slot).order_by(Slot.id))
        slots = result.scalars().all()
        for s in slots:
            print(f"Slot {s.id}: Symbol: {s.symbol} | Side: {s.side} | Qty: {s.qty} | EntryPrice: {s.entry_price} | SlotType: {s.slot_type} | StatusRisco: {s.status_risco} | Order: {s.order_id}")
            
        print("\n--- BANCA STATUS ---")
        result = await session.execute(select(BancaStatus).where(BancaStatus.id == 1))
        banca = result.scalar_one_or_none()
        if banca:
            print(f"Saldo: {banca.saldo_total} | Slots Disp: {banca.slots_disponiveis} | Status: {banca.status}")
        else:
            print("No banca status found.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(dump_postgres_slots())
