# 1CRYPTEN / 10D Sniper Factory V4.0 — Complete Architecture Reference
## Every Constant, Threshold, Strategy, Endpoint, Version, and Contradiction
## Last Update: 2026-06-25 (V114 — Sandbox Cooldown + 1M Confirmation Filter)

---

## 1. VERSIONS (Scattered Across Codebase)

| Location | Version | Context |
|---|---|---|
| `main.py:1` root | V110.704 | DEPLOYMENT_ID |
| `Dockerfile:14` | V110.708 | Build trigger 2026-06-03 |
| `requirements.txt` | V110.400 | Stable dependency stack |
| `database_service.py:1` | V110.175 | DB service |
| `blitz_sniper.py:1` | V110.137 | M30 extraction |
| `bankroll.py:1` | V111.0+ | Open position logic |
| `captain.py` | V20.5 | JARVIS system prompt |
| `hermes_agent.py` | V2.0 | ESCADINHA_DOCS_SSOT |
| `signal_generator.py` | V110.116/V110.118 | PriorityQueue, tie-breaker |
| `order_projection_service.py` | V110.999 | Stop ladder |
| `flash_agent.py` | V110.100+ | Escadinha motor |
| `fleet_audit.py` | V7.0 | Early ROI Panic |
| `market.py:228` | V110.100 | Protocol label in system_state |
| `hermes_system_prompt` in chat.py | V4.0 | "10D Sniper Factory V4.0" |
| `librarian.py` | V2.0/V2.1/V2.2 | Strategic study |
| `trade_analyst.py` | V1.0 | Performance Intelligence |
| `quartermaster.py` | V110.135 | Wick classification |
| `macro_analyst.py` | V35.0/V55.0 | Macro trend, BTC dominance |
| `whale_tracker.py` | V43.0/V89.0 | CVD analysis |
| `fleet_audit.py` | V16.5/V80.6 | State parity |
| `ai_service.py` | V110.505/V110.637 | Vision cascade |

**CONTRADICTION**: Multiple version schemes coexist — V20.5 (captain), V110.x (services), V2.x (hermes), V1.0 (trade_analyst). No single source of truth.

---

## 2. NUMERIC CONSTANTS & THRESHOLDS

### 2.1 Trading Core
| Constant | Value | Location |
|---|---|---|
| Default Leverage | 50x | `config.py`, `bankroll.py:80`, `slot_operator.py:123` |
| Sniper TP Percent | 0.02 (2% price = 100% ROI @ 50x) | `bankroll.py:80` |
| Max Slots (Lateral) | 20 | `bankroll.py:58` |
| Max Slots (Trending) | 40 | `bankroll.py:59` |
| Max Pending Slots | 1 | `bankroll.py:57` |
| DVAP Fixed Margin | Lateral=$2, Trending=$1 | `bankroll.py:54-55` |
| Min Gap Between Entries | 2s (`OPEN_COOLDOWN_SEC`) | `signal_generator.py` |
| Radar/Scan Interval | 5s | `signal_generator.py` |
| API Semaphore Limit | 5 concurrent | `signal_generator.py`, `market.py:524` |
| Priority Queue Tie-Breaker | V110.118 counter | `signal_generator.py` |

### 2.2 Oracle & Regime
| Constant | Value | Location |
|---|---|---|
| Oracle Stabilization Period | 150s (2.5 min) | `oracle_agent.py` |
| ADX Trending Threshold | 25 | `oracle_agent.py`, `quartermaster.py:73`, `market.py:214` |
| ADX Lateral Threshold | 25 (below = lateral) | `oracle_agent.py` |
| Regime Types | TRENDING, RANGING, TRANSITION | `oracle_agent.py` |

