# -*- coding: utf-8 -*-
import asyncio
import logging
import time
import json
import sys
import os
from typing import List, Dict, Any, Optional

# Importação condicional do paho-mqtt
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    mqtt = None

import grpc
from config import settings

# Adiciona o diretório backend e services ao sys.path para garantir a correta importação de gRPC stubs
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if current_dir not in sys.path:
    sys.path.append(current_dir)
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HermesBroker")

# Tentativa de carregar stubs gRPC compilados com fallback dinâmico
GRPC_STUBS_AVAILABLE = False
try:
    # Tenta import relativo ou absoluto do diretório services
    import services.hermes_pb2 as hermes_pb2
    import services.hermes_pb2_grpc as hermes_pb2_grpc
    GRPC_STUBS_AVAILABLE = True
except Exception as e_grpc:
    try:
        import hermes_pb2 as hermes_pb2
        import hermes_pb2_grpc as hermes_pb2_grpc
        GRPC_STUBS_AVAILABLE = True
    except Exception as e_grpc_inner:
        logger.warning(
            f"⚠️ [gRPC] Falha ao carregar stubs compilados do Hermes: {e_grpc}. "
            "Execute a compilação do arquivo protos/hermes.proto. Usando Mocks em runtime."
        )

class HermesBrokerService:
    def __init__(self):
        # --- Configurações de MQTT ---
        self.mqtt_broker = settings.MQTT_BROKER_URL
        self.mqtt_port = settings.MQTT_BROKER_PORT
        self.mqtt_user = settings.MQTT_USERNAME
        self.mqtt_password = settings.MQTT_PASSWORD
        self.topic_prefix = settings.MQTT_TOPIC_PREFIX
        self.mqtt_client = None
        self.is_mqtt_connected = False
        
        # Verificação de disponibilidade do MQTT
        if not MQTT_AVAILABLE:
            logger.warning("⚠️ [MQTT] Módulo paho-mqtt não disponível - MQTT desativado")
            logger.info("💡 [MQTT] Instale com: pip install paho-mqtt")

        # --- Configurações de gRPC ---
        self.grpc_port = settings.GRPC_SERVER_PORT
        self.grpc_server = None
        self.grpc_task = None

        logger.info(f"🛰️ [HERMES] Inicializado. Broker MQTT: {self.mqtt_broker}:{self.mqtt_port} | Porta gRPC: {self.grpc_port}")

    # ==========================================
    # 📡 SEÇÃO MQTT: PUBLICAÇÃO E MENGERIA ULTRA-RÁPIDA
    # ==========================================
    async def start_mqtt(self):
        """Inicializa e conecta o cliente MQTT de forma assíncrona."""
        if not MQTT_AVAILABLE:
            logger.warning("⚠️ [MQTT] MQTT não disponível - pulando conexão")
            return
            
        try:
            # Paho MQTT 2.0+ exige a declaração da versão da API de callback.
            # Verificamos hasattr para compatibilidade com versões antigas (como 1.6.x) no Railway.
            if hasattr(mqtt, "CallbackAPIVersion"):
                self.mqtt_client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2
                )
            else:
                self.mqtt_client = mqtt.Client()

            if self.mqtt_user and self.mqtt_password:
                self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_password)

            # Configura callbacks usando a assinatura da API Versão 2
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_disconnect = self._on_mqtt_disconnect

            logger.info(f"🔌 [MQTT] Conectando ao HiveMQ Cloud/Broker público em: {self.mqtt_broker}:{self.mqtt_port}...")

            # Conexão sem bloquear o loop principal (roda em thread secundária)
            self.mqtt_client.connect_async(self.mqtt_broker, self.mqtt_port, keepalive=60)
            self.mqtt_client.loop_start()

            # Pequeno delay para permitir a negociação da conexão inicial
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"❌ [MQTT] Erro crítico ao iniciar cliente MQTT: {e}", exc_info=True)

    def _check_mqtt_availability(self):
        """Verifica se MQTT está disponível e conectado"""
        if not MQTT_AVAILABLE:
            return False
        if not self.mqtt_client or not self.is_mqtt_connected:
            return False
        return True

    def _on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.is_mqtt_connected = True
            logger.info("✅ [MQTT] Conectado ao Broker MQTT com SUCESSO!")
        else:
            self.is_mqtt_connected = False
            logger.error(f"❌ [MQTT] Falha de conexão. Código de retorno: {rc}")

    def _on_mqtt_disconnect(self, client, userdata, flags, rc, properties=None):
        self.is_mqtt_connected = False
        logger.warning(f"⚠️ [MQTT] Desconectado do Broker MQTT. Código: {rc}. Tentando reconectar automaticamente...")

    async def publish_sniper_signal(self, symbol: str, side: str, entry_price: float, cohorts: List[str]):
        """
        Publica um sinal leve de sniper direcionado a Cohorts específicos para
        pulverização anti-slippage instantânea.
        """
        if not self._check_mqtt_availability():
            logger.error("❌ [MQTT] Não foi possível enviar o sinal: Cliente MQTT desconectado ou indisponível.")
            return False

        topic = f"{self.topic_prefix}/sinal"
        payload = {
            "version": "5.5.0",
            "type": "SNIPER_ORDER",
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "cohorts": cohorts,
            "timestamp": time.time()
        }
        
        msg_json = json.dumps(payload)
        res = self.mqtt_client.publish(topic, msg_json, qos=1)
        res.wait_for_publish()
        
        logger.info(f"📡 [MQTT] Sinal Sniper publicado no tópico '{topic}' para Cohorts {cohorts}. Qtd: {symbol}")
        return True

    async def publish_panic_signal(self, positions: List[Dict[str, Any]]):
        """
        Publica um sinal global de pânico PANIC para que todas as contas de usuários (shards)
        encerrem as posições de forma unificada concorrentemente.
        """
        if not self._check_mqtt_availability():
            logger.error("❌ [MQTT] Não foi possível enviar sinal de pânico: Cliente MQTT desconectado ou indisponível.")
            return False

        topic = f"{self.topic_prefix}/panic"
        payload = {
            "version": "5.5.0",
            "type": "PANIC_CLOSE_ALL",
            "timestamp": time.time(),
            "positions_to_close": [{"instId": p.get("instId"), "posSide": p.get("posSide")} for p in positions]
        }
        
        msg_json = json.dumps(payload)
        res = self.mqtt_client.publish(topic, msg_json, qos=2)  # QOS 2 garante a entrega exatamente uma vez
        res.wait_for_publish()
        
        logger.critical(f"🚨 [MQTT] SINAL GLOBAL DE PÂNICO PUBLICADO! Tópico: '{topic}'. Posições a liquidar: {len(positions)}")
        return True

    async def stop_mqtt(self):
        """Desconecta graciosamente o cliente MQTT."""
        if self.mqtt_client:
            logger.info("🛑 [MQTT] Desconectando do Broker...")
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.is_mqtt_connected = False
            logger.info("✅ [MQTT] Desconectado.")

    # ==========================================
    # ⚙️ SEÇÃO gRPC: SERVIDOR DE TENANCY E CONTROLE
    # ==========================================
    async def start_grpc(self):
        """Inicia o servidor gRPC assíncrono em segundo plano na porta configurada."""
        self.grpc_task = asyncio.create_task(self._run_grpc_server())
        logger.info("🚀 [gRPC] Servidor agendado para rodar em segundo plano.")

    async def _run_grpc_server(self):
        """Roda o loop principal do servidor gRPC."""
        # Se os stubs foram compilados com sucesso, importamos e subimos o servidor tipado
        if GRPC_STUBS_AVAILABLE:
            class HermesTenancyServicer(hermes_pb2_grpc.HermesTenancyServiceServicer):
                async def ValidateTenantKey(self, request, context):
                    logger.info(f"🔑 [gRPC] Requisição ValidateTenantKey: tenant={request.tenant_id}")
                    # Modo desenvolvimento aceita qualquer chave mockada ou chave ativa
                    is_valid = len(request.api_key) > 5
                    return hermes_pb2.TenantKeyResponse(
                        is_valid=is_valid,
                        error_message="" if is_valid else "Chave de API inválida ou curta demais"
                    )

                async def GetExposureLimits(self, request, context):
                    logger.info(f"📊 [gRPC] Requisição GetExposureLimits: tenant={request.tenant_id}")
                    # Alavancagem máxima de 50x de acordo com a especificação original
                    return hermes_pb2.ExposureLimitsResponse(
                        max_exposure_usd=1000.0,
                        max_leverage=50,
                        allowed_symbol_regex=".*"
                    )

                async def ReportTenantStatus(self, request, context):
                    logger.info(
                        f"📈 [gRPC Telemetry] Tenant={request.tenant_id} | Status={request.status_str} | "
                        f"PnL=${request.current_pnl_usd:.2f} | Margem=${request.current_margin_usd:.2f}"
                    )
                    return hermes_pb2.TenantStatusResponse(
                        acknowledged=True,
                        instruction="CONTINUE"
                    )

            server = grpc.aio.server()
            hermes_pb2_grpc.add_HermesTenancyServiceServicer_to_server(
                HermesTenancyServicer(), server
            )
            listen_addr = f"[::]:{self.grpc_port}"
            server.add_insecure_port(listen_addr)
            logger.info(f"❇️ [gRPC] Servidor gRPC de Tenancy ONLINE em {listen_addr}")
            
            self.grpc_server = server
            await server.start()
            await server.wait_for_termination()
            
        else:
            # Fallback seguro para desenvolvimento se stubs não estiverem gerados.
            # Roda um server TCP simples ou apenas simula para não crashar o sistema
            logger.warning("⚠️ [gRPC] Servidor rodando em MODO MOCK SIMULADO por falta de stubs compilados.")
            while True:
                await asyncio.sleep(3600)  # Mantém a task viva sem consumir CPU

    async def stop_grpc(self):
        """Encerra graciosamente o servidor gRPC."""
        if self.grpc_server:
            logger.info("🛑 [gRPC] Parando servidor gRPC...")
            await self.grpc_server.stop(grace=3.0)
            logger.info("✅ [gRPC] Servidor gRPC desligado.")
        
        if self.grpc_task:
            self.grpc_task.cancel()
            self.grpc_task = None

# Instanciação Singleton
hermes_broker_service = HermesBrokerService()
