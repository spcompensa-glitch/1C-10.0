import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../services")))

import asyncio
from services.firebase_service import firebase_service

async def check_firestore_state():
    # Load env vars manually
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))
    
    await firebase_service.initialize()
    if not firebase_service.is_active:
        print("Firebase not active")
        return
        
    doc = await asyncio.to_thread(firebase_service.db.collection("system_state").document("paper_engine").get)
    if doc.exists:
        data = doc.to_dict()
        print("Paper Balance:", data.get("balance"))
        print("\nPositions in Firestore:")
        for p in data.get("positions", []):
            print(p)
        print("\nMoonbags in Firestore:")
        for m in data.get("moonbags", []):
            print(m)
    else:
        print("paper_engine document does not exist")

if __name__ == "__main__":
    asyncio.run(check_firestore_state())