### 2.3 Escadinha (Trailing Stop) Phases
| Phase | ROI Trigger | Stop Level | Source |
|---|---|---|---|
| ORDER | 0% (entry) | Initial stop | `order_projection_service.py` |
| RISK_ZERO | 50% ROI | +25% ROI stop | `config.py` (SSOT unificado V121) |
| LUCRO_GARANTIDO | 100% ROI | — | `hermes_agent.py:172` |
| SUCESSO_TOTAL | 130% ROI | — | `hermes_agent.py:172` |
| EMANCIPACAO | 150% ROI | Moonbag +110% ROI | `hermes_agent.py:172`, `chat.py:82` |
| ESCADINHA | Intermediate | Trailing | `order_projection_service.py` |
| TRAILING | Active | Dynamic | `order_projection_service.py` |

**NOTE (V121)**: RISK_ZERO unificado em `config.py` — trigger 50% ROI, stop +25% ROI. `chat.py`, `hermes_agent.py` e `execution_protocol.py` agora leem do mesmo SSOT.

### 2.4 FlashAgent (Escadinha Motor)
| Constant | Value | Location |
|---|---|---|
| Trailing Stop Cycle | 1s | `flash_agent.py` |
| Slots Cache TTL | 3s | `flash_agent.py` |
| Decor Check Interval | 60s | `flash_agent.py` |

### 2.5 Blitz Sniper (M30 Extraction)
| Constant | Value | Location |
|---|---|---|
| Scan Cooldown | 300s (5 min) | `blitz_sniper.py` |
| Signal Cache TTL | 120s (2 min) | `blitz_sniper.py` |
| Min Elite Score | 80 | `blitz_sniper.py` |
| Fibonacci Zones | 0.382, 0.5, 0.618 | `blitz_sniper.py` |
| Indicators | Fibonacci, SMA, CVD, PriceAction, Volume, DNA | `blitz_sniper.py` |

### 2.6 Ambush Agent (Fibonacci Entry)
| Constant | Value | Location |
|---|---|---|
| Max Wait | 1800s (30 min) | `ambush.py:22` |
| Shallow Dip Target | Fibo 0.382 | `ambush.py:58` |
| Golden Zone Target | Fibo 0.5 | `ambush.py:55` |
| Sweep Tolerance (BUY) | 0.998x target | `ambush.py:83` |
| Sweep Tolerance (SELL) | 1.002x target | `ambush.py:84` |
| CVD Abort Threshold (BUY) | < -150,000 | `ambush.py:120` |
| CVD Abort Threshold (SELL) | > 150,000 | `ambush.py:128` |
| Volatility Class → Target | EXTREME/VOLATILE → 0.5 Fibo, else → 0.382 | `ambush.py:54-58` |

### 2.7 Quartermaster (Leverage Classification)
| Wick Intensity | Classification | Leverage | Margin Multiplier |
|---|---|---|---|
| < 0.45 | SMOOTH | 50x | 1.0x |
| 0.45–0.70 | JUMPY | 20x | 2.5x |
| > 0.70 | EXTREME | 10x | 5.0x |
| Pure Doji | — | — | 5.0 (max penalty) |

**Block Rule**: EXTREME + BTC ADX < 25 → BLOCK (except PAPER mode bypass)

### 2.8 Macro Analyst
| Constant | Value | Location |
|---|---|---|
| BTC Dominance Cache | 600s (10 min) | `macro_analyst.py:45` |
| Kline Cache | 300s (5 min) | `macro_analyst.py:98` |
| Correlation Threshold (Panic) | 0.8 | `macro_analyst.py:129` |
| BTC Drop Threshold (Panic) | -2.0% in 1H | `macro_analyst.py:130` |
| Risk Score: BTC > 2% | +4 | `macro_analyst.py:215` |
| Risk Score: BTC > 1% | +2 | `macro_analyst.py:216` |
| Risk Score: Dominance > 55% | +2 | `macro_analyst.py:221` |
| Risk Score: Dominance < 48% | -2 | `macro_analyst.py:222` |
| Risk Score Range | 0–10 | `macro_analyst.py:225` |

### 2.9 Whale Tracker
| Constant | Value | Location |
|---|---|---|
| Bull Trap: CVD Delta | > 40,000 + Price < 0.03% | `whale_tracker.py:75` |
| Bear Trap: CVD Delta | < -40,000 + Price > -0.03% | `whale_tracker.py:80` |
| Whale Pulse Threshold | 150,000 CVD delta | `whale_tracker.py:86` |
| Flow History Window | 5 entries | `whale_tracker.py:60` |
| Whale Presence: High | abs(CVD) > 100,000 | `whale_tracker.py:99` |
| Whale Presence: Moderate | abs(CVD) > 50,000 | `whale_tracker.py:101` |

