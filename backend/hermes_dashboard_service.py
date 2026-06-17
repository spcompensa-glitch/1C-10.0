"""
Hermes Dashboard Service — Gerencia o processo do Hermes v0.16.0 Web Dashboard.

Inicia o servidor web do Hermes como subprocesso na porta 9119 (padrão).
Fornece API para controlar lifecycle: start, stop, restart, status.

Usage:
    from hermes_dashboard_service import hermes_dashboard
    await hermes_dashboard.start()
    await hermes_dashboard.stop()
    status = hermes_dashboard.get_status()
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from typing import Optional, Dict, Any

logger = logging.getLogger("HERMES-DASHBOARD")

# Porta onde o Hermes Dashboard vai rodar
HERMES_DASHBOARD_PORT = int(os.getenv("HERMES_DASHBOARD_PORT", "9119"))
HERMES_DASHBOARD_HOST = os.getenv("HERMES_DASHBOARD_HOST", "127.0.0.1")


class HermesDashboardService:
    """Gerencia o processo do Hermes Dashboard (hermes dashboard)."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._port: int = HERMES_DASHBOARD_PORT
        self._host: str = HERMES_DASHBOARD_HOST
        self._start_time: Optional[float] = None
        self._ready: bool = False

    @property
    def is_running(self) -> bool:
        """True se o processo está ativo."""
        if self._process is None:
            return False
        ret = self._process.poll()
        return ret is None

    @property
    def port(self) -> int:
        return self._port

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    async def start(self) -> bool:
        """Inicia o Hermes Dashboard como subprocesso."""
        if self.is_running:
            logger.warning("Hermes Dashboard já está rodando.")
            return True

        logger.info(f"Iniciando Hermes Dashboard em {self.base_url}...")

        try:
            # Tenta usar o comando `hermes dashboard`
            # Fallback: python -m hermes_cli.main web
            cmd = self._find_hermes_command()

            if not cmd:
                logger.error("Hermes CLI não encontrado. Certifique-se de que 'hermes-agent' está instalado.")
                return False

            # Constrói comando completo
            full_cmd = cmd + ["dashboard", "--port", str(self._port), "--host", self._host, "--skip-build"]

            logger.info(f"Comando: {' '.join(full_cmd)}")

            self._process = subprocess.Popen(
                full_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )

            self._start_time = time.time()

            # Aguarda o servidor ficar pronto (polling)
            ready = await self._wait_for_ready(timeout=30)
            if ready:
                self._ready = True
                logger.info(f"Hermes Dashboard ONLINE em {self.base_url}")
            else:
                logger.warning("Hermes Dashboard pode não estar pronto (timeout). Continuando...")

            return True

        except Exception as e:
            logger.error(f"Erro ao iniciar Hermes Dashboard: {e}")
            return False

    async def stop(self) -> bool:
        """Para o Hermes Dashboard."""
        if not self.is_running:
            logger.info("Hermes Dashboard não está rodando.")
            self._process = None
            self._ready = False
            return True

        logger.info("Parando Hermes Dashboard...")

        try:
            if sys.platform == "win32":
                self._process.terminate()
            else:
                self._process.send_signal(signal.SIGTERM)

            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Hermes Dashboard não respondeu ao SIGTERM. Forçando kill...")
                self._process.kill()
                self._process.wait(timeout=5)

        except Exception as e:
            logger.error(f"Erro ao parar Hermes Dashboard: {e}")
            self._process.kill()

        self._process = None
        self._ready = False
        logger.info("Hermes Dashboard parado.")
        return True

    async def restart(self) -> bool:
        """Reinicia o Hermes Dashboard."""
        await self.stop()
        await asyncio.sleep(1)
        return await self.start()

    def get_status(self) -> Dict[str, Any]:
        """Retorna o status atual do serviço."""
        return {
            "running": self.is_running,
            "ready": self._ready,
            "port": self._port,
            "host": self._host,
            "url": self.base_url,
            "uptime": (time.time() - self._start_time) if self._start_time and self.is_running else 0,
            "pid": self._process.pid if self._process and self.is_running else None,
        }

    def _find_hermes_command(self) -> Optional[list]:
        """Encontra o executável do Hermes CLI."""
        # 1. Tenta 'hermes' no PATH
        try:
            import shutil
            hermes_path = shutil.which("hermes")
            if hermes_path:
                return [hermes_path]
        except Exception:
            pass

        # 2. Tenta python -m hermes_cli.main
        try:
            import hermes_cli  # noqa: F401
            return [sys.executable, "-m", "hermes_cli.main"]
        except ImportError:
            pass

        return None

    async def _wait_for_ready(self, timeout: int = 30) -> bool:
        """Aguarda o servidor HTTP responder."""
        import httpx

        start = time.time()
        async with httpx.AsyncClient(timeout=5) as client:
            while time.time() - start < timeout:
                try:
                    resp = await client.get(f"{self.base_url}/api/status")
                    if resp.status_code == 200:
                        return True
                except (httpx.ConnectError, httpx.TimeoutException, Exception):
                    pass
                await asyncio.sleep(1)
        return False


# Singleton
hermes_dashboard = HermesDashboardService()
