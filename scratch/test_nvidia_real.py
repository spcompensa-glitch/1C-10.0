import os
import asyncio
import httpx

async def test_real_nvidia():
    api_key = "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"
    
    # Try integrate.api.nvidia.com (Standard NVIDIA API endpoint)
    endpoints = [
        "https://integrate.api.nvidia.com/v1",
        "https://api.nvidia.com/v1"
    ]
    
    # Nemotron-4b-chat or Llama3 models
    models = [
        "meta/llama3-70b-instruct",
        "nvidia/nemotron-4b-chat",
        "meta/llama-3.1-8b-instruct"
    ]
    
    for base_url in endpoints:
        for model in models:
            print(f"\n🧪 Trying {base_url} with model {model}...")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello! Confirm if you are working."}
                ],
                "temperature": 0.5,
                "max_tokens": 100,
                "stream": False
            }
            
            try:
                async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
                    response = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
                    print(f"Status Code: {response.status_code}")
                    if response.status_code == 200:
                        result = response.json()
                        print(f"🎉 SUCCESS! Response:\n{result['choices'][0]['message']['content']}")
                        return
                    else:
                        print(f"Error: {response.text}")
            except Exception as e:
                print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_real_nvidia())