### 2.10 Fleet Audit (State Parity)
| Constant | Value | Location |
|---|---|---|
| Reconciliation Interval | 20s | `fleet_audit.py:24` |
| Immunity Period (new positions) | 60s | `fleet_audit.py:88` |
| Early Panic Age Window | < 300s | `fleet_audit.py:91` |
| Early Panic ROI Threshold | -80% | `fleet_audit.py:91` |
| Emergency Exit ROI | -90% | `fleet_audit.py:96` |
| SL Deviation Tolerance | 0.2% | `fleet_audit.py:152` |
| Moonbag Promotion Buffer | 300s (5 min) | `fleet_audit.py:176` |

### 2.11 Librarian Agent
| Constant | Value | Location |
|---|---|---|
| Study Interval | 7200s (2 hours) | `librarian.py:37` |
| Initial Stagger (boot) | 30s | `librarian.py:62` |
| Negative Pattern Window | 259200s (72 hours) | `librarian.py:106` |
| Super Quarantine Window | 14400s (4 hours) | `librarian.py:92` |
| Super Quarantine Trigger | ≥ 2 consecutive losses | `librarian.py:89` |
| Top Rankings Kept | 25 | `librarian.py:408` |
| Kline Download (fresh) | 1500 candles (~62 days) | `librarian.py:244` |
| Kline Download (update) | 100 candles | `librarian.py:244` |
| DNA Default Ambush Buffer | 0.0012 (0.12%) | `librarian.py:313` |
| DNA VOLATILE Buffer | 0.0025 (0.25%) | `librarian.py:318` |
| DNA EXTREME Buffer | 0.0045 (0.45%) | `librarian.py:316` |
| Retest Heavy Wick Threshold | > 2.5 avg | `librarian.py:308` |
| Nectar Seal: ELITE | win_rate ≥ 70% + H4 UP + trades ≥ 10 | `librarian.py:324` |
| Quality Seal: SpecOps | win_rate ≥ 65% + DD ≤ 20% + H4 UP | `librarian.py:279` |
| Quality Seal: Quarentena | win_rate < 45% or DD ≥ 25% | `librarian.py:282` |
| Missed Opps Window | 2%–10% move (price %) | `librarian.py:481` |
| Missed Opps Max | 10 items | `librarian.py:495` |

**Memecoin Blacklist**: PEPE, DOGE, SHIB, FLOKI, BONK, WIF, MYRO, 1000SATS, ORDI, MEME, TURBO, PEOPLE

### 2.12 Librarian Auditor (Bias Adjustment)
| Constant | Value | Location |
|---|---|---|
| Audit Interval | 14400s (4 hours) | `librarian_auditor.py:48` |
| Min Trades for Bias Change | 5 | `librarian_auditor.py:89` |
| Bias: Low Win Rate | 0.5 (wr < 40%) | `librarian_auditor.py:94` |
| Bias: Moderate | 0.8 (wr < 50%) | `librarian_auditor.py:95` |
| Bias: High | 1.2 (wr > 65%) | `librarian_auditor.py:96` |
| Bias Range | 0.5–1.2 | `librarian_auditor.py:86` |
| Sensor Threshold for "Ampulheta" | score > 70 | `librarian_auditor.py:74` |

### 2.13 Trade Analyst
| Constant | Value | Location |
|---|---|---|
| Analysis Interval | 1800s (30 min) | `trade_analyst.py:74` |
| Sessions (UTC) | Asia 0–8, London 8–16, NY 13–22 | `trade_analyst.py:29-31` |
| Big Win Threshold | ≥ 50% ROI | `trade_analyst.py:49` |
| Win Threshold | ≥ 10% ROI | `trade_analyst.py:51` |
| Breakeven | 0–10% ROI | `trade_analyst.py:53` |
| Small Loss | -20% to 0% ROI | `trade_analyst.py:55` |
| Big Loss | < -20% ROI | `trade_analyst.py:57` |
| Target Hit Accuracy | ≥ 90% | `trade_analyst.py:163` |
| Adaptive: Raise Min Score | wr < 45% after 20+ trades → +5 | `trade_analyst.py:336` |
| Adaptive: Block Pattern | wr < 35% after 5+ trades | `trade_analyst.py:345` |

