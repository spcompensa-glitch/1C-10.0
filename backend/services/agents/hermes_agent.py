"""
[HERMES] Hermes Agent V1.0 — Compliance, Telemetria & Chat Orchestrator

3 Pilares:
1. 🧠 COMPLIANCE ENGINE: Compara docs vs código vs runtime e detecta divergências
2. 📊 TELEMETRY ENGINE: Consolida FleetAudit + FlowSentinel + Guardian
3. 💬 CHAT ENGINE: Responde com contexto do Segundo Cérebro + compliance

Integra: DeepSeek (cérebro), JarvisBrain (dimensões), Intel Wiki (contexto)
"""
import logging
import asyncio
import time
import json
import os
from typing import Dict, Any, List, Optional
from config import settings
from services.agents.aios_adapter import AIOSAgent
from services.sovereign_service import sovereign_service

logger = logging.getLogger("HermesAgent")

# --- Docs SSOT (Hardcoded from config.py para acesso rápido) ---
# [V121] RISK_ZERO unificado: trigger=settings.RISK_ZERO_TRIGGER_ROI, stop=settings.RISK_ZERO_STOP_TARGET
ESCADINHA_DOCS_SSOT = {
    "description": "Escadinha (Trailing Stop) — Sincronizado com order_projection_service.py (ORDER_STOP_LADDER) e config.py",
    "phases": [
        {"name": "RISK_ZERO", "trigger_roi": 50.0, "sl_target_roi": 25.0, "desc": "Risk Zero: SL vai para +25% ROI (Fôlego/Taxas)"},
        {"name": "LUCRO_GARANTIDO", "trigger_roi": 100.0, "sl_target_roi": 50.0, "desc": "Garante +50% ROI"},
        {"name": "SUCESSO_TOTAL", "trigger_roi": 130.0, "sl_target_roi": 110.0, "desc": "Garante +110% ROI"},
        {"name": "EMANCIPATION", "trigger_roi": 150.0, "sl_target_roi": 110.0, "desc": "Emancipação: Slot liberado, vira Moonbag"}
    ],
    "stop_loss_rules": {
        "standard_sl_percent": "1.0% a 1.5%",
        "hard_cap_percent": "1.5% para bancas < $100",
        "ignition_sl_percent": "0.8% (Score >= 90)"
    }
}


