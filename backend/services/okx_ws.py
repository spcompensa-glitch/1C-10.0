# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import time
import hmac
import hashlib
import base64
from typing import List, Dict, Any, Optional, Callable
import websockets
from websockets.exceptions import ConnectionClosed
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OKXWS")

class OKXWebSocket:
    def __init__(self):
        self.api_key = settings.OKX_API_KEY_MASTER
        self.api_secret = settings.OKX_API_SECRET_MASTER
        self.passphrase = settings.OKX_PASSPHRASE_MASTER
        self.testnet = settings.OKX_TESTNET
        
        # Endpoint do WebSocket privado da OKX V5
        # Para Demo Trading (Paper): wss://wspap.okx.com:8443/ws/v5/private
        # Para Live (Mainnet): wss://ws.okx.com:8443/ws/v5/private
        if self.testnet:
            self.endpoint = "wss://wspap.okx.com:8443/ws/v5/private"
        else:
            self.endpoint = "wss://ws.okx.com:8443/ws/v5/private"
            
        self.is_mock = self.api_key == "mock_api_key_master_10d_sniper" or not self.api_key
        
        self.ws = None
        self.is_connected = False
        self.is_reconnecting = False
        self.last_message_time = time.time()
        self.msg_queue = asyncio.Queue()
        
        self._callbacks: List[Callable[[List[Dict[str, Any]]], None]] = []
        
        self._connection_task = None
        self._worker_task = None
        self._ping_task = None
        self._mock_task = None
        
        logger.info(f"🔌 [OKX-WS] Inicializado. Testnet={self.testnet}, Mock={self.is_mock}")

    def register_callback(self, callback: Callable[[List[Dict[str, Any]]], None]):
        """Registra uma função de callback para receber atualizações de posições."""
        self._callbacks.append(callback)
        logger.info("📝 [OKX-WS] Callback registrado para receber dados de posições.")

    def _trigger_callbacks(self, data: List[Dict[str, Any]]):
        """Dispara todas as funções de callback registradas com os dados das posições."""
        for callback in self._callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"❌ [OKX-WS] Erro ao executar callback: {e}", exc_info=True)

    def _generate_signature(self, timestamp: str) -> str:
        """Gera a assinatura de autenticação para o login do WebSocket da OKX V5."""
        if not self.api_secret:
            return ""
        message = timestamp + "GET" + "/users/self/verify"
        mac = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode("utf-8")

    async def start(self):
        """Inicia a conexão com o WebSocket privado da OKX."""
        if self.is_mock:
            # Em modo simulado (mock), subimos o loop gerador de posições fictícias
            if not self._mock_task:
                self._mock_task = asyncio.create_task(self._run_mock_simulator())
                logger.info("✨ [OKX-WS] Simulador de WebSocket OKX iniciado.")
            return

        self._connection_task = asyncio.create_task(self._connect_loop())
        self._worker_task = asyncio.create_task(self._process_queue_loop())
        logger.info("🚀 [OKX-WS] Loops de conexão e processamento iniciados.")

    async def stop(self):
        """Encerra graciosamente todas as conexões e loops."""
        logger.info("🛑 [OKX-WS] Parando WebSocket...")
        
        if self._mock_task:
            self._mock_task.cancel()
            self._mock_task = None
            
        if self._connection_task:
            self._connection_task.cancel()
            self._connection_task = None
            
        if self._worker_task:
            self._worker_task.cancel()
            self._worker_task = None
            
        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None

        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
            self.ws = None
            
        self.is_connected = False
        logger.info("✅ [OKX-WS] WebSocket parado.")

    async def _connect_loop(self):
        """Loop resiliente que gerencia a conexão, autenticação e watchdog."""
        while True:
            try:
                logger.info(f"🔗 [OKX-WS] Conectando ao endpoint: {self.endpoint}")
                async with websockets.connect(self.endpoint, ping_interval=None) as ws:
                    self.ws = ws
                    self.is_connected = True
                    self.last_message_time = time.time()
                    
                    # 1. Login no WebSocket Privado
                    logged_in = await self._login()
                    if not logged_in:
                        logger.error("❌ [OKX-WS] Falha no login da conta Master. Tentando reconectar...")
                        await asyncio.sleep(5)
                        continue
                        
                    # 2. Subscrever canal de Posições
                    subbed = await self._subscribe_positions()
                    if not subbed:
                        logger.error("❌ [OKX-WS] Falha ao subscrever canal de posições. Tentando reconectar...")
                        await asyncio.sleep(5)
                        continue

                    # Inicia o ping em segundo plano
                    if self._ping_task:
                        self._ping_task.cancel()
                    self._ping_task = asyncio.create_task(self._ping_loop())
                    
                    # 3. Leitura contínua de mensagens
                    while True:
                        try:
                            msg_str = await asyncio.wait_for(ws.recv(), timeout=45.0)
                            self.last_message_time = time.time()
                            await self.msg_queue.put(msg_str)
                        except asyncio.TimeoutError:
                            logger.warning("⚠️ [OKX-WS] Watchdog: Nenhuma mensagem recebida em 45s. Enviando ping manual...")
                            await ws.send("ping")
                        except ConnectionClosed:
                            logger.warning("⚠️ [OKX-WS] Conexão fechada pelo servidor remoto.")
                            break
                            
            except Exception as e:
                logger.error(f"❌ [OKX-WS] Erro no loop de conexão: {e}")
                self.is_connected = False
                await asyncio.sleep(5)

    async def _login(self) -> bool:
        """Autentica a conexão WebSocket."""
        timestamp = str(int(time.time()))
        sign = self._generate_signature(timestamp)
        
        login_req = {
            "op": "login",
            "args": [
                {
                    "apiKey": self.api_key,
                    "passphrase": self.passphrase,
                    "timestamp": timestamp,
                    "sign": sign
                }
            ]
        }
        
        logger.info("🔑 [OKX-WS] Enviando payload de login...")
        await self.ws.send(json.dumps(login_req))
        
        try:
            resp_str = await asyncio.wait_for(self.ws.recv(), timeout=10.0)
            resp = json.loads(resp_str)
            if resp.get("event") == "login" and resp.get("code") == "0":
                logger.info("✅ [OKX-WS] Login realizado com SUCESSO na conta Master!")
                return True
            else:
                logger.error(f"❌ [OKX-WS] Falha no login: {resp}")
                return False
        except Exception as e:
            logger.error(f"❌ [OKX-WS] Timeout/Erro ao aguardar resposta de login: {e}")
            return False

    async def _subscribe_positions(self) -> bool:
        """Subscreve o canal privado de posições."""
        sub_req = {
            "op": "subscribe",
            "args": [
                {
                    "channel": "positions",
                    "instType": "ANY"
                }
            ]
        }
        
        logger.info("📡 [OKX-WS] Subscrevendo canal de posições privadas...")
        await self.ws.send(json.dumps(sub_req))
        
        try:
            resp_str = await asyncio.wait_for(self.ws.recv(), timeout=10.0)
            resp = json.loads(resp_str)
            # A OKX retorna um evento de subscrição bem-sucedido
            if resp.get("event") == "subscribe" or (resp.get("arg", {}).get("channel") == "positions"):
                logger.info("✅ [OKX-WS] Subscrição no canal de posições realizada com SUCESSO!")
                return True
            else:
                logger.error(f"❌ [OKX-WS] Falha na subscrição: {resp}")
                return False
        except Exception as e:
            logger.error(f"❌ [OKX-WS] Timeout/Erro ao aguardar resposta de subscrição: {e}")
            return False

    async def _ping_loop(self):
        """Loop para envio periódico de ping e batimento de pulsação (heartbeat)."""
        while self.is_connected and self.ws:
            try:
                await asyncio.sleep(20)
                await self.ws.send("ping")
                logger.debug("💓 [OKX-WS] Ping enviado.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [OKX-WS] Falha ao enviar ping: {e}")
                break

    async def _process_queue_loop(self):
        """Processa as mensagens recebidas na fila assíncrona de forma desacoplada."""
        while True:
            try:
                msg_str = await self.msg_queue.get()
                
                # Trata resposta rápida de pong da OKX
                if msg_str == "pong":
                    logger.debug("💓 [OKX-WS] Pong recebido.")
                    self.msg_queue.task_done()
                    continue
                    
                data = json.loads(msg_str)
                channel = data.get("arg", {}).get("channel")
                
                if channel == "positions" and "data" in data:
                    positions_data = data["data"]
                    # Dispara os callbacks registrados com os dados de posições recebidos
                    self._trigger_callbacks(positions_data)
                    
                self.msg_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [OKX-WS] Erro ao processar mensagem do WebSocket: {e}")
                await asyncio.sleep(0.1)

    async def _run_mock_simulator(self):
        """Simulador de mercado de alta fidelidade para fins de testes locais."""
        logger.info("🤖 [OKX-WS MOCK] Iniciando gerador de feeds simulados de PnL...")
        from services.okx_service import okx_service
        
        while True:
            try:
                await asyncio.sleep(2.0)
                # Puxa as posições mockadas atualizadas do okx_service
                positions = await okx_service.get_positions()
                if positions:
                    # Dispara os callbacks com as posições atualizadas
                    self._trigger_callbacks(positions)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [OKX-WS MOCK] Erro no simulador mock: {e}")
                await asyncio.sleep(5.0)

# Instanciação Singleton
okx_ws_service = OKXWebSocket()
