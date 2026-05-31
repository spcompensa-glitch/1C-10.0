import httpx
import json

def test_server():
    base_url = "http://localhost:8085/api"
    print("Connecting to local 1Crypten server...")
    
    # 1. Test Health Status
    try:
        resp = httpx.get(f"{base_url}/health", timeout=15.0)
        print(f"Health Response (Code {resp.status_code}):")
        print(json.dumps(resp.json(), indent=2))
    except Exception as e:
        print(f"Failed to get health: {e}")
        
    # 2. Test connectivity
    try:
        resp = httpx.get(f"{base_url}/test", timeout=15.0)
        print(f"\nTest Response (Code {resp.status_code}):")
        print(json.dumps(resp.json(), indent=2))
    except Exception as e:
        print(f"Failed to get test connectivity: {e}")

if __name__ == "__main__":
    test_server()