class HermesAgent(AIOSAgent):
    """
    HERMES — Inteligência Central de Compliance e Orquestração.
    
    Responsabilidades:
    1. Monitorar divergências entre docs, código e runtime
    2. Consolidar telemetria da frota (FleetAudit, FlowSentinel, Guardian)
    3. Orquestrar chat com contexto do Segundo Cérebro
    4. Emitir notificações via WebSocket para o PWA
    """
    
    def __init__(self):
        super().__init__(
            agent_id="agent-hermes",
            role="compliance_orchestrator",
            capabilities=[
                "compliance_audit",
                "telemetry_consolidation",
                "chat_orchestration",
                "notification_broadcast",
                "divergence_detection"
            ]
        )
        self.is_running = False
        self.compliance_interval = 300  # 5 min entre auditorias de compliance
        self.telemetry_interval = 60     # 1 min entre consolidação de telemetria
        self._last_compliance_check = 0
        self._last_telemetry_broadcast = 0
        
        # Cache de divergências encontradas
        self.divergencias: List[Dict] = []
        self.conformidades: List[str] = []
        self.last_compliance_report: Optional[Dict] = None
        
        # Referências carregadas lazy
        self._deepseek = None
        self._jarvis_brain = None
        self._wiki_context_cache = ""
        self._last_wiki_load = 0

    async def _lazy_load_deps(self):
        """Load dependencies lazily to avoid circular imports."""
        try:
            from services.deepseek_service import deepseek_service
            self._deepseek = deepseek_service
        except Exception:
            self._deepseek = None
        
        try:
            from services.agents.jarvis_brain import jarvis_brain
            self._jarvis_brain = jarvis_brain
        except Exception:
            self._jarvis_brain = None
        
        # Initialize DeepSeek
        if self._deepseek and not self._deepseek._initialized:
            try:
                self._deepseek.initialize()
            except Exception:
                pass

    async def _load_wiki_context(self) -> str:
        """Load Intel Wiki content for chat context (cached 5 min)."""
        now = time.time()
        if self._wiki_context_cache and (now - self._last_wiki_load) < 300:
            return self._wiki_context_cache
        
        try:
            # Try to load the intel_wiki.html content
            wiki_paths = [
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "intel_wiki.html"),
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "intel_wiki.html"),
            ]
            for path in wiki_paths:
                abs_path = os.path.abspath(path)
                if os.path.exists(abs_path):
                    with open(abs_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    self._wiki_context_cache = content[:5000]
                    self._last_wiki_load = now
                    logger.info("📚 Hermes: Wiki context loaded")
                    return self._wiki_context_cache
        except Exception as e:
            logger.warning(f"⚠️ Hermes: Failed to load wiki: {e}")
        
        self._wiki_context_cache = "Intel Wiki disponível em /intel/wiki"
        return self._wiki_context_cache

    async def start(self):
        """Start the Hermes Agent monitoring loops."""
        try:
            self.is_running = True
            await self._lazy_load_deps()
            logger.info("🟢 HERMES ONLINE: Compliance & Telemetry Engine ativo.")
            asyncio.create_task(self.run_compliance_loop())
            asyncio.create_task(self.run_telemetry_loop())
        except Exception as e:
            logger.error(f"❌ HERMES start error (running in degraded mode): {e}")
            # Keep is_running True even if deps fail — degraded mode still serves chat
            self.is_running = True

    async def stop(self):
        self.is_running = False
        logger.info("🔴 HERMES OFFLINE.")

    async def on_message(self, message: Any):
        """Handle direct messages from the kernel/dispatcher."""
        if isinstance(message, dict):
            msg_type = message.get("type", "")
            if msg_type == "COMPLIANCE_CHECK":
                return await self.run_compliance_audit()
            elif msg_type == "CHAT_QUERY":
                return await self.handle_chat_query(
                    message.get("text", ""),
                    message.get("context", {})
                )
        return {"status": "ACK", "agent": self.agent_id}

    # ============================================================
    # 🧠 COMPLIANCE ENGINE
    # ============================================================

    async def run_compliance_audit(self) -> Dict[str, Any]:
        """
        [HERMES COMPLIANCE] Auditoria completa:
        1. Compara docs SSOT vs código real (protocol_registry, execution_protocol)
        2. Verifica runtime (slots ativos) contra o esperado
        3. Identifica divergências estruturais
        """
        await self._lazy_load_deps()
        
        try:
            # 1. Load code constants from order_projection_service
            from services.order_projection_service import ORDER_STOP_LADDER_RANGING, ORDER_STOP_LADDER_TRENDING
            
            code_phases = {}
            for ladder in (ORDER_STOP_LADDER_RANGING, ORDER_STOP_LADDER_TRENDING):
                for level in ladder:
                    if level.phase in ("ESCADINHA", "EMANCIPACAO"):
                        code_phases[level.name] = {
                            "trigger_roi": level.trigger_roi,
                            "sl_target_roi": level.stop_roi,
                            "label": level.name.replace("_", " ").title()
                        }
            
            # 2. Get runtime data from sovereign_service
            runtime_slots = []
            try:
                active_slots = await sovereign_service.get_active_slots()
                for s in active_slots:
                    if s.get("symbol"):
                        runtime_slots.append({
                            "symbol": s.get("symbol"),
                            "roi": s.get("pnl_percent", 0),
                            "current_stop": s.get("current_stop"),
                            "phase": s.get("escadinha_phase", "UNKNOWN"),
                            "entry": s.get("entry_price")
                        })
            except Exception:
                runtime_slots = []

            # 3. Compare docs vs code
            divergencias = []
            conformidades = []
            
            doc_phases = {p["name"]: p for p in ESCADINHA_DOCS_SSOT["phases"]}
            
            # Map code names to doc names
            name_mapping = {
                "RISCO_ZERO": "RISK_ZERO",
                "LUCRO_GARANTIDO": "LUCRO_GARANTIDO",
                "SUCESSO_TOTAL": "SUCESSO_TOTAL",
                "EMANCIPADA": "EMANCIPATION"
            }
            
            for phase_name, phase_data in code_phases.items():
                doc_name = name_mapping.get(phase_name, phase_name)
                doc_phase = doc_phases.get(doc_name)
                if not doc_phase:
                    divergencias.append({
                        "area": f"Escadinha - {phase_name}",
                        "expected": "Documentado nos SSOT",
                        "actual": "Presente no código mas NÃO documentado",
                        "severity": "MEDIUM",
                        "impact": "Fase existe no código mas não tem especificação formal"
                    })
                    continue
                
                # Compare trigger ROI
                code_trigger = phase_data.get("trigger_roi")
                doc_trigger = doc_phase.get("trigger_roi")
                if abs((code_trigger or 0) - (doc_trigger or 0)) > 5:
                    divergencias.append({
                        "area": f"Escadinha - {phase_name} (gatilho)",
                        "expected": f"Gatilho em {doc_trigger}% ROI (docs)",
                        "actual": f"Gatilho em {code_trigger}% ROI (código)",
                        "severity": "HIGH",
                        "impact": f"Escadinha vai travar {abs(code_trigger - doc_trigger):.0f}% antes/depois do esperado"
                    })
                else:
                    conformidades.append(f"{phase_name}: gatilho OK (~{doc_trigger}%)")

            # 4. Check runtime divergences
            for slot in runtime_slots:
                roi = slot.get("roi", 0)
                phase = slot.get("phase", "UNKNOWN")
                if phase == "UNKNOWN" and roi > 50:
                    divergencias.append({
                        "area": f"Runtime - {slot['symbol']}",
                        "expected": "Escadinha deveria estar ativa (ROI > 50%)",
                        "actual": f"ROI={roi:.1f}% mas sem fase de Escadinha",
                        "severity": "CRITICAL",
                        "impact": "Lucro não protegido — risco de perda total do gain"
                    })

            self.divergencias = divergencias
            self.conformidades = conformidades
            
            report = {
                "timestamp": time.time(),
                "total_divergencias": len(divergencias),
                "total_conformidades": len(conformidades),
                "divergencias": divergencias,
                "conformidades": conformidades,
                "resumo": self._gerar_resumo(divergencias, conformidades)
            }
            
            self.last_compliance_report = report
            
            # Se houver divergências críticas, emitir notificação
            has_critical = any(d["severity"] == "CRITICAL" for d in divergencias)
            if has_critical:
                await self._emit_notification(
                    "🚨 HERMES: Divergência Crítica Detectada",
                    f"{len(divergencias)} divergência(s) encontrada(s). "
                    f"{sum(1 for d in divergencias if d['severity'] == 'CRITICAL')} crítica(s). "
                    f"Áreas: {', '.join(set(d['area'] for d in divergencias[:3]))}",
                    severity="CRITICAL"
                )
                # Broadcast compliance report via WebSocket
                await self._broadcast_compliance(report)
            
            logger.info(f"✅ HERMES Compliance: {len(divergencias)} divergências, {len(conformidades)} conformidades")
            return report

        except Exception as e:
            logger.error(f"❌ HERMES Compliance Error: {e}")
            return {"error": str(e), "divergencias": [], "conformidades": []}

    def _gerar_resumo(self, divergencias: List[Dict], conformidades: List[str]) -> str:
        """Gera resumo em linguagem natural do estado de compliance."""
        if not divergencias and not conformidades:
            return "Nenhuma auditoria realizada ainda."
        
        parts = []
        if conformidades:
            parts.append(f"✅ {len(conformidades)} conformidades OK")
        if divergencias:
            severities = {}
            for d in divergencias:
                s = d["severity"]
                severities[s] = severities.get(s, 0) + 1
            severity_str = ", ".join(f"{n} {s}" for s, n in sorted(severities.items()))
            parts.append(f"🚨 {len(divergencias)} divergências ({severity_str})")
        
        return " | ".join(parts)

    async def run_compliance_loop(self):
        """Background loop: periodic compliance audit."""
        while self.is_running:
            try:
                await asyncio.sleep(self.compliance_interval)
                await self.run_compliance_audit()
            except Exception as e:
                logger.error(f"❌ Hermes Compliance Loop: {e}")
                await asyncio.sleep(30)

    # ============================================================
    # 📊 TELEMETRY ENGINE
    # ============================================================

    async def run_telemetry_loop(self):
        """Background loop: consolidate and broadcast telemetry."""
        while self.is_running:
            try:
                await asyncio.sleep(self.telemetry_interval)
                await self._consolidate_and_broadcast()
            except Exception as e:
                logger.error(f"❌ Hermes Telemetry Loop: {e}")
                await asyncio.sleep(10)

    async def _consolidate_and_broadcast(self):
        """
        Consolida dados de FleetAudit, FlowSentinel, Guardian e sistema
        e emite payload de telemetria unificado via WebSocket.
        """
        try:
            # Get system state
            system_state = {}
            try:
                system_state = sovereign_service._pulse_cache or {}
            except Exception:
                pass

            # Get active slots
            active_slots = []
            try:
                slots = await sovereign_service.get_active_slots()
                active_slots = [s for s in slots if s.get("symbol")]
            except Exception:
                pass

            telemetry = {
                "type": "hermes_telemetry",
                "data": {
                    "timestamp": time.time(),
                    "system": {
                        "current_state": system_state.get("current", "UNKNOWN"),
                        "radar_mode": system_state.get("radar_mode", "NONE"),
                        "btc_price": system_state.get("btc_price"),
                        "btc_adx": system_state.get("btc_adx"),
                    },
                    "slots": {
                        "total": 4,
                        "active": len(active_slots),
                        "symbols": [s.get("symbol") for s in active_slots],
                        "total_roi": sum(float(s.get("pnl_percent", 0)) for s in active_slots)
                    },
                    "compliance": {
                        "total_divergencias": len(self.divergencias),
                        "has_critical": any(d["severity"] == "CRITICAL" for d in self.divergencias),
                        "last_check": self._last_compliance_check
                    },
                    "hermes_status": "ONLINE" if self.is_running else "OFFLINE"
                }
            }

            from services.websocket_service import websocket_service
            await websocket_service.broadcast(telemetry)
            
            logger.debug(f"📡 Hermes Telemetry broadcast: {len(active_slots)} slots ativos")

        except Exception as e:
            logger.error(f"❌ Hermes Telemetry consolidation error: {e}")

    # ============================================================
    # 💬 CHAT ORCHESTRATOR
    # ============================================================

    async def handle_chat_query(
        self,
        user_message: str,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Orquestra uma resposta de chat completa:
        1. Detecta dimensões (JarvisBrain)
        2. Carrega contexto do Segundo Cérebro
        3. Verifica compliance ativo
        4. Gera resposta via DeepSeek
        """
        await self._lazy_load_deps()
        
        # 1. Detect dimensions
        active_dims = []
        if self._jarvis_brain:
            active_dims = self._jarvis_brain.detect_dimensions(user_message)
        
        # 2. Check if it's a compliance query
        compliance_context = None
        if any(word in user_message.lower() for word in ["compliance", "divergencia", "escadinha", "auditoria", "hermes"]):
            compliance_context = json.dumps(self.divergencias[:5], indent=2) if self.divergencias else "Nenhuma divergência ativa."
        
        # 3. Handle special commands
        if "compliance" in user_message.lower() or "auditar" in user_message.lower():
            report = await self.run_compliance_audit()
            return {
                "response": self._format_compliance_report(report),
                "context": {"type": "compliance_report", "active_dimensions": active_dims}
            }
        
        if "telemetria" in user_message.lower() or "status sistema" in user_message.lower():
            return {
                "response": await self._generate_system_status(),
                "context": {"type": "system_status", "active_dimensions": active_dims}
            }
            
        # [N8N HYBRID] Comandos para o Servidor MCP n8n
        if "n8n listar" in user_message.lower() or "fluxos n8n" in user_message.lower() or "ferramentas n8n" in user_message.lower():
            from services.n8n_client import n8n_client
            try:
                tools = await n8n_client.list_tools()
                return {
                    "response": f"🤖 **Fluxos (Tools) do n8n Encontrados:**\n```json\n{json.dumps(tools, indent=2)}\n```\n*Diga 'n8n rodar [nome_do_fluxo]' para executar.*",
                    "context": {"type": "n8n_tools", "active_dimensions": active_dims}
                }
            except Exception as e:
                return {"response": f"❌ Falha ao contactar o n8n: {e}", "context": {"active_dimensions": active_dims}}

        if "n8n rodar" in user_message.lower() or "n8n executar" in user_message.lower():
            from services.n8n_client import n8n_client
            # Extrai o nome do fluxo após a palavra-chave
            trigger_word = "rodar" if "rodar" in user_message.lower() else "executar"
            parts = user_message.lower().split(trigger_word, 1)
            workflow_name = parts[1].strip() if len(parts) > 1 else ""
            
            if not workflow_name:
                return {"response": "⚠️ Você precisa informar o nome do fluxo. Ex: `n8n rodar meu_fluxo`", "context": {}}
                
            try:
                res = await n8n_client.call_tool(workflow_name)
                return {
                    "response": f"✅ **Fluxo disparado no n8n:**\n```json\n{json.dumps(res, indent=2)}\n```",
                    "context": {"type": "n8n_execution", "active_dimensions": active_dims}
                }
            except Exception as e:
                return {"response": f"❌ Falha ao executar o fluxo no n8n: {e}", "context": {"active_dimensions": active_dims}}
        
        # 4. Load wiki context
        wiki_context = await self._load_wiki_context()
        
        # 5. Generate response via DeepSeek
        if not self._deepseek:
            return {
                "response": "🛡️ HERMES está em modo degradado. Serviço DeepSeek indisponível. Use o comando `hermes:true` no chat padrão.",
                "context": {"type": "degraded", "active_dimensions": active_dims}
            }
        
        response = await self._deepseek.generate_chat_response(
            user_message=user_message,
            active_dimensions=active_dims,
            wiki_context=wiki_context,
            compliance_context=compliance_context
        )
        
        return {
            "response": response,
            "context": {
                "active_dimensions": active_dims,
                "has_compliance_alerts": bool(self.divergencias),
                "compliance_count": len(self.divergencias)
            }
        }

    def _format_compliance_report(self, report: Dict) -> str:
        """Format compliance report for chat display."""
        if not report or "error" in report:
            return "❌ Falha ao executar auditoria de compliance."
        
        parts = ["🛡️ **Relatório de Compliance HERMES**\n"]
        
        divs = report.get("divergencias", [])
        confs = report.get("conformidades", [])
        
        if confs:
            parts.append(f"✅ **{len(confs)} Conformidades:**")
            for c in confs[:5]:
                parts.append(f"  • {c}")
            parts.append("")
        
        if divs:
            parts.append(f"🚨 **{len(divs)} Divergências:**")
            for d in divs[:5]:
                severity_icon = {"CRITICAL": "💀", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
                icon = severity_icon.get(d["severity"], "⚪")
                parts.append(f"  {icon} **{d['area']}**")
                parts.append(f"    Esperado: {d['expected']}")
                parts.append(f"    Real: {d['actual']}")
                parts.append(f"    Impacto: {d['impact']}")
                parts.append("")
        
        if not divs and not confs:
            parts.append("Nenhuma auditoria realizada ainda.")
        
        return "\n".join(parts)

    async def _generate_system_status(self) -> str:
        """Generate system status summary for chat."""
        try:
            slots = await sovereign_service.get_active_slots()
            active = [s for s in slots if s.get("symbol")]
            
            parts = ["📊 **Status do Sistema 10D**\n"]
            parts.append(f"⚡ Slots: {len(active)}/4 ativos")
            
            for s in active:
                symbol = s.get("symbol", "???")
                roi = float(s.get("pnl_percent", 0))
                side = s.get("side", "LONG")
                entry = float(s.get("entry_price", 0))
                stop = float(s.get("current_stop", 0))
                
                roi_icon = "🟢" if roi >= 0 else "🔴"
                parts.append(f"  {roi_icon} {symbol} ({side}) ROI: {roi:.1f}% | Entry: ${entry:.4f} | SL: ${stop:.4f}")
            
            if self.divergencias:
                parts.append(f"\n🚨 {len(self.divergencias)} divergência(s) de compliance ativa(s)")
            
            parts.append(f"\n🛡️ Hermes: ONLINE | DeepSeek: Conectado")
            
            return "\n".join(parts)
        except Exception as e:
            return f"❌ Erro ao gerar status: {e}"

    # ============================================================
    # 📡 NOTIFICATIONS
    # ============================================================

    async def _emit_notification(self, title: str, message: str, severity: str = "INFO"):
        """Emit notification via WebSocket to PWA."""
        from services.websocket_service import websocket_service
        
        await websocket_service.broadcast({
            "type": "hermes_notification",
            "data": {
                "title": title,
                "message": message,
                "severity": severity,
                "timestamp": time.time()
            }
        })

    async def _broadcast_compliance(self, report: Dict):
        """Broadcast compliance report via WebSocket."""
        from services.websocket_service import websocket_service
        
        await websocket_service.broadcast({
            "type": "hermes_compliance",
            "data": {
                "total_divergencias": report.get("total_divergencias", 0),
                "total_conformidades": report.get("total_conformidades", 0),
                "resumo": report.get("resumo", ""),
                "divergencias": [
                    {"area": d["area"], "severity": d["severity"], "impact": d["impact"]}
                    for d in report.get("divergencias", [])
                ],
                "timestamp": report.get("timestamp", time.time())
            }
        })

    # ============================================================
    # 🔍 FORCE CHECK (API Trigger)
    # ============================================================

    async def force_compliance_check(self) -> Dict:
        """Force an immediate compliance check (called from API)."""
        return await self.run_compliance_audit()


# Singleton
hermes_agent = HermesAgent()
