# -*- coding: utf-8 -*-
import asyncio
import logging
import time
import json
import hmac
import hashlib
import base64
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import httpx
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OKXService")

class OKXService:
    def __init__(self):
        self.api_key = settings.OKX_API_KEY_MASTER
        self.api_secret = settings.OKX_API_SECRET_MASTER
        self.passphrase = settings.OKX_PASSPHRASE_MASTER
        self.testnet = settings.OKX_TESTNET
        
        # Base URL para OKX V5
        if self.testnet:
            self.base_url = "https://www.okx.com"
        else:
            self.base_url = "https://www.okx.com"
            
        self.is_mock = self.api_key == "mock_api_key_master_10d_sniper" or not self.api_key
        
        if self.is_mock:
            logger.warning("⚠️ [OKX] Credenciais mockadas detectadas! OKX Service rodando em MODO SIMULADO (MOCK).")
            # Estado mockado local para posições da conta Master
            self._mock_positions = [
                {
                    "instId": "BTC-USDT-SWAP",
                    "posSide": "long",
                    "pos": "0.1",
                    "availPos": "0.1",
                    "avgPx": "65000",
                    "upl": "120.5",  # PnL Não Realizado flutuante
                    "margin": "130.0",  # Margem Alocada
                    "mgnVal": "130.0",
                    "cTime": str(int(time.time() * 1000))
                },
                {
                    "instId": "ETH-USDT-SWAP",
                    "posSide": "short",
                    "pos": "1.5",
                    "availPos": "1.5",
                    "avgPx": "3400",
                    "upl": "-45.2",  # PnL não realizado flutuante
                    "margin": "102.0",  # Margem Alocada
                    "mgnVal": "102.0",
                    "cTime": str(int(time.time() * 1000))
                }
            ]
        else:
            self._mock_positions = []
            
        self._instrument_cache = {}
        logger.info(f"🔌 [OKX] Inicializado em modo {'TESTNET/SIMULADO' if self.testnet else 'MAINNET'}. Mock={self.is_mock}")

    def _get_timestamp(self) -> str:
        """Retorna timestamp no formato ISO 8601 UTC exigido pela OKX."""
        now = datetime.now(timezone.utc)
        return now.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """Gera assinatura HMAC-SHA256 em base64 para a autenticação OKX V5."""
        if not self.api_secret:
            return ""
        message = timestamp + method + request_path + body
        mac = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _get_headers(self, method: str, request_path: str, body: str = "") -> Dict[str, str]:
        """Gera os headers necessários para autenticação na OKX."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        if self.testnet:
            headers["x-simulated-trading"] = "1"

        if self.is_mock:
            return headers

        timestamp = self._get_timestamp()
        signature = self._generate_signature(timestamp, method, request_path, body)

        headers.update({
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase
        })

        return headers

    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Busca as posições ativas na conta.
        Retorna uma lista de posições formatadas de acordo com o padrão OKX V5.
        """
        if self.is_mock:
            # Atualiza levemente o PnL mockado para simular o mercado oscilando nos testes
            import random
            for pos in self._mock_positions:
                upl_val = float(pos["upl"])
                # Pequena variação simulando oscilação
                upl_val += random.uniform(-2.5, 3.5)
                pos["upl"] = f"{upl_val:.2f}"
            return self._mock_positions

        request_path = "/api/v5/account/positions"
        url = self.base_url + request_path
        headers = self._get_headers("GET", request_path)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0":
                        return data.get("data", [])
                    else:
                        logger.error(f"❌ [OKX REST] Erro na API OKX: {data.get('msg')}")
                        return []
                else:
                    logger.error(f"❌ [OKX REST] Erro de rede HTTP {response.status_code}: {response.text}")
                    return []
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica ao obter posições: {e}", exc_info=True)
            return []

    async def batch_close_positions(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Envia ordens em lote usando /api/v5/trade/batch-orders para zerar posições
        concorrentemente de forma ultra-rápida (Algoritmo Knife-Drop).
        """
        if not positions:
            logger.info("ℹ️ [OKX REST] Nenhuma posição para fechar em lote.")
            return {"code": "0", "msg": "No positions to close", "data": []}

        if self.is_mock:
            logger.info(f"🔪 [KNIFE-DROP MOCK] Executando fechamento em lote de {len(positions)} posições!")
            closed_symbols = [pos["instId"] for pos in positions]
            self._mock_positions = []  # Esvazia posições mockadas
            logger.info(f"✨ [KNIFE-DROP MOCK] Posições fechadas com sucesso: {closed_symbols}")
            return {"code": "0", "msg": "success", "data": [{"clOrdId": f"mock_close_{i}", "ordId": f"okx_ord_{i}", "sCode": "0", "sMsg": "success"} for i in range(len(positions))]}

        request_path = "/api/v5/trade/batch-orders"
        url = self.base_url + request_path
        
        # Constrói o corpo da ordem de mercado para fechamento
        # Para fechar uma posição, enviamos uma ordem com a direção oposta (posSide correspondente)
        orders = []
        for pos in positions:
            inst_id = pos["instId"]
            pos_side = pos["posSide"]  # "long" ou "short"
            size = pos["pos"]  # Qtd da posição
            
            # Direção de fechamento:
            # Se posSide = long, side = sell
            # Se posSide = short, side = buy
            side = "sell" if pos_side == "long" else "buy"
            
            order_req = {
                "instId": inst_id,
                "tdMode": "cross",  # Portfolio Margin usa cross margin
                "side": side,
                "posSide": pos_side,
                "ordType": "market",
                "sz": size,
                "clOrdId": f"kd_{inst_id.lower().replace('-', '_')}_{int(time.time()*1000)}"
            }
            orders.append(order_req)

        body_str = json.dumps(orders)
        headers = self._get_headers("POST", request_path, body_str)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, content=body_str)
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"🔪 [KNIFE-DROP] Resposta do fechamento em lote OKX: {data}")
                    return data
                else:
                    logger.error(f"❌ [OKX REST] Erro de rede HTTP no fechamento em lote {response.status_code}: {response.text}")
                    return {"code": str(response.status_code), "msg": response.text}
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica no Knife-Drop batch close: {e}", exc_info=True)
            return {"code": "-1", "msg": str(e)}

    async def get_instrument_details(self, symbol: str) -> Dict[str, Any]:
        """
        Puxa e coloca em cache os limites de precisão (lotSize e stepSize) para evitar
        erros de precisão de ordens no book da OKX.
        """
        # Formata o símbolo do padrão Bybit (BTCUSDT) para OKX (BTC-USDT-SWAP)
        inst_id = symbol
        if "-" not in symbol:
            # Ex: AVAXUSDT -> AVAX-USDT-SWAP
            if symbol.endswith("USDT"):
                inst_id = f"{symbol[:-4]}-USDT-SWAP"
            elif symbol.endswith("USDC"):
                inst_id = f"{symbol[:-4]}-USDC-SWAP"
        
        if inst_id in self._instrument_cache:
            return self._instrument_cache[inst_id]

        if self.is_mock:
            mock_detail = {
                "instId": inst_id,
                "lotSize": "0.1" if "BTC" in inst_id else "1.0",
                "tickSize": "0.1",
                "minSz": "0.1" if "BTC" in inst_id else "1.0",
                "ctVal": "1.0"
            }
            self._instrument_cache[inst_id] = mock_detail
            return mock_detail

        request_path = f"/api/v5/public/instruments?instType=SWAP&instId={inst_id}"
        url = self.base_url + request_path
        headers = self._get_headers("GET", request_path)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0" and data.get("data"):
                        inst_info = data["data"][0]
                        detail = {
                            "instId": inst_info.get("instId"),
                            "lotSize": inst_info.get("lotSz", "1.0"),
                            "tickSize": inst_info.get("tickSz", "0.01"),
                            "minSz": inst_info.get("minSz", "1.0"),
                            "ctVal": inst_info.get("ctVal", "1.0") # Valor do contrato
                        }
                        self._instrument_cache[inst_id] = detail
                        return detail
                    else:
                        logger.error(f"❌ [OKX REST] Instrumento {inst_id} não encontrado na OKX.")
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP ao buscar instrumento {response.status_code}")
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha ao obter detalhes do instrumento {inst_id}: {e}")

        # Fallback seguro
        fallback = {"instId": inst_id, "lotSize": "1.0", "tickSize": "0.01", "minSz": "1.0", "ctVal": "1.0"}
        return fallback

# Instanciação Singleton
okx_service = OKXService()
