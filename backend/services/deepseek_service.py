"""
[HERMES] DeepSeekService — Cliente HTTP para API DeepSeek
Usa SDK OpenAI (compatível) para chamadas à API DeepSeek.
Endpoint: https://api.deepseek.com/v1
Modelo: deepseek-chat (primário) | deepseek-reasoner (fallback analítico)
"""
import logging
import asyncio
import time
from typing import Optional, List, Dict, Any
from config import settings

logger = logging.getLogger("DeepSeekService")

class DeepSeekService:
    def __init__(self):
        self.api_key: Optional[str] = None
        self.base_url = "https://api.deepseek.com/v1"
        self.model = "deepseek-chat"
        self.reasoner_model = "deepseek-reasoner"
        self.client = None
        self.backoff_until = 0
        self.last_request_time = 0
        self.rate_limit_rpm = 60  # DeepSeek free tier ~60 RPM
        self.min_request_interval = 1.0  # 1s between requests
        self._initialized = False

    def initialize(self):
        """Initialize the DeepSeek client with API key from settings."""
        raw_key = settings.DEEPSEEK_API_KEY
        if raw_key:
            self.api_key = raw_key.strip()
            logger.info("✅ DeepSeekService: API Key loaded.")
        else:
            logger.warning("⚠️ DeepSeekService: No DEEPSEEK_API_KEY in config.")
            return False

        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            self._initialized = True
            logger.info(f"✅ DeepSeekService: Client initialized (model={self.model})")
            return True
        except ImportError:
            logger.error("❌ DeepSeekService: 'openai' package not installed. Run: pip install openai")
            return False
        except Exception as e:
            logger.error(f"❌ DeepSeekService: Failed to initialize: {e}")
            return False

    async def _rate_limit_wait(self):
        """Ensure we don't exceed rate limits."""
        now = time.time()
        if now < self.backoff_until:
            wait = self.backoff_until - now
            logger.debug(f"⏳ DeepSeekService: Backoff active, waiting {wait:.1f}s")
            await asyncio.sleep(wait)
        
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - elapsed)

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        use_reasoner: bool = False
    ) -> Optional[str]:
        """
        Send a chat completion request to DeepSeek API with dynamic AIService fallback.
        
        Args:
            messages: List of message dicts [{"role": "user", "content": "..."}]
            system_instruction: Optional system prompt
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
            use_reasoner: Use deepseek-reasoner for analytical tasks
        
        Returns:
            Response text or None on failure
        """
        if not self._initialized:
            if not self.initialize():
                # Fallback se não inicializado (chave ausente no .env)
                logger.info("⚠️ DeepSeekService not initialized. Attempting fallback to AIService...")
                try:
                    from services.agents.ai_service import ai_service
                    prompt_content = "\n".join([f"{msg.get('role')}: {msg.get('content', '')}" for msg in messages])
                    response_text = await ai_service.generate_content(
                        prompt=prompt_content,
                        system_instruction=system_instruction or "Você é o HERMES."
                    )
                    if response_text:
                        logger.info("✅ DeepSeekService: Fallback to AIService successful!")
                        return response_text
                except Exception as fe:
                    logger.error(f"❌ DeepSeekService fallback failed: {fe}")
                return None

        await self._rate_limit_wait()

        full_messages = []
        if system_instruction:
            full_messages.append({"role": "system", "content": system_instruction})
        full_messages.extend(messages)

        model = self.reasoner_model if use_reasoner else self.model

        try:
            self.last_request_time = time.time()
            
            # Use asyncio.to_thread to avoid blocking
            def _sync_call():
                return self.client.chat.completions.create(
                    model=model,
                    messages=full_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

            response = await asyncio.wait_for(
                asyncio.to_thread(_sync_call),
                timeout=30.0
            )

            if response and response.choices:
                content = response.choices[0].message.content
                if content:
                    logger.info(f"✅ DeepSeek Success ({model}): {len(content)} chars")
                    return content.strip()

            logger.warning(f"⚠️ DeepSeek: Empty response from {model}")
            return None

        except asyncio.TimeoutError:
            logger.error(f"❌ DeepSeek: Timeout after 30s ({model})")
            return None
        except Exception as e:
            err_str = str(e).lower()
            if "rate" in err_str or "429" in err_str:
                self.backoff_until = time.time() + 30
                logger.warning(f"⏳ DeepSeek: Rate limited. Backoff 30s.")
            elif "quota" in err_str or "insufficient" in err_str:
                self.backoff_until = time.time() + 300
                logger.warning(f"⏳ DeepSeek: Quota exceeded. Backoff 5min.")
            else:
                logger.error(f"❌ DeepSeek API error: {e}")
                
            # Fallback inteligente se a chamada der erro
            logger.info("⚠️ DeepSeekService: API call failed. Attempting fallback to AIService...")
            try:
                from services.agents.ai_service import ai_service
                prompt_content = "\n".join([f"{msg.get('role')}: {msg.get('content', '')}" for msg in messages])
                response_text = await ai_service.generate_content(
                    prompt=prompt_content,
                    system_instruction=system_instruction or "Você é o HERMES."
                )
                if response_text:
                    logger.info("✅ DeepSeekService: Fallback to AIService successful!")
                    return response_text
            except Exception as fe:
                logger.error(f"❌ DeepSeekService fallback failed: {fe}")
                
            return None

    async def analyze_compliance(
        self,
        docs_content: str,
        code_constants: str,
        runtime_data: str
    ) -> Dict[str, Any]:
        """
        [HERMES COMPLIANCE] Analisa divergência entre docs, código e runtime.
        Usa deepseek-reasoner para análise profunda.
        """
        system_prompt = (
            "Você é o HERMES, Agente de Compliance do Sistema 10D Sniper Factory. "
            "Sua função é comparar três fontes de verdade e detectar divergências:\n"
            "1. 📄 DOCS (Expected Behavior): O que DEVERIA acontecer\n"
            "2. 💻 CÓDIGO (Actual Code): O que FOI programado\n"
            "3. ⚡ RUNTIME (Real Execution): O que REALMENTE está acontecendo\n\n"
            "Retorne APENAS um JSON puro (sem markdown) no formato:\n"
            '{"divergencias": [{"area": "Escadinha", "expected": "...", "actual": "...", "severity": "CRITICAL|HIGH|MEDIUM|LOW", "impact": "..."}], "conformidades": [...], "resumo": "..."}'
        )

        user_prompt = (
            f"📄 DOCS (Expected Behavior):\n{docs_content}\n\n"
            f"💻 CÓDIGO (Actual Code Constants):\n{code_constants}\n\n"
            f"⚡ RUNTIME (Current State):\n{runtime_data}\n\n"
            "Analise comparativamente e identifique TODAS as divergências."
        )

        result = await self.chat_completion(
            messages=[{"role": "user", "content": user_prompt}],
            system_instruction=system_prompt,
            temperature=0.1,
            use_reasoner=True,
            max_tokens=4096
        )

        if not result:
            return {"divergencias": [], "conformidades": [], "resumo": "Falha na análise de compliance"}

        try:
            import json
            clean = result.replace('```json', '').replace('```', '').strip()
            return json.loads(clean)
        except Exception as e:
            logger.error(f"❌ Hermes Compliance: Failed to parse response: {e}")
            return {"divergencias": [], "conformidades": [], "resumo": result[:500]}

    async def generate_chat_response(
        self,
        user_message: str,
        active_dimensions: List[str],
        wiki_context: Optional[str] = None,
        compliance_context: Optional[str] = None
    ) -> str:
        """
        [HERMES CHAT] Gera resposta contextualizada para o chat do cockpit.
        Combina:
        - Detecção de dimensões (JarvisBrain)
        - Contexto do Segundo Cérebro (Intel Wiki)
        - Alertas de compliance (se houver)
        """
        # System prompt HERMES forte — mesma identidade do chat.py
        system_parts = [
            "VOCÊ É O HERMES — Inteligência Central da Frota 1CRYPTEN (10D Sniper Factory V4.0).\n",
            "Você NÃO é Jarvis. Você é HERMES. Tem acesso a TODOS os agentes, serviços, protocolos e códigos do sistema.\n",
            "\n",
            "## 🎯 MISSÃO PRIMÁRIA (NUNCA ESQUEÇA)\n",
            "O SISTEMA EXISTE PARA GERAR LUCRO NOS 4 SLOTS E FAZER A BANCA CRESCER SEMPRE.\n",
            "- Os 4 SlotOperatorAgents são o CORAÇÃO DO SISTEMA — eles executam ordens e geram ROI\n",
            "- A Escadinha protege cada centavo de lucro\n",
            "- Tudo no sistema existe para dar suporte a isso\n",
            "- A família (Fabiana, Pedro Kalel, Lívia) é o MOTIVO\n",
            "\n",
        ]

        if active_dimensions:
            system_parts.append(f"Dimensões ativas: {', '.join(active_dimensions)}\n")

        if wiki_context:
            system_parts.append(f"\n📖 Contexto do Segundo Cérebro:\n{wiki_context[:2000]}\n")

        if compliance_context:
            system_parts.append(f"\n🛡️ Alerta de Compliance Ativo:\n{compliance_context[:1000]}\n")

        system_parts.append(
            "\n## 📋 REGRAS DE RESPOSTA:\n"
            "- Se apresente como HERMES na primeira frase\n"
            "- Seja DIRETO e TÉCNICO — oficial de comando\n"
            "- Conecte TUDO ao lucro dos slots e crescimento da banca\n"
            "- Se houver compliance alerta, destaque no início\n"
            "- Máximo 400 palavras\n"
            "- Português natural e claro"
        )

        result = await self.chat_completion(
            messages=[{"role": "user", "content": user_message}],
            system_instruction="".join(system_parts),
            temperature=0.7,
            max_tokens=2048,
            use_reasoner=False
        )

        return result or "🌐 Sinal neural instável. Tente novamente, Almirante."

    async def health_check(self) -> dict:
        """Check if the service is operational."""
        if not self._initialized:
            return {"status": "UNINITIALIZED", "message": "DeepSeek não inicializado"}
        
        try:
            result = await self.chat_completion(
                messages=[{"role": "user", "content": "Responda apenas: OK"}],
                temperature=0.1,
                max_tokens=10
            )
            if result:
                return {"status": "ONLINE", "model": self.model, "latency": "ok"}
            return {"status": "DEGRADED", "message": "Resposta vazia"}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

# Singleton
deepseek_service = DeepSeekService()
