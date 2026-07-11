import os
import logging
from datetime import datetime
import asyncio

logger = logging.getLogger("1CRYPTEN-GALAXY")

class GalaxyMemoryService:
    def __init__(self, vault_path: str = None):
        if not vault_path:
            # Default directory in the root of the workspace
            self.vault_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vault_galaxy"))
        else:
            self.vault_path = os.path.abspath(vault_path)

        self.trades_dir = os.path.join(self.vault_path, "trades")
        self.journal_dir = os.path.join(self.vault_path, "journal")
        self.strategies_dir = os.path.join(self.vault_path, "strategies")

        self._initialized = False

    def ensure_dirs(self):
        if self._initialized:
            return
        try:
            os.makedirs(self.vault_path, exist_ok=True)
            os.makedirs(self.trades_dir, exist_ok=True)
            os.makedirs(self.journal_dir, exist_ok=True)
            os.makedirs(self.strategies_dir, exist_ok=True)
            self._initialized = True
        except Exception as e:
            logger.error(f"Erro ao inicializar diretórios do Memory Galaxy: {e}")

    async def save_trade_memory(self, trade_data: dict):
        """Salva a nota markdown do trade e cria os links de constelação."""
        self.ensure_dirs()
        try:
            trade_id = trade_data.get("id") or trade_data.get("order_id") or f"trade_{int(datetime.utcnow().timestamp())}"
            symbol = str(trade_data.get("symbol", "UNKNOWN")).upper()
            side = str(trade_data.get("side", "UNKNOWN")).upper()
            pnl = float(trade_data.get("pnl", 0.0))
            pnl_pct = float(trade_data.get("pnl_percent", 0.0))
            strategy = str(trade_data.get("strategy", "UNKNOWN")).upper()
            close_reason = str(trade_data.get("close_reason", "UNKNOWN"))
            entry_price = float(trade_data.get("entry_price", 0.0))
            exit_price = float(trade_data.get("exit_price", 0.0))
            
            # Formatação de datas
            ts = trade_data.get("timestamp")
            if isinstance(ts, datetime):
                dt_obj = ts
            else:
                try:
                    dt_obj = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                except:
                    dt_obj = datetime.utcnow()

            date_str = dt_obj.strftime("%Y-%m-%d")
            time_str = dt_obj.strftime("%H:%M:%S")

            filename = f"{date_str}_{symbol}_{trade_id}.md"
            filepath = os.path.join(self.trades_dir, filename)

            # Markdown Content
            md_content = f"""---
type: trade
id: "{trade_id}"
symbol: "{symbol}"
side: "{side}"
pnl: {pnl}
pnl_percent: {pnl_pct}
strategy: "{strategy}"
close_reason: "{close_reason}"
date: "{date_str}"
time: "{time_str}"
tags:
  - trade
  - symbol/{symbol}
  - strategy/{strategy}
  - pnl/{"profit" if pnl >= 0 else "loss"}
---

# Relatório de Operação: {symbol} ({side})

Relatório gerado automaticamente pelo motor sandbox do **1Crypten**.

## Métricas do Trade
| Métrica | Valor |
| --- | --- |
| **Identificador** | `{trade_id}` |
| **Par de Ativo** | `{symbol}` |
| **Direção** | `{side}` |
| **Estratégia** | `{strategy}` |
| **Preço de Entrada** | `${entry_price:.6f}` |
| **Preço de Saída** | `${exit_price:.6f}` |
| **PnL Realizado** | `${pnl:.2f} USD` |
| **Retorno (ROI)** | `{pnl_pct:.2f}%` |
| **Motivo de Fechamento** | `{close_reason}` |
| **Data e Hora** | `{date_str} {time_str} UTC` |

## Constelação de Contexto
- **Diário do Dia:** [[journal/{date_str}]]
- **Configurações Relacionadas:** [[strategies/{strategy.lower()}]]
"""
            # Grava a nota do trade de forma não-bloqueante
            await asyncio.to_thread(self._write_file, filepath, md_content)
            logger.info(f"✨ [MEMORY-GALAXY] Nota de trade registrada para {symbol} ({trade_id})")

            # Registra no diário diário também
            event_msg = f"- **Trade Fechado:** [[trades/{date_str}_{symbol}_{trade_id}|{symbol} {side}]] | PnL: `${pnl:.2f}` ({pnl_pct:.2f}%) | Motivo: `{close_reason}` | Estratégia: `{strategy}`"
            await self.log_journal_event("TRADE_CLOSE", event_msg, date_str)

        except Exception as e:
            logger.error(f"Erro ao salvar memória do trade: {e}")

    async def log_journal_event(self, event_type: str, description: str, date_str: str = None):
        """Grava ou adiciona um evento ao diário de bordo diário."""
        self.ensure_dirs()
        try:
            if not date_str:
                date_str = datetime.utcnow().strftime("%Y-%m-%d")

            filename = f"{date_str}.md"
            filepath = os.path.join(self.journal_dir, filename)

            time_str = datetime.utcnow().strftime("%H:%M:%S")
            
            # Se a nota de diário não existe, cria com frontmatter
            if not os.path.exists(filepath):
                initial_content = f"""---
type: journal
date: "{date_str}"
tags:
  - journal
---

# Diário de Operações — {date_str}

Notas de bordo e logs consolidados das operações executadas.

## Relatório de Eventos ({time_str} UTC)
{description}
"""
                await asyncio.to_thread(self._write_file, filepath, initial_content)
            else:
                # Se existe, lê e adiciona nova linha ao final do arquivo
                def append_event():
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # Procura ou cria seção de eventos
                    if "## Relatório de Eventos" not in content:
                        content += "\n\n## Relatório de Eventos\n"
                    
                    content += f"\n[{time_str} UTC] {description}"
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content)

                await asyncio.to_thread(append_event)

        except Exception as e:
            logger.error(f"Erro ao atualizar diário de bordo do Memory Galaxy: {e}")

    async def save_strategy_memory(self, strategy_name: str, config_summary: str):
        """Salva ou atualiza a documentação de uma estratégia no cofre."""
        self.ensure_dirs()
        try:
            name = strategy_name.lower()
            filename = f"{name}.md"
            filepath = os.path.join(self.strategies_dir, filename)

            md_content = f"""---
type: strategy
name: "{strategy_name}"
tags:
  - strategy
---

# Configurações de Estratégia: {strategy_name}

{config_summary}
"""
            await asyncio.to_thread(self._write_file, filepath, md_content)
        except Exception as e:
            logger.error(f"Erro ao salvar nota de estratégia: {e}")

    def _write_file(self, filepath: str, content: str):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

# Instância Singleton
galaxy_memory_service = GalaxyMemoryService()
