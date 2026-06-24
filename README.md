# 1Crypten 7.0 — Elite Trading System

**Current Version:** V112.11 (Escadinha Refinada — Desempenho em Tendência)  
**Status:** 🟢 OPERATIONAL REAL (Live OKX Trading + Sandbox Testing)  
**Last Updated:** 2026-06-24

---

## 🎯 Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- OKX API credentials (with trading permissions)

### Local Setup
```bash
# 1. Clone repository
git clone https://github.com/JonatasOliveira1983/1C-7.0.git
cd 1C-7.0

# 2. Install dependencies
pip install -r backend/requirements.txt
npm install --prefix frontend

# 3. Configure environment
cp .env.example .env
# Edit .env with your OKX credentials

# 4. Start backend
python main.py

# 5. Backend serves frontend at http://localhost:8085
```

### Login
- **URL:** http://localhost:8085
- **Default User:** `admin` / `admin123`

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| **[MASTER_ARCHITECTURE.md](./MASTER_ARCHITECTURE.md)** | Complete system architecture, AI stack, and execution model |
| **[STATE.md](./STATE.md)** | Current operational state, active features, and recent changes |
| **[SNIPER_PROTOCOLS.md](./SNIPER_PROTOCOLS.md)** | Signal generation, regime gating, and trading protocols |
| **[RESET_PROTOCOL.md](./RESET_PROTOCOL.md)** | System reset procedures and recovery mechanisms |
| **[RULES.md](./RULES.md)** | Coding standards, patterns, and project rules |
| **[frontend/README.md](./frontend/README.md)** | Frontend architecture, components, and UI patterns |
| **[frontend/LOGIN_GUIDE.md](./frontend/LOGIN_GUIDE.md)** | Authentication and login flow |

---

## 🏗️ Architecture at a Glance

### Dual-Execution Model (V112.9)
- **Sandbox Mode**: All signals simulated for statistical analysis and backtesting
- **Real Mode**: Approved signals execute on OKX with live trading
- **Both run simultaneously** with identical risk management and regime filtering

### Signal Routing Flow
1. **Signal Generation** → AI stack generates entry signals
2. **Captain Agent** → Picks up signals, applies regime gating, routes to execution
3. **Regime Gating**:
   - LATERAL (ADX < 25) → Only DECOR SHADOW strategy executes
   - TRENDING (ADX ≥ 25) → VELOCITY FLOW + ALPHA SHIELD strategies execute
4. **Execution**:
   - Both sandbox_service.simulate_order() AND bankroll_manager.open_position() called
   - OKX atomic order placement via REST API
   - Stop-loss and take-profit levels managed by FlashAgent

### Risk Management
- **Portfolio Guardian**: Monitors overall account equity and drawdown
- **FlashAgent (V2.0)**: Manages stop-loss laddering per position
- **ExecutionCapacityGate**: Validates slippage, liquidity, funding costs before entry
- **Regime Shield**: Blocks entry signals that conflict with market regime

### Supported Assets (41 Pairs)
ELITE_40_MATRIX + SOL:
```
BTC, ETH, BNB, SOL, XRP, ADA, DOGE, POLKADOT, LINK, UNISWAP,
LITECOIN, CARDANO, COSMOS, MONERO, DOGECOIN, XRP, STELLAR, DASH,
TEZOS, FLOW, NEAR, FILECOIN, BALANCER, CURVE, AAVE, COMPOUND,
YEARN, WRAPPED_BTC, LIDO, ROCKETPOOL, CONVEX, SUSHISWAP, QUICKSWAP,
PANCAKESWAP, DYDX, FIL, ALGO, LTC, ... and more
```

---

## 🚀 Running in Production

### Docker Deployment
```bash
docker-compose up -d
# Deploys backend + frontend + Redis caching
```