### 2.14 Slot Operator
| Constant | Value | Location |
|---|---|---|
| Loop Interval | 3s | `slot_operator.py:27` |
| Default Leverage (ROI calc) | 50x | `slot_operator.py:123` |
| PNL Update Threshold | > 1.0% change | `slot_operator.py:132` |

### 2.15 OnChain Whale Watcher
| Constant | Value | Location |
|---|---|---|
| USDT Alert Threshold | $500,000+ | `onchain_whale_watcher.py:79` |
| ETH Alert Threshold | 200+ ETH | `onchain_whale_watcher.py:79` |
| Max Alerts Kept | 20 | `onchain_whale_watcher.py:49` |

### 2.16 AI Service
| Constant | Value | Location |
|---|---|---|
| Vision Rate Limit | 10 RPM | `ai_service.py:29` |
| Vision Timeout (Gemini) | 15s | `ai_service.py:218` |
| Vision Timeout (OpenRouter) | 20s | `ai_service.py:256` |
| Gemini Backoff (429) | 120s | `ai_service.py:174` |
| Gemini Vision Backoff (quota) | 3600s (1 hour) | `ai_service.py:230` |
| DeepSeek Backoff (429) | 60s | `ai_service.py:140` |
| OpenRouter 429 Backoff | 300s | `ai_service.py:285` |
| AI Broadcast Interval | 60s | `ai_service.py:303` |
| Content Generation Timeout | 25s | `ai_service.py:164` |
| OpenRouter Key Prefix Fix | `sk-or-v1-` auto-prepend | `ai_service.py:34-37` |

**AI Provider Cascade** (DeepSeek primary, then):
1. DeepSeek (primary)
2. Gemini 2.0 Flash → Gemini 2.0 Flash Lite → Gemini Flash Latest
3. OpenRouter: `google/gemini-flash-1.5-8b`, `google/gemini-flash-1.5-exp`, `meta-llama/llama-3.2-11b-vision-instruct:free`, `openai/gpt-4o-mini`

### 2.17 Market Data (Sector Map)
| Sector | Symbols |
|---|---|
| AI | FET, AGIX, OCEAN, RNDR, NEAR, ROSE, TAO, GRT, AI, NFP, WLD, ARKM |
| MEME | PEPE, DOGE, SHIB, FLOKI, BONK, WIF, MYRO, 1000SATS, ORDI, MEME, TURBO, PEOPLE |
| L1 | BTC, ETH, SOL, ADA, DOT, AVAX, MATIC, LINK, BNB, ATOM, FTM, OP, ARB, APT, SUI, SEI, NEAR |
| DEFI | UNI, MKR, AAVE, SNX, LDO, JUP, RUNE, INJ, DYDX, CRV, 1INCH, GMX |
| INFRA | TIA, FIL, AR, GRT, DYM, PYTH, ALT |
| GAMEFI | IMX, BEAM, GALA, AXS, SAND, MANA, RON, APE |
| DEPIN | HNT, IOTX, POWR |
| PAYMENTS | TRX, XRP, LTC |
| DEFAULT | OTHER |

---

## 3. API ENDPOINTS

### 3.1 Market Routes (`/api`)
| Method | Path | Description |
|---|---|---|
| GET | `/api/elite-pairs` | OKX 50x eligible pairs |
| GET | `/api/btc/regime` | BTC regime (stub: BULLISH 0.95) |
| GET | `/api/radar/pulse` | Radar pulse signals |
| GET | `/api/radar/grid` | Market radar grid |
| GET | `/api/radar/librarian` | Librarian intelligence/rankings |
| GET | `/api/radar/regimes` | Per-pair regime analysis (42 pairs, 60s cache) |
| GET | `/api/captain/tocaias` | Active ambush symbols |
| GET | `/api/trend/{symbol}` | 1H trend analysis |
| GET | `/api/market/klines` | Klines proxy (15m–4H) |
| GET | `/api/system/state` | Full system state (1s cache) |
| GET | `/api/market/study` | Market study with patterns/FVG/OB |
| GET | `/api/vision/stats` | Vision stats (stub: 42 global) |

