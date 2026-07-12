"""
[Hermes] NVIDIAService — Cliente HTTP para API NVIDIA
Serviço de IA para o Hermes Guardian usando NVIDIA AI.
Endpoint: https://api.nvidia.com/v1
Modelo: meta/llama3-70b-instruct
Author: DevOps Team
Version: 1.0
"""

import logging
import asyncio
import time
import httpx
from typing import Optional, List, Dict, Any
from config import settings

logger = logging.getLogger("NVIDIAService")

class NVIDIAService:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.base_url = "https://api.nvidia.com/v1"
        self.model = "nvidia/nemotron-4b-chat"
        self.client = None
        self.backoff_until = 0
        self.last_request_time = 0
        self.rate_limit_rpm = 60  # NVIDIA API rate limit
        self.min_request_interval = 1.0  # 1s between requests
        self._initialized = False

    def initialize(self):
        """Initialize the NVIDIA client with API key from settings."""
        raw_key = settings.NVAPI_KEY
        if raw_key:
            self.api_key = raw_key.strip()
            logger.info("✅ NVIDIAService: NVIDIA API Key loaded.")
        else:
            logger.warning("⚠️ NVIDIAService: No NVAPI_KEY in config.")
            return False

        try:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=30.0,
                verify=False  # Desativar verificação SSL para testes
            )
            self._initialized = True
            logger.info(f"✅ NVIDIAService: Client initialized (model={self.model})")
            return True
        except Exception as e:
            logger.error(f"❌ NVIDIAService: Failed to initialize: {e}")
            return False

    async def _rate_limit_wait(self):
        """Rate limiting for NVIDIA API calls"""
        now = time.time()
        if self.backoff_until > now:
            sleep_time = self.backoff_until - now
            logger.info(f"⏸️ NVIDIAService: Rate limiting, waiting {sleep_time:.1f}s")
            await asyncio.sleep(sleep_time)
        
        # Ensure minimum request interval
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - elapsed)
        
        self.last_request_time = time.time()

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        use_reasoning: bool = False
    ) -> Optional[str]:
        """
        Generate response using NVIDIA AI API with dynamic AIService fallback.
        
        Args:
            messages: Conversation messages
            system_instruction: System prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
            use_reasoning: Use reasoning model (not available in NVIDIA)

        Returns:
            Response text or None on failure
        """
        # 1. Tentar chamar a API real da NVIDIA se inicializada
        if self._initialized or self.initialize():
            await self._rate_limit_wait()
            
            full_messages = []
            if system_instruction:
                full_messages.append({"role": "system", "content": system_instruction})
            full_messages.extend(messages)

            try:
                # Make the request directly with asyncio
                response = await self.client.post(
                    "/chat/completions",
                    json={
                        "model": self.model,
                        "messages": full_messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": False
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    if content:
                        logger.info("✅ NVIDIAService: Success using NVIDIA API")
                        return content
                else:
                    logger.error(f"❌ NVIDIAService: API Error {response.status_code}: {response.text}")
                    
                    # Handle rate limiting
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        self.backoff_until = time.time() + retry_after
                        logger.warning(f"⚠️ NVIDIAService: Rate limited, retrying in {retry_after}s")
                    
            except Exception as e:
                logger.error(f"❌ NVIDIAService: Request failed: {e}")

        # 2. FALLBACK 1: Tentar a cascata inteligente do AIService (Gemini/OpenRouter)
        logger.info("⚠️ NVIDIAService: Attempting smart fallback to AIService...")
        try:
            from services.agents.ai_service import ai_service
            # Concatena as mensagens anteriores para criar um prompt contextualizado
            prompt_parts = []
            for msg in messages:
                role = "Almirante" if msg.get("role") == "user" else "Hermes"
                prompt_parts.append(f"{role}: {msg.get('content', '')}")
            prompt_content = "\n".join(prompt_parts)
            
            response_text = await ai_service.generate_content(
                prompt=prompt_content,
                system_instruction=system_instruction or "Você é o HERMES — assistente de compliance e oficial de comando da frota."
            )
            if response_text:
                logger.info("✅ NVIDIAService: Dynamic fallback to AIService successful!")
                return response_text
        except Exception as fe:
            logger.error(f"❌ NVIDIAService fallback to AIService failed: {fe}")

        # Se ambos falharem, retorna None para permitir a continuação da cascata no hermes_agent
        logger.warning("⚠️ NVIDIAService: AIService fallback also failed. Returning None to continue cascade.")
        return None

    async def chat_completion(
        self,
        user_message: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Optional[str]:
        """
        Simple chat completion interface
        
        Args:
            user_message: User message
            system_instruction: System prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            Response text or None on failure
        """
        messages = [{"role": "user", "content": user_message}]
        return await self.generate_response(
            messages=messages,
            system_instruction=system_instruction,
            temperature=temperature,
            max_tokens=max_tokens
        )

    async def close(self):
        """Close the HTTP client"""
        if self.client:
            await self.client.aclose()
            self._initialized = False
            logger.info("🔌 NVIDIAService: Client closed")

# Global instance for easy access
nvidia_service = NVIDIAService()