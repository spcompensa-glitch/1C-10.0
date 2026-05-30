import httpx
import json

try:
    resp = httpx.get('https://1crypten.space/api/slots', timeout=10.0)
    data = resp.json()
    print("STATUS CODE:", resp.status_code)
    print("SLOTS RETORNADOS:")
    for slot in data:
        print(f"Slot {slot.get('id')}: {slot.get('symbol')} | {slot.get('side')} | Qty: {slot.get('qty')} | Entry: {slot.get('entry_price')} | Risco: {slot.get('status_risco')}")
except Exception as e:
    print("ERRO:", e)
