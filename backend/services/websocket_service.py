# 1CRYPTEN_SPACE_V4.0 - V110.175 WebSocket Service (Real-time Command Center)
import logging
import json
import asyncio
from typing import List, Dict, Set
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("WebSocketService")

class WebSocketService:
    def __init__(self):
        # Gerencia as conexões ativas do Cockpit
        self.active_connections: Set[WebSocket] = set()
        self._last_slots_snapshot = []  # [V110.999] Cache do último estado de slots
        self._last_moonbags_snapshot = []  # [V110.999] Cache do último estado de moonbags
        self._last_banca_snapshot = {}  # [V110.999] Cache do último estado da banca
        self._last_radar_snapshot = {}  # [V110.999] Cache do último radar pulse

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"🔌 Cockpit Connected. Active sessions: {len(self.active_connections)}")
        # [V110.999] Envia snapshot imediato ao conectar — resolve ordens invisíveis no Observatory
        await self._send_initial_snapshot(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"❌ Cockpit Disconnected. Active sessions: {len(self.active_connections)}")

    async def _send_initial_snapshot(self, websocket: WebSocket):
        """[V110.999] Envia estado atual para um cliente recém-conectado."""
        def json_serial(obj):
            if hasattr(obj, 'isoformat'): return obj.isoformat()
            if isinstance(obj, set): return list(obj)
            return str(obj)
        try:
            # 1. Envia slots ativos
            if self._last_slots_snapshot:
                msg = json.dumps({"type": "live_slots", "data": self._last_slots_snapshot}, default=json_serial)
                await websocket.send_text(msg)
            # 2. Envia último radar pulse
            if self._last_radar_snapshot:
                msg = json.dumps({"type": "radar_pulse", "data": self._last_radar_snapshot}, default=json_serial)
                await websocket.send_text(msg)
            # 3. Envia moonbags ativas
            if self._last_moonbags_snapshot:
                msg = json.dumps({"type": "moonbag_vault", "data": self._last_moonbags_snapshot}, default=json_serial)
                await websocket.send_text(msg)
            # 4. Envia status da banca
            if self._last_banca_snapshot:
                msg = json.dumps({"type": "banca_status", "data": self._last_banca_snapshot}, default=json_serial)
                await websocket.send_text(msg)
            logger.info(f"📦 [WS-SNAPSHOT] Snapshot inicial enviado para novo cliente.")
        except Exception as e:
            logger.warning(f"⚠️ [WS-SNAPSHOT] Falha ao enviar snapshot inicial: {e}")

    async def broadcast(self, message: dict):
        """Envia dados para todos os cockpits conectados."""
        if not self.active_connections:
            return
            
        disconnected = set()
        
        # [V110.151] Robust JSON Serialization (Handles datetime objects)
        def json_serial(obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            if isinstance(obj, set):
                return list(obj)
            return str(obj)

        try:
            msg_str = json.dumps(message, default=json_serial)
        except Exception as e:
            logger.error(f"CRITICAL: Failed to serialize WS message: {e}")
            return
        
        for connection in self.active_connections:
            try:
                await connection.send_text(msg_str)
            except Exception as e:
                logger.warning(f"Failed to send WS message: {e}")
                disconnected.add(connection)
        
        # Cleanup
        for conn in disconnected:
            self.disconnect(conn)

    async def emit_slot_update(self, slot_id: int, data: dict):
        """Envia atualização de um slot específico."""
        # V110.180: Encapsula em 'data' para compatibilidade com o trigger do rtdb.ref('live_slots')
        # Se o frontend espera a lista completa, usaremos emit_slots.
        await self.broadcast({
            "type": "SLOT_UPDATE",
            "data": data
        })

    async def emit_slots(self, slots: list):
        """Envia a lista completa de slots (V110.180)."""
        self._last_slots_snapshot = slots  # [V110.999] Atualiza cache
        await self.broadcast({
            "type": "live_slots",
            "data": slots
        })

    async def emit_moonbags(self, moonbags: list):
        """Envia a lista completa de Moonbags (V110.999)."""
        self._last_moonbags_snapshot = moonbags  # [V110.999] Atualiza cache
        await self.broadcast({
            "type": "moonbag_vault",
            "data": moonbags
        })

    async def emit_radar_pulse(self, signals: list):
        """Envia novos sinais do Radar (V110.180)."""
        await self.broadcast({
            "type": "radar_pulse",
            "data": {
                "signals": signals,
                "updated_at": asyncio.get_event_loop().time()
            }
        })

    async def emit_banca_status(self, data: dict):
        """Envia status da banca."""
        self._last_banca_snapshot = data  # [V110.999] Atualiza cache
        await self.broadcast({
            "type": "banca_status",
            "data": data
        })

    async def update_radar_pulse(self, signals: list, decisions: list, market_context: dict):
        """Envia o pacote completo de inteligência do Radar (V110.180)."""
        payload = {
            "signals": signals,
            "decisions": decisions,
            "market_context": market_context,
            "updated_at": asyncio.get_event_loop().time()
        }
        self._last_radar_snapshot = payload  # [V110.999] Atualiza cache
        await self.broadcast({
            "type": "radar_pulse",
            "data": payload
        })

    async def emit_system_state(self, state: dict):
        """Envia o estado global do sistema (V110.181)."""
        await self.broadcast({
            "type": "system_state",
            "data": state
        })

    async def emit_ai_cascade(self, data: dict):
        """[V4.2.1] Envia o status da cascata de IA para a UI."""
        await self.broadcast({
            "type": "ai_cascade_status",
            "data": data
        })

    # ============================================================
    # [HERMES] Notification & Telemetry Broadcasts
    # ============================================================

    async def emit_hermes_notification(self, title: str, message: str, severity: str = "INFO"):
        """[HERMES] Envia notificação do Hermes Agent para o PWA."""
        await self.broadcast({
            "type": "hermes_notification",
            "data": {
                "title": title,
                "message": message,
                "severity": severity,
                "timestamp": asyncio.get_event_loop().time()
            }
        })

    async def emit_hermes_telemetry(self, telemetry: dict):
        """[HERMES] Envia telemetria consolidada do Hermes."""
        await self.broadcast({
            "type": "hermes_telemetry",
            "data": telemetry
        })

    async def emit_hermes_compliance(self, report: dict):
        """[HERMES] Envia relatório de compliance do Hermes."""
        await self.broadcast({
            "type": "hermes_compliance",
            "data": report
        })

websocket_service = WebSocketService()