### Railway Deployment
- See [Railway docs](https://railway.app)
- Branch: `main` → Auto-deploys to production
- URL: https://1crypten-hermes-agent-production.up.railway.app

### Monitoring
- **Cockpit Dashboard**: http://localhost:8085/cockpit (real-time trading UI)
- **Sandbox Testing**: http://localhost:8085/sandbox
- **Neural Chat**: http://localhost:8085/neural-chat
- **Hermes Dashboard**: http://localhost:8085/hermes (legacy admin interface)

---

## ⚙️ Environment Configuration

### Critical Variables
```bash
# OKX Trading (REAL = live trading, PAPER = sandbox only)
OKX_EXECUTION_MODE=REAL
OKX_API_KEY_MASTER=<your-api-key>
OKX_API_SECRET_MASTER=<your-api-secret>
OKX_PASSPHRASE_MASTER=<your-passphrase>
OKX_TESTNET=False

# System
PORT=8085
JWT_SECRET_KEY=<random-secret>
DATABASE_URL=sqlite:///./backend/auth.db

# Firebase (optional, for Firestore logging)
FIREBASE_CREDENTIALS_PATH=serviceAccountKey.json
```

---

## 🧪 Testing

### Run Unit Tests
```bash
pytest backend/tests/
```

### Run Integration Tests
```bash
pytest backend/tests/integration/
```

### Local Sandbox Testing
1. Start backend in PAPER mode: `OKX_EXECUTION_MODE=PAPER python main.py`
2. Open Sandbox UI at `/sandbox`
3. Test strategies without real money

---

## 🔄 API Endpoints

### Trading
- `POST /api/captain/take-signal` — Submit signal for execution
- `POST /api/trading/open-position` — Open new position
- `POST /api/trading/close-position/{slot_id}` — Close position
- `GET /api/slots` — Get active positions

### System
- `GET /api/system/status` — System health
- `POST /api/system/re-sync` — Sync with OKX
- `POST /panic` — Close all positions (emergency)

### History & Analytics
- `GET /api/history` — Trade history
- `GET /api/history/stats` — Performance statistics
- `GET /api/captain/tocaias` — Active signals being hunted

---

## 🐛 Troubleshooting

### Backend won't start
```bash
# Check OKX credentials in .env
# Verify Python 3.10+ installed: python --version
# Check port 8085 not in use: lsof -i :8085
```

### OKX orders not executing
```bash
# Check execution mode: OKX_EXECUTION_MODE must be REAL
# Verify credentials are correct
# Check OKX account has trading permissions
# Monitor logs for 429 (Rate Limit) or 50113 (balance insufficient) errors
```

### Frontend not loading
```bash
# Clear browser cache: Ctrl+Shift+Delete
# Check Network tab in DevTools for failed requests
# Verify backend serving static files: curl http://localhost:8085/cockpit.html
```

---

## 📊 Key Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Win Rate | >55% | See `/api/history/stats` |
| Avg Hold Time | 2-8h | Strategy dependent |
| Max Drawdown | <30% | ~15% (recent) |
| Sharpe Ratio | >1.5 | ~1.2 (live) |
| Active Slots | 1-16 | Variable |

---

## 🤝 Contributing

1. Fork repository
2. Create feature branch: `git checkout -b feature/something`
3. Commit changes: `git commit -m "fix: describe change"`
4. Push: `git push origin feature/something`
5. Create Pull Request
6. See [RULES.md](./RULES.md) for coding standards

---

## 📝 License

Proprietary — 1Crypten Inc.

---

## ❓ Support

- **Issues**: [GitHub Issues](https://github.com/JonatasOliveira1983/1C-7.0/issues)
- **Commits**: [Git History](https://github.com/JonatasOliveira1983/1C-7.0/commits/main/)
- **Architecture Questions**: See MASTER_ARCHITECTURE.md

---

**Last Deployed:** 2026-06-23  
**Maintainer:** Jonatas Oliveira (@JonatasOliveira1983)
