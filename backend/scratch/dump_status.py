import asyncio
import sys
import os

backend_dir = r"c:\Users\spcom\Desktop\10D REAL 5.0\1CRYPTEN_SPACE_V4.0\backend"
sys.path.append(backend_dir)

async def check():
    from services.database_service import database_service
    from services.okx_rest import okx_rest_service
    
    slots = await database_service.get_active_slots()
    output = "--- SLOTS STATUS ---\n"
    for s in slots:
        output += f"Slot {s.id}: {s.symbol} | {s.status_risco}\n"
    
    output += "\n--- PAPER POSITIONS ---\n"
    for p in okx_rest_service.paper_positions:
        output += f"Paper: {p.get('symbol')}\n"
        
    with open("scratch/status_report.txt", "w") as f:
        f.write(output)

if __name__ == "__main__":
    asyncio.run(check())
