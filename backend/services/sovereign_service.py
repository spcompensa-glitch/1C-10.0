# sovereign_service.py — ORQUESTRADOR E PONTE DE DADOS
# Ponte inteligente criada para delegar dinamicamente e evitar importações circulares.
# versão: V110.702-bridge

import asyncio
import logging

logger = logging.getLogger("sovereign-service")

class SovereignServiceBridge:
    """Ponte e orquestrador de estado para governança centralizada."""
    
    def __init__(self):
        self._initialized = False
        self._pulse_cache = {"btc_direction": "LATERAL"}
        logger.info("🏛️ SovereignServiceBridge inicializado")
    
    async def initialize(self):
        """Inicialização simulada."""
        logger.info("🏛️ SovereignServiceBridge.initialize() — ativando pontes")
        await asyncio.sleep(0.1)
        self._initialized = True
        logger.info("✅ SovereignServiceBridge pronto para despacho.")
    
    async def update_ai_cascade(self, status: dict):
        """Método chamado pelo ai_service para broadcast de status."""
        logger.debug("🏛️ update_ai_cascade() — broadcast registrado")
    
    async def update_pulse_drag(self, **kwargs):
        """Método para atualizar o pulse do sistema."""
        logger.debug(f"🏛️ update_pulse_drag() — {len(kwargs)} parâmetros atualizados no cache")
        self._pulse_cache.update(kwargs)
    
    async def get_active_slots(self, force_refresh=False):
        """Retorna slots ativos do banco de dados relacional (SSOT)."""
        from services.database_service import database_service
        return await database_service.get_active_slots()
        
    async def get_slot(self, slot_id: int):
        """Busca dados de um slot específico."""
        from services.database_service import database_service
        return await database_service.get_slot(slot_id)
        
    async def update_slot(self, slot_id: int, data: dict):
        """Atualiza dados do slot no banco e propaga para o WebSocket."""
        from services.database_service import database_service
        return await database_service.update_slot(slot_id, data)
        
    async def update_bankroll(self, amount: float):
        """Atualiza banca/saldo total do sistema."""
        from services.database_service import database_service
        return await database_service.update_banca_status({"saldo_total": amount})
        
    async def hard_reset_slot(self, slot_id: int, reason: str = "Tolerancia Zero", pnl: float = 0, trade_data: dict = None):
        """Reseta totalmente um slot no banco, envia para o histórico e limpa a UI."""
        from services.firebase_service import firebase_service
        return await firebase_service.hard_reset_slot(slot_id, reason, pnl, trade_data)
    
    async def free_slot(self, slot_id: int, reason: str = "Promoted to Moonbag"):
        """Libera o slot no Firebase/RTDB."""
        from services.firebase_service import firebase_service
        return await firebase_service.free_slot(slot_id, reason)
        
    async def get_paper_state(self):
        """Retorna o estado do simulador de papel (Paper Mode)."""
        from services.firebase_service import firebase_service
        return await firebase_service.get_paper_state()
        
    async def update_paper_state(self, data: dict):
        """Atualiza o estado do simulador de papel (Paper Mode)."""
        from services.firebase_service import firebase_service
        return await firebase_service.update_paper_state(data)
    
    async def get_conformidades(self):
        """Retorna conformidades simuladas (para Hermes)."""
        return []

# Instância global unificada
sovereign_service = SovereignServiceBridge()