### 3.2 Chat Routes (`/api`)
| Method | Path | Description |
|---|---|---|
| POST | `/api/hermes/chat` | Hermes chat (primary) |
| POST | `/api/hermes/compliance` | Force compliance check |
| GET | `/api/hermes/status` | Hermes agent status |
| POST | `/api/chat` | Legacy Jarvis chat |
| POST | `/api/chat/manual` | Manual chat with dimensions |
| POST | `/api/chat/reset` | Reset chat history (API key required) |
| GET | `/api/chat/status` | Chat status |
| POST | `/api/tts` | Text-to-speech |
| GET | `/api/tts/voices` | TTS voices list |
| GET | `/api/logs` | Recent logs |

### 3.3 Trading Routes (`/api`)
| Method | Path | Description |
|---|---|---|
| GET | `/api/slots` | Get all slots (public, V110.999) |

### 3.4 Sandbox Routes (`/api/sandbox`)
| Method | Path | Description |
|---|---|---|
| GET | `/api/sandbox/trades` | List sandbox trades (param: active_only=bool) |
| GET | `/api/sandbox/stats` | Stats: total, active, win_rate, pnl, strategy_breakdown, current_regime |
| GET | `/api/sandbox/patterns` | Pattern mining: whitelist/blacklist pairs, direction win rate |
| GET | `/api/sandbox/analytics` | Detailed analytics: loss_by_regime, loss_by_symbol, loss_by_hour, risk_reward |
| POST | `/api/sandbox/clear` | Clear all sandbox trade history |

### 3.5 Vault Routes (`/api/vault`)
| Method | Path | Description |
|---|---|---|
| POST | `/api/vault/save` | Save encrypted keys |
| GET | `/api/vault/status` | Check vault status |

