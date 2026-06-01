import os
import logging
import httpx
import asyncio
import time
from typing import Optional

logger = logging.getLogger("TelegramService")

class TelegramService:
    def __init__(self):
        # Carrega variáveis do ambiente diretamente (suporte a Railway)
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        self.last_update_id = 0
        self.is_active = bool(self.bot_token and self.chat_id)

    async def send_message(self, text: str, parse_mode: str = "HTML"):
        """Envia mensagem para o Telegram (se ativo) E para o Dashboard (Sovereign-WS)."""
        
        # 1. Envio interno para o Chat do Dashboard (WebSocket Hermes Channel)
        try:
            from services.websocket_service import websocket_service
            # Usando asyncio.create_task para não bloquear
            asyncio.create_task(websocket_service.emit_hermes_notification(
                title="Hermes Monitor",
                message=text,
                severity="INFO"
            ))
        except Exception as e:
            logger.error(f"Erro ao emitir para o WebSocket: {e}")

        # 2. Envio Externo via Telegram
        if not self.is_active:
            logger.debug("Telegram ignorado (TELEGRAM_BOT_TOKEN ou CHAT_ID não configurados). Dashboard notificado.")
            return

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)
                if response.status_code != 200:
                    logger.error(f"Erro na API do Telegram: {response.text}")
        except Exception as e:
            logger.error(f"Falha de conexão com Telegram: {e}")

    async def _handle_banca_command(self):
        """Skill /banca: Calcula e devolve o extrato consolidado do sistema."""
        try:
            from services.database_service import database_service
            banca = await database_service.get_banca_status()
            slots = await database_service.get_active_slots()
            moonbags = await database_service.get_moonbags()
            
            saldo = banca.get("saldo_total", 0.0)
            
            # Cabeçalho
            msg = "🏦 <b>EXTRATO DO GUARDIÃO (HERMES)</b>\n\n"
            msg += f"<b>💰 Saldo Atual:</b> ${saldo:.2f}\n"
            
            # Resumo de Slots
            ativas = [s for s in slots if s.get("status_risco") != "LIVRE" and s.get("symbol")]
            msg += f"\n<b>⚡ Slots em Batalha:</b> {len(ativas)}/4\n"
            for s in ativas:
                pnl = s.get('pnl_percent', 0.0)
                emoji = "🟢" if pnl >= 0 else "🔴"
                msg += f"  {emoji} {s.get('symbol')} | PnL: {pnl:.2f}%\n"
                
            # Resumo de Moonbags
            msg += f"\n<b>🚀 Moonbags (Emancipadas):</b> {len(moonbags)}\n"
            for m in moonbags[:5]: # Mostra apenas as 5 mais recentes
                pnl = m.get('pnl_percent', 0.0)
                emoji = "🛡️" if pnl >= 0 else "🩸"
                msg += f"  {emoji} {m.get('symbol')} | Lucro Livre: {pnl:.2f}%\n"
                
            msg += "\n👁️ <i>Sigo na vigia. A banca está protegida!</i>"
            
            await self.send_message(msg)
        except Exception as e:
            logger.error(f"Erro ao processar Skill /banca: {e}")
            await self.send_message("❌ Erro interno ao buscar dados da banca.")

    async def _poll_updates(self):
        """Loop contínuo de Long-Polling para receber comandos e mensagens do Telegram."""
        if not self.base_url: return
        url = f"{self.base_url}/getUpdates"
        
        while True:
            try:
                params = {"offset": self.last_update_id + 1, "timeout": 30}
                async with httpx.AsyncClient() as client:
                    response = await client.get(url, params=params, timeout=35.0)
                    if response.status_code == 200:
                        data = response.json()
                        for result in data.get("result", []):
                            self.last_update_id = result["update_id"]
                            message = result.get("message", {})
                            text = message.get("text", "")
                            
                            if text:
                                if text.startswith("/banca"):
                                    logger.info("Skill /banca requisitada pelo Telegram!")
                                    asyncio.create_task(self._handle_banca_command())
                                elif text.startswith("/"):
                                    await self.send_message("⚠️ Comando não reconhecido. Use `/banca` ou converse normalmente comigo!")
                                else:
                                    logger.info(f"📨 Mensagem recebida no Telegram: '{text}' - Processando...")
                                    asyncio.create_task(self._handle_telegram_chat(text))
            except httpx.ReadTimeout:
                pass # Timeout normal do long-polling
            except Exception as e:
                logger.debug(f"Telegram polling ignorável: {e}")
            
            await asyncio.sleep(2)

    async def _handle_telegram_chat(self, user_message: str):
        """Processa mensagens comuns usando a inteligência integrada do HermesAgent."""
        try:
            from services.agents.hermes_agent import hermes_agent
            result = await hermes_agent.handle_chat_query(user_message)
            reply = result.get("response", "🌐 Sinal neural instável... Tente novamente, Almirante.")
            await self.send_message(reply)
        except Exception as e:
            logger.error(f"❌ Erro no chat do Telegram com HermesAgent: {e}")
            # Fallback direto caso o hermes_agent falhe por algum motivo
            try:
                from services.agents.ai_service import ai_service
                reply = await ai_service.generate_content(
                    prompt=user_message,
                    system_instruction=(
                        "Você é o HERMES — assistente de compliance e oficial de comando da frota do Sistema 1CRYPTEN.\n"
                        "Sua missão é responder ao Almirante Jonatas sobre a banca, slots, e integridade do sistema.\n"
                        "Responda em português do Brasil de forma extremamente concisa, técnica e direta."
                    )
                )
                await self.send_message(reply or "🌐 Sinal neural instável.")
            except Exception as e2:
                logger.error(f"❌ Fallback crítico do Telegram falhou: {e2}")
                await self.send_message("❌ Ocorreu um erro interno de transmissão neural.")

    def start_polling_task(self):
        """Ativa a escuta de comandos no Telegram de forma assíncrona."""
        if not self.is_active:
            logger.warning("⚠️ Telegram Service não está ativo. Ignorando início do Polling.")
            return
        
        logger.info("🤖 Telegram Polling INICIADO de forma inteligente pelo Hermes Guardian.")
        asyncio.create_task(self._poll_updates())

telegram_service = TelegramService()
