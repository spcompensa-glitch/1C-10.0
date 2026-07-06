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
    @staticmethod
    def to_okx_inst_id(symbol: str) -> str:
        """Converte símbolo legacy Bybit (ex: AVAXUSDT ou AVAXUSDT.P) para formato OKX nativo (ex: AVAX-USDT-SWAP)."""
        if not symbol:
            return ""
        norm = symbol.strip().upper()
        if norm.endswith(".P"):
            norm = norm[:-2]
        
        if "-" in norm:
            return norm
            
        if norm.endswith("USDT"):
            return f"{norm[:-4]}-USDT-SWAP"
        elif norm.endswith("USDC"):
            return f"{norm[:-4]}-USDC-SWAP"
        return f"{norm}-USDT-SWAP"

    @staticmethod
    def from_okx_inst_id(symbol: str) -> str:
        """Converte símbolo OKX nativo (ex: AVAX-USDT-SWAP) para formato legacy com sufixo .P (ex: AVAXUSDT.P) usado em chaves de cache interno."""
        if not symbol:
            return ""
        norm = symbol.strip().upper()
        if "-" not in norm:
            if not norm.endswith(".P"):
                return f"{norm}.P"
            return norm
            
        parts = norm.split("-")
        base = parts[0]
        quote = parts[1] if len(parts) > 1 else "USDT"
        
        return f"{base}{quote}.P"

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

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "", custom_secret: str = None) -> str:
        """Gera assinatura HMAC-SHA256 em base64 para a autenticação OKX V5."""
        secret = custom_secret or self.api_secret
        if not secret:
            return ""
        message = timestamp + method + request_path + body
        mac = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _get_headers(self, method: str, request_path: str, body: str = "", **kwargs) -> Dict[str, str]:
        """Gera os headers necessários para autenticação na OKX. Aceita credenciais dinâmicas."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        if self.testnet:
            headers["x-simulated-trading"] = "1"

        if self.is_mock:
            return headers

        custom_key = kwargs.get("custom_key")
        custom_secret = kwargs.get("custom_secret")
        custom_passphrase = kwargs.get("custom_passphrase")

        timestamp = self._get_timestamp()
        signature = self._generate_signature(timestamp, method, request_path, body, custom_secret=custom_secret)

        headers.update({
            "OK-ACCESS-KEY": custom_key or self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": custom_passphrase or self.passphrase
        })

        return headers

    async def get_wallet_balance(self) -> float:
        """
        Busca o saldo total (totalEq) da conta OKX.
        Retorna 0.0 se falhar ou se estiver em modo mock.
        """
        if self.is_mock:
            return 0.0

        request_path = "/api/v5/account/balance"
        url = self.base_url + request_path
        headers = self._get_headers("GET", request_path)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0" and data.get("data"):
                        total_eq = float(data["data"][0].get("totalEq", 0.0))
                        logger.info(f"💰 [OKX-BALANCE] Saldo total da conta: ${total_eq:.2f}")
                        return total_eq
                    else:
                        logger.error(f"❌ [OKX-BALANCE] Erro na API: {data.get('msg')}")
                else:
                    logger.error(f"❌ [OKX-BALANCE] Erro HTTP {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"❌ [OKX-BALANCE] Falha ao obter saldo: {e}", exc_info=True)

        return 0.0

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
                "clOrdId": f"kd{inst_id.upper().replace('-SWAP', '').replace('-', '')}{int(time.time() * 1000)}"
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
        inst_id = self.to_okx_inst_id(symbol)
        
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

    async def place_atomic_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        sl_price: float,
        tp_price: float = None,
        slot_id: int = 0,
        leverage: float = 50,
        username: str = None,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        [Fase 1] Envia uma ordem de mercado (Market) atômica para a OKX Testnet/Mainnet
        com Stop Loss e Take Profit acoplados.
        """
        inst_id = self.to_okx_inst_id(symbol)
        
        # Converte o lado (side)
        # Bybit: Buy/Sell ➔ OKX: buy/sell
        side_okx = side.strip().lower()
        
        # Determina a direção da posição (posSide) para modo Hedge:
        # Se side é buy -> posSide é long
        # Se side é sell -> posSide é short
        pos_side = "long" if side_okx == "buy" else "short"
        
        # Ajusta lotes e step size usando o instrument details
        details = await self.get_instrument_details(symbol)
        lot_size = float(details.get("lotSize", "1.0"))
        
        # Arredonda a quantidade de forma precisa para múltiplos de lotSize
        rounded_qty = round(qty / lot_size) * lot_size
        min_sz = float(details.get("minSz", "1.0"))
        if rounded_qty < min_sz:
            rounded_qty = min_sz
            
        qty_str = f"{rounded_qty:.4f}".rstrip('0').rstrip('.')
        if not qty_str or qty_str == "0":
            qty_str = f"{min_sz}"

        cl_ord_id = f"snp{inst_id.upper().replace('-SWAP', '').replace('-', '')}{int(time.time() * 1000)}"

        # Corpo da requisição para a OKX V5 Order API
        order_req = {
            "instId": inst_id,
            "tdMode": "cross",  # Portfolio Margin exige cross margin
            "side": side_okx,
            "posSide": pos_side,
            "ordType": "market",
            "sz": qty_str,
            "clOrdId": cl_ord_id
        }

        # Acopla o Stop Loss / Take Profit via attachAlgoOrds (Exigência Moderna da OKX API v5)
        attach_list = []
        algo_item = {}
        
        if sl_price and sl_price > 0:
            algo_item.update({
                "slOrdPx": "-1",
                "slTriggerPx": f"{sl_price:.8f}".rstrip('0').rstrip('.'),
                "slTriggerPxType": "last"
            })
            
        if tp_price and tp_price > 0:
            algo_item.update({
                "tpOrdPx": "-1",
                "tpTriggerPx": f"{tp_price:.8f}".rstrip('0').rstrip('.'),
                "tpTriggerPxType": "last"
            })
            
        if algo_item:
            attach_list.append(algo_item)
            order_req["attachAlgoOrds"] = attach_list

        if self.is_mock:
            logger.info(f"🤖 [OKX-REST MOCK] place_atomic_order simulada: {order_req}")
            # Simula a posição criada no mock de posições ativas
            mock_pos = {
                "instId": inst_id,
                "posSide": pos_side,
                "pos": qty_str,
                "availPos": qty_str,
                "avgPx": "100.0",  # Preço médio mockado
                "upl": "0.0",
                "margin": str((float(qty_str) * 100.0) / leverage),
                "mgnVal": str((float(qty_str) * 100.0) / leverage),
                "cTime": str(int(time.time() * 1000))
            }
            # Remove qualquer posição duplicada se existir
            self._mock_positions = [p for p in self._mock_positions if p["instId"] != inst_id]
            self._mock_positions.append(mock_pos)
            return {
                "code": "0",
                "msg": "success",
                "data": [{"clOrdId": cl_ord_id, "ordId": f"okx_ord_{int(time.time())}", "sCode": "0", "sMsg": "success"}]
            }

        # [V124] Configurar alavancagem ANTES de enviar a ordem (corrige bug 3x → 50x)
        leverage_result = await self.set_leverage(symbol, leverage, mgn_mode="cross")
        if leverage_result and leverage_result.get("code") != "0":
            logger.warning(f"⚠️ [OKX] Falha ao configurar {leverage}x para {symbol}: {leverage_result.get('msg')}")

        request_path = "/api/v5/trade/order"
        url = self.base_url + request_path
        body_str = json.dumps(order_req)
        
        headers = self._get_headers(
            "POST", 
            request_path, 
            body_str, 
            custom_key=kwargs.get("api_key"),
            custom_secret=kwargs.get("api_secret"),
            custom_passphrase=kwargs.get("passphrase")
        )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, content=body_str)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0":
                        logger.info(f"✅ [OKX REST] Ordem enviada com sucesso: {data}")
                        return data
                    else:
                        err_detail = ""
                        if data.get("data"):
                            ord_err = data["data"][0]
                            err_detail = f" | sCode: {ord_err.get('sCode')} | sMsg: {ord_err.get('sMsg')}"
                            if ord_err.get("sCode") == "51001" and settings.OKX_EXECUTION_MODE == "PAPER":
                                logger.warning(f"🤖 [OKX-REST MOCK] {inst_id} não existe na Testnet (erro 51001). Simulando execução local com sucesso.")
                                return {
                                    "code": "0",
                                    "msg": "success",
                                    "data": [{"clOrdId": cl_ord_id, "ordId": f"okx_mock_{int(time.time())}", "sCode": "0", "sMsg": "success"}]
                                }
                        logger.error(f"❌ [OKX REST] Falha ao enviar ordem: {data.get('msg')}{err_detail} (payload: {order_req})")
                        return data
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} no envio da ordem: {response.text}")
                    return {"code": str(response.status_code), "msg": response.text}
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica no envio de ordem para {inst_id}: {e}", exc_info=True)
            return {"code": "-1", "msg": str(e)}

    async def close_position(self, symbol: str, side: str, qty: float, reason: str = "MANUAL_CLOSE", username: str = None, **kwargs) -> bool:
        """
        [Fase 1] Encerra uma posição individual de forma isolada na OKX Testnet/Mainnet
        enviando uma ordem de fechamento a mercado.
        """
        inst_id = self.to_okx_inst_id(symbol)
        side_norm = side.strip().lower()
        
        # No fechamento:
        # Se a posição for LONG (posSide="long"), enviamos um "sell" (side="sell")
        # Se a posição for SHORT (posSide="short"), enviamos um "buy" (side="buy")
        pos_side = "long" if side_norm in ["buy", "long"] else "short"
        close_side = "sell" if pos_side == "long" else "buy"
        
        details = await self.get_instrument_details(symbol)
        lot_size = float(details.get("lotSize", "1.0"))
        
        rounded_qty = round(qty / lot_size) * lot_size
        min_sz = float(details.get("minSz", "1.0"))
        if rounded_qty < min_sz:
            rounded_qty = min_sz
            
        qty_str = f"{rounded_qty:.4f}".rstrip('0').rstrip('.')
        if not qty_str or qty_str == "0":
            qty_str = f"{min_sz}"

        cl_ord_id = f"cls{inst_id.upper().replace('-SWAP', '').replace('-', '')}{int(time.time() * 1000)}"

        close_req = {
            "instId": inst_id,
            "tdMode": "cross",
            "side": close_side,
            "posSide": pos_side,
            "ordType": "market",
            "sz": qty_str,
            "clOrdId": cl_ord_id
        }

        if self.is_mock:
            logger.info(f"🤖 [OKX-REST MOCK] close_position simulado para {inst_id}: {close_req}")
            # Remove a posição correspondente do mock
            self._mock_positions = [p for p in self._mock_positions if p["instId"] != inst_id]
            return True

        request_path = "/api/v5/trade/order"
        url = self.base_url + request_path
        body_str = json.dumps(close_req)
        headers = self._get_headers(
            "POST", 
            request_path, 
            body_str,
            custom_key=kwargs.get("api_key"),
            custom_secret=kwargs.get("api_secret"),
            custom_passphrase=kwargs.get("passphrase")
        )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, content=body_str)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0":
                        logger.info(f"✅ [OKX REST] Posição de {inst_id} fechada com sucesso: {data}")
                        return True
                    else:
                        err_detail = ""
                        if data.get("data"):
                            ord_err = data["data"][0]
                            err_detail = f" | sCode: {ord_err.get('sCode')} | sMsg: {ord_err.get('sMsg')}"
                        logger.error(f"❌ [OKX REST] Falha ao fechar posição: {data.get('msg')}{err_detail} (payload: {close_req})")
                        return False
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} no fechamento de posição: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica ao fechar posição de {inst_id}: {e}", exc_info=True)
            return False

    async def get_klines(self, symbol: str, interval: str = "60", limit: int = 20) -> List[List[Any]]:
        """
        Busca velas históricas (Klines) públicas na OKX.
        Retorna uma lista de velas no formato da Bybit: [start_time, open, high, low, close]
        """
        # Se for OKX Testnet, apenas BTC e ETH têm cobertura garantida. Altcoins dão Instrument ID doesn't exist
        clean_sym = symbol.replace(".P", "").replace(".p", "").upper()
        if self.testnet and clean_sym not in ["BTCUSDT", "ETHUSDT"]:
            logger.info(f"ℹ️ [OKX REST] Ignorando chamada kline para {symbol} na OKX Testnet (cobertura reduzida).")
            return []

        inst_id = self.to_okx_inst_id(symbol)
        
        # Mapeamento de intervalos Bybit -> OKX
        interval_map = {
            "1": "1m",
            "3": "3m",
            "5": "5m",
            "15": "15m",
            "30": "30m",
            "60": "1H",
            "120": "2H",
            "240": "4H",
            "360": "6H",
            "720": "12H",
            "D": "1D",
            "W": "1W",
            "M": "1M"
        }
        bar = interval_map.get(str(interval), "1H")
        
        if self.is_mock:
            # Mock de klines para desenvolvimento local
            now_ms = int(time.time() * 1000)
            mock_klines = []
            import random
            price = 100.0
            for i in range(limit):
                ts = now_ms - (i * 3600 * 1000)
                o = price + random.uniform(-1.0, 1.0)
                h = o + random.uniform(0.0, 2.0)
                l = o - random.uniform(0.0, 2.0)
                c = (h + l) / 2
                mock_klines.append([str(ts), str(o), str(h), str(l), str(c)])
            return mock_klines

        request_path = f"/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}"
        url = self.base_url + request_path
        headers = self._get_headers("GET", request_path)

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0" and data.get("data"):
                        okx_candles = data.get("data", [])
                        # OKX retorna: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
                        # Bybit espera: [start_time, open, high, low, close]
                        formatted = []
                        for c in okx_candles:
                            if len(c) >= 5:
                                formatted.append([
                                    c[0], # ts
                                    c[1], # o
                                    c[2], # h
                                    c[3], # l
                                    c[4]  # c
                                ])
                        return formatted
                    else:
                        logger.error(f"❌ [OKX REST] Erro ao obter klines para {inst_id}: {data.get('msg')}")
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} ao buscar klines para {inst_id}")
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica ao obter klines para {inst_id}: {e}")
        
        return []

    async def get_open_interest(self, symbol: str) -> float:
        """
        Busca o Open Interest atual para um símbolo na OKX.
        """
        # Se for OKX Testnet, apenas BTC e ETH têm cobertura garantida. Altcoins dão Instrument ID doesn't exist
        clean_sym = symbol.replace(".P", "").replace(".p", "").upper()
        if self.testnet and clean_sym not in ["BTCUSDT", "ETHUSDT"]:
            return 0.0

        inst_id = self.to_okx_inst_id(symbol)
        
        if self.is_mock:
            return 1500000.0

        request_path = f"/api/v5/public/open-interest?instId={inst_id}"
        url = self.base_url + request_path
        headers = self._get_headers("GET", request_path)

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0" and data.get("data"):
                        return float(data["data"][0].get("oi", 0.0))
                    else:
                        logger.error(f"❌ [OKX REST] Erro ao obter Open Interest para {inst_id}: {data.get('msg')}")
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} ao buscar Open Interest para {inst_id}")
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica ao obter Open Interest para {inst_id}: {e}")
            
        return 0.0

    async def get_long_short_ratio(self, symbol: str, period: str = "5min") -> float:
        """
        Busca a proporção Long/Short para o símbolo na OKX.
        """
        inst_id = self.to_okx_inst_id(symbol)
        ccy = inst_id.split("-")[0] # ex: BTC
        
        # Mapeamento do período Bybit -> OKX
        okx_period = "5m"
        if "5" in period:
            okx_period = "5m"
        elif "15" in period:
            okx_period = "15m"
        elif "30" in period:
            okx_period = "30m"
        elif "1h" in period:
            okx_period = "1h"
        elif "4h" in period:
            okx_period = "4h"
        elif "1d" in period or "D" in period:
            okx_period = "1d"

        if self.is_mock:
            return 1.2

        request_path = f"/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={ccy}&period={okx_period}"
        url = self.base_url + request_path
        headers = self._get_headers("GET", request_path)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0" and data.get("data"):
                        ratio_data = data.get("data", [])
                        if ratio_data and len(ratio_data) > 0:
                            item = ratio_data[0]
                            if isinstance(item, dict):
                                return float(item.get("ratio", 1.0))
                            elif isinstance(item, list) and len(item) >= 2:
                                return float(item[1])
                    else:
                        logger.debug(f"ℹ️ [OKX REST Rubik] Endpoint ratio indisponível ou erro: {data.get('msg')}")
                else:
                    logger.debug(f"ℹ️ [OKX REST Rubik] Erro HTTP {response.status_code} ao buscar ratio")
        except Exception as e:
            logger.debug(f"❌ [OKX REST] Erro ao buscar long-short ratio no Rubik: {e}")
            
        return 1.0

    async def set_leverage(self, symbol: str, leverage: float, mgn_mode: str = "cross") -> Dict[str, Any]:
        """
        [V110.705] Configura a alavancagem e modo de margem na conta OKX.
        POST /api/v5/account/set-leverage
        """
        if self.is_mock:
            logger.info(f"🤖 [OKX-REST MOCK] set_leverage simulado para {symbol}: {leverage}x ({mgn_mode})")
            return {"code": "0", "msg": "success"}

        inst_id = self.to_okx_inst_id(symbol)
        request_path = "/api/v5/account/set-leverage"
        url = self.base_url + request_path
        
        body = {
            "instId": inst_id,
            "lever": str(int(leverage)),
            "mgnMode": mgn_mode
        }
        body_str = json.dumps(body)
        headers = self._get_headers("POST", request_path, body_str)
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, content=body_str)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0":
                        logger.info(f"✅ [OKX REST] Alavancagem de {inst_id} configurada para {leverage}x ({mgn_mode})")
                        return data
                    else:
                        logger.error(f"❌ [OKX REST] Falha ao configurar alavancagem para {inst_id}: {data.get('msg')}")
                        return data
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} ao setar alavancagem")
                    return {"code": str(response.status_code), "msg": f"HTTP error {response.status_code}"}
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica ao setar alavancagem para {inst_id}: {e}")
            return {"code": "-1", "msg": str(e)}

    async def get_klines(self, symbol: str, interval: str = "60", limit: int = 20) -> List[List[Any]]:
        """
        Busca velas históricas (Klines) públicas na OKX.
        Retorna uma lista de velas no formato da Bybit: [start_time, open, high, low, close]
        """
        # Se for OKX Testnet, apenas BTC e ETH têm cobertura garantida. Altcoins dão Instrument ID doesn't exist
        clean_sym = symbol.replace(".P", "").replace(".p", "").upper()
        if self.testnet and clean_sym not in ["BTCUSDT", "ETHUSDT"]:
            logger.info(f"ℹ️ [OKX REST] Ignorando chamada kline para {symbol} na OKX Testnet (cobertura reduzida).")
            return []

        inst_id = self.to_okx_inst_id(symbol)
        
        # Mapeamento de intervalos Bybit -> OKX
        interval_map = {
            "1": "1m",
            "3": "3m",
            "5": "5m",
            "15": "15m",
            "30": "30m",
            "60": "1H",
            "120": "2H",
            "240": "4H",
            "360": "6H",
            "720": "12H",
            "D": "1D",
            "W": "1W",
            "M": "1M"
        }
        bar = interval_map.get(str(interval), "1H")
        
        if self.is_mock:
            # Mock de klines para desenvolvimento local
            now_ms = int(time.time() * 1000)
            mock_klines = []
            import random
            price = 100.0
            for i in range(limit):
                ts = now_ms - (i * 3600 * 1000)
                o = price + random.uniform(-1.0, 1.0)
                h = o + random.uniform(0.0, 2.0)
                l = o - random.uniform(0.0, 2.0)
                c = (h + l) / 2
                mock_klines.append([str(ts), str(o), str(h), str(l), str(c)])
            return mock_klines

        request_path = f"/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}"
        url = self.base_url + request_path
        headers = self._get_headers("GET", request_path)

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0" and data.get("data"):
                        okx_candles = data.get("data", [])
                        # OKX retorna: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
                        # Bybit espera: [start_time, open, high, low, close]
                        formatted = []
                        for c in okx_candles:
                            if len(c) >= 5:
                                formatted.append([
                                    c[0], # ts
                                    c[1], # o
                                    c[2], # h
                                    c[3], # l
                                    c[4]  # c
                                ])
                        return formatted
                    else:
                        logger.error(f"❌ [OKX REST] Erro ao obter klines para {inst_id}: {data.get('msg')}")
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} ao buscar klines para {inst_id}")
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica ao obter klines para {inst_id}: {e}")
        
        return []

    async def get_open_interest(self, symbol: str) -> float:
        """
        Busca o Open Interest atual para um símbolo na OKX.
        """
        # Se for OKX Testnet, apenas BTC e ETH têm cobertura garantida. Altcoins dão Instrument ID doesn't exist
        clean_sym = symbol.replace(".P", "").replace(".p", "").upper()
        if self.testnet and clean_sym not in ["BTCUSDT", "ETHUSDT"]:
            return 0.0

        inst_id = self.to_okx_inst_id(symbol)
        
        if self.is_mock:
            return 1500000.0

        request_path = f"/api/v5/public/open-interest?instId={inst_id}"
        url = self.base_url + request_path
        headers = self._get_headers("GET", request_path)

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0" and data.get("data"):
                        return float(data["data"][0].get("oi", 0.0))
                    else:
                        logger.error(f"❌ [OKX REST] Erro ao obter Open Interest para {inst_id}: {data.get('msg')}")
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} ao buscar Open Interest para {inst_id}")
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica ao obter Open Interest para {inst_id}: {e}")
            
        return 0.0

    async def get_long_short_ratio(self, symbol: str, period: str = "5min") -> float:
        """
        Busca a proporção Long/Short para o símbolo na OKX.
        """
        inst_id = self.to_okx_inst_id(symbol)
        ccy = inst_id.split("-")[0] # ex: BTC
        
        # Mapeamento do período Bybit -> OKX
        okx_period = "5m"
        if "5" in period:
            okx_period = "5m"
        elif "15" in period:
            okx_period = "15m"
        elif "30" in period:
            okx_period = "30m"
        elif "1h" in period:
            okx_period = "1h"
        elif "4h" in period:
            okx_period = "4h"
        elif "1d" in period or "D" in period:
            okx_period = "1d"

        if self.is_mock:
            return 1.2

        request_path = f"/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy={ccy}&period={okx_period}"
        url = self.base_url + request_path
        headers = self._get_headers("GET", request_path)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0" and data.get("data"):
                        ratio_data = data.get("data", [])
                        if ratio_data and len(ratio_data) > 0:
                            item = ratio_data[0]
                            if isinstance(item, dict):
                                return float(item.get("ratio", 1.0))
                            elif isinstance(item, list) and len(item) >= 2:
                                return float(item[1])
                    else:
                        logger.debug(f"ℹ️ [OKX REST Rubik] Endpoint ratio indisponível ou erro: {data.get('msg')}")
                else:
                    logger.debug(f"ℹ️ [OKX REST Rubik] Erro HTTP {response.status_code} ao buscar ratio")
        except Exception as e:
            logger.debug(f"❌ [OKX REST] Erro ao buscar long-short ratio no Rubik: {e}")
            
        return 1.0

    async def set_leverage(self, symbol: str, leverage: float, mgn_mode: str = "cross") -> Dict[str, Any]:
        """
        [V110.705] Configura a alavancagem e modo de margem na conta OKX.
        POST /api/v5/account/set-leverage
        """
        if self.is_mock:
            logger.info(f"🤖 [OKX-REST MOCK] set_leverage simulado para {symbol}: {leverage}x ({mgn_mode})")
            return {"code": "0", "msg": "success"}

        inst_id = self.to_okx_inst_id(symbol)
        request_path = "/api/v5/account/set-leverage"
        url = self.base_url + request_path
        
        body = {
            "instId": inst_id,
            "lever": str(int(leverage)),
            "mgnMode": mgn_mode
        }
        body_str = json.dumps(body)
        headers = self._get_headers("POST", request_path, body_str)
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, content=body_str)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == "0":
                        logger.info(f"✅ [OKX REST] Alavancagem de {inst_id} configurada para {leverage}x ({mgn_mode})")
                        return data
                    else:
                        logger.warning(f"⚠️ [OKX REST] Falha ao configurar alavancagem para {inst_id}: {data.get('msg')}")
                        return data
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} ao setar alavancagem")
                    return {"code": str(response.status_code), "msg": response.text}
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica ao setar alavancagem para {inst_id}: {e}")
            return {"code": "-1", "msg": str(e)}

    async def get_pending_algo_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Busca ordens condicionais pendentes (como stop loss) para o par informado."""
        if self.is_mock:
            return [{"algoId": "mock_algo_sl_123", "instId": self.to_okx_inst_id(symbol), "slTriggerPx": "10.0", "ordType": "conditional"}]

        inst_id = self.to_okx_inst_id(symbol)
        request_path = f"/api/v5/trade/orders-algo-pending?instType=SWAP&instId={inst_id}&ordType=conditional"
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
                        logger.error(f"❌ [OKX REST] Erro ao obter algo orders para {inst_id}: {data.get('msg')}")
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} ao obter algo orders")
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha ao obter algo orders para {inst_id}: {e}")
        return []

    async def amend_algo_order(self, symbol: str, algo_id: str, new_stop_price: float) -> Dict[str, Any]:
        """Altera o preço de disparo de uma algo order existente (Stop Loss)."""
        if self.is_mock:
            logger.info(f"🤖 [OKX-REST MOCK] amend_algo_order {algo_id} para {new_stop_price}")
            return {"code": "0", "msg": "success", "data": [{"algoId": algo_id, "sCode": "0", "sMsg": "success"}]}

        inst_id = self.to_okx_inst_id(symbol)
        request_path = "/api/v5/trade/amend-algos"
        url = self.base_url + request_path

        payload = {
            "algoId": algo_id,
            "instId": inst_id,
            "newSlTriggerPx": f"{new_stop_price:.8f}".rstrip('0').rstrip('.')
        }
        body_str = json.dumps(payload)
        headers = self._get_headers("POST", request_path, body_str)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, content=body_str)
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} ao alterar algo order: {response.text}")
                    return {"code": str(response.status_code), "msg": response.text}
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica ao alterar algo order {algo_id}: {e}")
            return {"code": "-1", "msg": str(e)}

    async def place_algo_order(self, symbol: str, side: str, qty: float, sl_price: float, pos_side: str = None) -> Dict[str, Any]:
        """Coloca uma nova algo order condicional (Stop Loss independente)."""
        inst_id = self.to_okx_inst_id(symbol)
        side_okx = side.lower()
        if not pos_side:
            pos_side = "long" if side_okx == "buy" else "short"

        if self.is_mock:
            logger.info(f"🤖 [OKX-REST MOCK] place_algo_order {symbol} {side_okx} {qty} sl={sl_price}")
            return {"code": "0", "msg": "success", "data": [{"algoId": "mock_new_algo_123", "sCode": "0", "sMsg": "success"}]}

        details = await self.get_instrument_details(symbol)
        lot_size = float(details.get("lotSize", "1.0"))
        rounded_qty = round(qty / lot_size) * lot_size
        min_sz = float(details.get("minSz", "1.0"))
        if rounded_qty < min_sz:
            rounded_qty = min_sz
        qty_str = f"{rounded_qty:.4f}".rstrip('0').rstrip('.')

        payload = {
            "instId": inst_id,
            "tdMode": "cross",
            "side": "sell" if pos_side == "long" else "buy",  # O lado da ordem condicional de stop deve fechar a posição
            "posSide": pos_side,
            "ordType": "conditional",
            "sz": qty_str,
            "slTriggerPx": f"{sl_price:.8f}".rstrip('0').rstrip('.'),
            "slOrdPx": "-1",  # Stop Loss a mercado
            "reduceOnly": True
        }

        request_path = "/api/v5/trade/order-algo"
        url = self.base_url + request_path
        body_str = json.dumps(payload)
        headers = self._get_headers("POST", request_path, body_str)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, content=body_str)
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} ao criar algo order: {response.text}")
                    return {"code": str(response.status_code), "msg": response.text}
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica ao criar algo order para {symbol}: {e}")
            return {"code": "-1", "msg": str(e)}

    async def amend_batch_algo_orders(self, amends: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Altera múltiplas algo orders (stops) de uma só vez (máximo 10 por chamada da API da OKX).
        Formato de cada item em amends:
        {
           "algoId": str,
           "instId": str,
           "newSlTriggerPx": str
        }
        """
        if self.is_mock:
            logger.info(f"🤖 [OKX-REST MOCK] amend_batch_algo_orders para {len(amends)} ordens")
            return {"code": "0", "msg": "success", "data": [{"algoId": item["algoId"], "sCode": "0", "sMsg": "success"} for item in amends]}

        if not amends:
            return {"code": "0", "msg": "No orders to amend", "data": []}

        request_path = "/api/v5/trade/amend-algos"
        url = self.base_url + request_path
        body_str = json.dumps(amends)
        headers = self._get_headers("POST", request_path, body_str)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, content=body_str)
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"❌ [OKX REST] Erro HTTP {response.status_code} no amend de lote: {response.text}")
                    return {"code": str(response.status_code), "msg": response.text}
        except Exception as e:
            logger.error(f"❌ [OKX REST] Falha crítica no amend de algo orders em lote: {e}")
            return {"code": "-1", "msg": str(e)}

# Instanciação Singleton
okx_service = OKXService()