### 3.6 Admin Routes (`/api/admin`)
| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/users` | List users (admin) |
| GET | `/api/admin/stats` | System stats |
| POST | `/api/admin/user/{username}/status` | Update user status |
| POST | `/api/admin/lockdown` | Toggle lockdown |
| POST | `/api/admin/reset-system` | Nuclear reset |

### 3.7 Auth Routes
| Method | Path | Description |
|---|---|---|
| POST | `/login` | Login (JWT) |
| POST | `/register` | Register (pending approval) |
| POST | `/refresh` | Refresh token |
| POST | `/logout` | Logout |
| GET | `/me` | Current user profile |
| POST | `/change-password` | Change password |
| GET | `/users` | List users (admin, paginated) |
| PUT | `/users/{user_id}/role` | Change user role |
| DELETE | `/users/{user_id}` | Delete user |
| POST | `/users/{user_id}/approve` | Approve user |
| POST | `/users/{user_id}/block` | Block user |

### 3.8 System Routes
| Method | Path | Description |
|---|---|---|
| GET | `/api/test` | Basic test |
| GET | `/api/debug/test` | Debug test |
| GET | `/api/health` | Health check (includes VERSION, DEPLOYMENT_ID) |

### 3.9 Dashboard Routes
| Method | Path | Description |
|---|---|---|
| GET | `/favicon.ico` | Favicon |
| GET | `/api/dashboard` | Serve SPA index.html |
| GET | `/10d`, `/chat`, `/config` | SPA routes |
| GET | `/banca/ui`, `/vault/ui`, `/armament/ui` | Legacy redirects → SPA |
| GET | `/tower`, `/command-tower` | → `/config` |
| GET | `/banca`, `/radar`, `/vault` | → `/10d` |
| GET | `/logs` | → `/chat` |
| GET | `/settings` | → `/config` |

### 3.10 Rate Limiting
| Endpoint Group | Limit | Window |
|---|---|---|
| Chat/Hermes | 10 req | 60s per IP |

---

## 4. ARCHITECTURE

### 4.1 Two Entry Points
| File | Purpose | How It Runs |
|---|---|---|
| `main.py` (root) | Railway deployment (worker+web) | `python main.py` → FastAPI on PORT (default 8085) |
| `backend/main.py` | Dockerfile CMD | `uvicorn backend.main:app --host 0.0.0.0 --port 8085` |

**Root `main.py`** imports:
- `portfolio_guardian` (DESATIVADO but instantiated)
- `sentinel_auditor`
- All backend routes
- WebSocket endpoints for cockpit

**`backend/main.py`** imports:
- All backend routes
- Static file mounts for frontend
- Kernel boot on startup

### 4.2 Database Layer
| Database | Purpose | Key Tables |
|---|---|---|
| PostgreSQL (async) | Primary persistent storage | `slots`, `radar_pulse`, `banca_status`, `sandbox_trades`, `moonbags` |
| Firebase Firestore | Multi-tenant, cloud sync | `users`, `trade_history`, `trade_analytics`, `fleet_intelligence`, `vault_history` |
| Firebase RTDB | Real-time state | `system_state`, `active_slots`, `radar_pulse`, `chat_status`, `librarian_intelligence`, `banca` |
| SQLite (librarian) | Kline cache for backtesting | `klines` table |

### 4.3 Agent System (AIOS)
| Agent | Role | Key Behavior |
|---|---|---|
| `Captain` (V20.5) | JARVIS Brain, Signal Routing | Quality gates, regime gating, Fleet Consensus (Macro 15%, Whale 25%, SMC 30%, OnChain 30%) |
| `Oracle` | Data Integrity Guardian | Regime determination, ADX validation, 150s stabilization |
| `FlashAgent` | Escadinha Motor | 1s trailing stop cycle, single writer for stops |
| `SlotOperator` (x4) | Trade Execution | 3s observation loop, virtual stop loss monitoring |
| `BlitzSniper` | M30 Elite Extraction | 300s cooldown, score ≥ 80, dual slots (1&2) |
| `Ambush` | Fibonacci Entry | 30min timeout, Wyckoff reclaim detection |
| `BankrollGuardian` | Trade Authorization | Regime-gated entry, slot limits |
| `Quartermaster` | Leverage Scaling | Wick classification (SMOOTH/JUMPY/EXTREME) |
| `Librarian` | Asset DNA / Rankings | 2h study cycle, sector analysis, memecoin blacklist |
| `LibrarianAuditor` | Bias Adjustment | 4h audit cycle, sensor weight tuning |
| `MacroAnalyst` | BTC Macro Risk | Pearson correlation panic filter, dominance analysis |
| `WhaleTracker` | Institutional Flow | CVD/OI analysis, trap detection, whale pulse |
| `SentimentSpecialist` | Retail Sentiment | LS-Ratio + Funding Rate (no LLM) |
| `OnChainWhaleWatcher` | Blockchain Monitoring | Bybit hot wallet tracking, Etherscan API |
| `TradeAnalyst` | Post-Trade Autopsy | 30min batch analysis, pattern scoring, session tracking |
| `FleetAudit` | State Parity | 20s reconciliation, Early ROI Panic, ghost cleanup |
| `HermesAgent` | Compliance/Telemetry/Chat | DeepSeek integration, ESCADINHA_DOCS_SSOT |
| `JarvisBrain` | Multi-Dimension Chat | 10 personal dimensions (Trading, Philosophy, Family, etc.) |
| `AIService` | AI Provider Cascade | DeepSeek → Gemini → OpenRouter fallback |

### 4.4 Stop Ladder Architecture
**RANGING mode** — 3 levels (simplified)
**TRENDING mode** — 10+ levels (full Escadinha progression)

Phase lifecycle: `ORDER → ESCADINHA → TRAILING`

### 4.5 Key Contradictions Found

1. ~~**RISK_ZERO ROI threshold**: `chat.py` HERMES prompt says **80%**, `hermes_agent.py` SSOT says **50%**~~ ✅ RESOLVIDO V121: unificado em `config.py` (50% trigger → +25% stop)
2. **Version scheme**: Multiple overlapping versioning (V20.5, V110.x, V2.x, V1.0, V35.0, V43.0, V55.0, V56.0, V7.0, V16.5, V80.6, V89.0)
3. **Portfolio Guardian**: Imported and instantiated in root `main.py` but marked DESATIVADO — superseded by FlashAgent's individual stop handling
4. **Legacy Bybit references**: `market.py` still names services `BybitRest`, `BybitWS`; `fleet_audit.py` references "Bybit" in comments despite OKX-only operation
5. **`get_slot_type()` always returns "DVAP"** (V110.950) — makes slot type differentiation vestigial
6. ~~**Two distinct FastAPI apps**: Root `main.py` (Firebase-first) and `backend/main.py` (Postgres-first) serve different deployment paths~~ ✅ RESOLVIDO V120.4: apenas `backend.main:app` roda em produção
7. **Admin nuclear reset**: `admin.py:132` resets `paper_balance` to `100.0` but `admin.py:167` comment says "resetar banca para $20.00" and line 183 says "Banca de $100.00"
8. **`radar_pulse`**: Not a separate file — it's a data structure in `database_service.py`, `firebase_service.py`, and `websocket_service.py`

---

## 4.6 SandboxService — Forward Testing Lab (V113.2 / V114)

### Constants

| Constant | Value | Source |
|---|---|---|
| Bank (virtual) | **$22.00 USD** | `routes/sandbox.py:49` (`BANCA = 22.0`) |
| Avg Margin per Trade | **$0.75** | `routes/sandbox.py:50` (`MARGEM_MEDIA = 0.75`) |
| Margin range (simulated OKX) | $0.50 – $1.00 | `routes/sandbox.py:54` |
| PnL USD per trade | `(pnl_pct / 100.0) * 0.75` | `routes/sandbox.py:55` |
| Bank PnL (%) | `(total_pnl_usd / 22.0) * 100` | `routes/sandbox.py:82` |
| Leverage | 50x | `sandbox_service.py` |
| Monitor Cycle | 1s | `sandbox_service.py` |
| Price Cache TTL | 60s | `sandbox_service.py` |
| Conservative Price Window | 120s | `okx_ws_public.py:291` |
| Initial Stop (ALL regimes) | **-5% ROI** | `sandbox_service.py` (V113.2, unified) |
| Stale Entry Threshold | 70% of stop, floor -10% | `sandbox_service.py` |
| [V114] Stop-Out Cooldown | **300s (5 min) per symbol** | `sandbox_service.py` (`_stop_cooldown`) |
| [V114] 1M Candles Fetched | 5 (limit), 3 evaluated | `sandbox_service.py` |
| [V114] 1M Confirmation Threshold | 2 of 3 candles in signal direction | `sandbox_service.py` |
| Auto-Blocklist Check Interval | 120s | `sandbox_service.py` |
| Auto-Blocklist Trigger | PnL < -20% AND WR < 30% after 5+ trades | `sandbox_service.py` |
| US Market Open Filter | 13:30–14:30 UTC | `sandbox_service.py` |
| Frontend Poll (stats) | 2s | `sandbox.html` |
| Frontend Poll (patterns) | 5s | `sandbox.html` |
| Frontend Balance Placeholder | **$22.00 USD** | `sandbox.html:158` |

### Signal Pipeline (V114)

```
_process_radar_signals()
  1. ADX / regime filter (LATERAL vs TRENDING)
  2. Macro BTC filter (SMA 200 daily → BULLISH/BEARISH)
  3. US Market Open filter (13:30-14:30 UTC, extra ADX >= 28 required)
  4. Static + auto-blocklist check
  5. already_active check (no duplicate symbol+strategy+direction)
  6. [V114] Cooldown check: skip if symbol had CLOSED_SL within 300s
  7. [V114] 1M confirmation: 2/3 recent candles must confirm direction
  8. Entry Sanity Check: immediate ROI must not exceed 70% of stop
  9. save_sandbox_trade() → open position
```

### Log Identifiers

| Log Tag | When Fired |
|---|---|
| `[SANDBOX-OPEN]` | Trade opened successfully |
| `[SANDBOX-STALE]` | Entry rejected — price already past stale threshold |
| `[SANDBOX-COOLDOWN-SET]` | 300s cooldown registered after CLOSED_SL |
| `[SANDBOX-COOLDOWN]` | Signal blocked — symbol in cooldown (shows seconds remaining) |
| `[SANDBOX-1M-REJECT]` | Signal blocked — 1M candles don't confirm direction |
| `[SANDBOX-LOSS]` | Trade closed on stop (CLOSED_SL) |
| `[SANDBOX-FLASH]` | Stop ladder level advanced |
| `[SANDBOX-PARTIAL]` | 50% partial exit triggered at +15% ROI in LATERAL |
| `[SANDBOX-MACRO-BLOCK]` | Signal blocked by BTC SMA 200 macro filter |
| `[SANDBOX-OPEN-FILTER]` | Signal blocked by US market open timing filter |
| `[SANDBOX-BLOCKLIST]` | Symbol blocked by static or auto-blocklist |
| `[SANDBOX-AUTO-BLOCKLIST]` | Symbol added to auto-blocklist (critical performance) |
| `[SANDBOX-PRICE-UNAVAILABLE]` | Price unavailable in WS + REST + cache — tick skipped |

### Bug History

| Bug | Commit | Fix |
|---|---|---|
| WS=0 stop never detected | `5d77b0f` | `_check_stop_hit` now falls back to `_get_current_price()` (REST+cache) |
| Analytics `fase` typo | `7175a80` | `state.get("fase")` → `state.get("phase")` in `routes/sandbox.py` |
| Stale entry (MaxROI=0%) | `d92c28f` | Entry Sanity Check: 70% of stop threshold |
| Chain re-entries | `855fcec` | V114: 300s cooldown per symbol after CLOSED_SL |
| Entry against 1M momentum | `855fcec` | V114: 2/3 bearish/bullish 1M candle confirmation |


---

## 5. DEPLOYMENT

| Component | Value |
|---|---|
| Platform | Railway + Docker |
| Python | 3.12-slim |
| PORT | 8085 |
| Procfile | `web: python main.py` / `worker: python worker.py` |
| Health Check | `GET /api/health` |
| Entry Point (Docker) | `uvicorn backend.main:app --host 0.0.0.0 --port 8085` |
| Entry Point (Railway) | `python main.py` |

---

## 6. EXCHANGE INTEGRATION

| Component | Exchange | Mode |
|---|---|---|
| Primary | OKX | PAPER or REAL |
| Legacy (dead code) | Bybit (pybit) | Referenced but unused |
| WebSocket (private) | `wspap.okx.com` (testnet) / `ws.okx.com` (live) | Auth feed |
| WebSocket (public) | OKX public feed | Prices, CVD, RSI, OI |

---

## 7. KEY FILE PATHS

| File | Purpose | Lines |
|---|---|---|
| `backend/config.py` | All settings/thresholds | Core |
| `backend/main.py` | FastAPI app (Docker) | ~200 |
| `main.py` (root) | FastAPI app (Railway) | ~1300 |
| `backend/services/signal_generator.py` | Strategy engine (DECOR/VELOCITY/ALPHA) | ~3900+ |
| `backend/services/bankroll.py` | Position management | ~500 |
| `backend/services/order_projection_service.py` | Stop ladders | ~500 |
| `backend/services/agents/captain.py` | JARVIS V20.5 | ~2800+ |
| `backend/services/agents/hermes_agent.py` | Compliance orchestrator | ~500 |
| `backend/services/agents/librarian.py` | Asset DNA | 534 |
| `backend/services/agents/flash_agent.py` | Escadinha motor | ~500 |
| `backend/services/agents/trade_analyst.py` | Post-trade analytics | 481 |
| `frontend/cockpit.html` | Main SPA frontend | 431,526 bytes |
