# 📚 1Crypten Documentation Index

## 🚀 Getting Started
- **[README.md](./README.md)** — Quick start guide, setup instructions, and architecture overview
- **[frontend/LOGIN_GUIDE.md](./frontend/LOGIN_GUIDE.md)** — How to authenticate and access the system

## 🏗️ Architecture & Design
- **[MASTER_ARCHITECTURE.md](./MASTER_ARCHITECTURE.md)** — Complete system architecture (v111.4+)
  - AI stack layers (Hermes, Oracle, Captain, FlashAgent)
  - Signal generation and consensus protocols
  - Execution model and risk management
  - Version history and changes

- **[STATE.md](./STATE.md)** — Current operational state (v112.9)
  - Active features and components
  - Regime gating rules
  - Recent changes and known issues
  - Performance metrics

## 🎯 Core Protocols
- **[SNIPER_PROTOCOLS.md](./SNIPER_PROTOCOLS.md)** — Signal generation and execution
  - Entry signal protocols
  - Stop-loss laddering (ESCADINHA)
  - Regime gating (LATERAL vs TRENDING)
  - Strategy specifications (DECOR SHADOW, VELOCITY FLOW, ALPHA SHIELD)

- **[RESET_PROTOCOL.md](./RESET_PROTOCOL.md)** — System reset and recovery
  - Full system reset procedures
  - Component recovery strategies
  - Emergency bailout protocols

## 📋 Rules & Standards
- **[RULES.md](./RULES.md)** — Coding standards and project rules
  - Code style guidelines
  - Commit message format
  - Testing requirements
  - Security best practices

## 💻 Frontend Documentation
- **[frontend/README.md](./frontend/README.md)** — Frontend architecture
  - Component structure
  - React patterns used
  - State management (hooks)
  - Real-time WebSocket updates

## 🛠️ OpenCode Skills & Rules
The `.opencode/` directory contains reusable patterns and coding standards:

### Skills (Workflows)
- `skills/backend-patterns/` — FastAPI and Python patterns
- `skills/database-migrations/` — Database change management
- `skills/testing/` — Test writing patterns (TDD, unit, integration)
- `skills/deployment-patterns/` — Docker, Railway, production deployment
- `skills/security-review/` — Security auditing and hardening

### Rules (Quick Reference)
- `rules/python/` — Python coding rules
- `rules/common/` — Universal coding and git rules
- See individual `.md` files for specific guidance

## 📊 System Overview

### V112.9 Highlights (Current)
```
✅ Intelligent Regime Gating (LATERAL vs TRENDING)
✅ Dual-Execution (Sandbox + Real OKX simultaneously)
✅ FlashAgent V2.0 (Unified stop-loss management)
✅ 41 Supported Trading Pairs
✅ Real-time Cockpit Dashboard
✅ Emergency Panic System
✅ AI Consensus Stack (Oracle + Captain + Hermes)
```

### Architecture Layers (Top → Bottom)
1. **UI Layer** (frontend/): React + Tailwind, WebSocket real-time updates
2. **API Layer** (backend/routes/): FastAPI REST endpoints
3. **Service Layer**:
   - `agents/` — AI decision-making (Captain, FlashAgent, SlotOperator)
   - `bankroll.py` — Order execution and risk management
   - `execution_protocol.py` — Atomic order placement logic
4. **Connector Layer**:
   - `okx_service.py` — OKX REST API client
   - `okx_ws.py` — OKX WebSocket feed (real-time tickers)
5. **Storage Layer**:
   - Firebase Firestore — Persistent slot/trade data
   - Redis — Cache (tickers, CVD, OI, locks)
   - SQLite — Authentication database

## 🔄 Key Workflows

### Signal → Execution Path
```
Signal Generation
    ↓
Captain Agent (Quality Gate)
    ↓
Regime Gating Check
    ├─→ LATERAL? Use DECOR SHADOW only
    └─→ TRENDING? Use VELOCITY FLOW + ALPHA SHIELD
    ↓
BankrollManager (Capacity Check)
    ├─→ Sandbox: sandbox_service.simulate_order()
    └─→ Real: okx_rest_service.place_atomic_order()
    ↓
FlashAgent (Stop Management)
    ├─→ Monitor position every 1s
    ├─→ Update stop at ROI milestones
    └─→ Close on stop-loss or T/P hit
```

### Dashboard Updates
```
Backend (WebSocket Publisher)
    ├─→ Send slot updates every 500ms
    ├─→ Send price tickers every 1s
    ├─→ Send system status every 5s
    ↓
Frontend (React + Hooks)
    ├─→ useSlots() — Get active positions
    ├─→ useBanca() — Get bankroll status
    ├─→ useRadar() — Get incoming signals
    └─→ Render Cockpit Dashboard in real-time
```

## 🧪 Testing & Quality

### Test Categories
- **Unit Tests**: Individual function logic
- **Integration Tests**: Component interactions (OKX API mocking)
- **E2E Tests**: Full signal-to-execution flow

### Running Tests
```bash
# All tests
pytest

# Only fast unit tests
pytest -m "not slow"

# With coverage
pytest --cov=backend/
```

## 📞 Troubleshooting Map

| Problem | Root Cause | Solution | Docs |
|---------|-----------|----------|------|
| "Only sending to Sandbox" | OKX_EXECUTION_MODE=PAPER | Set to REAL in .env | [README.md](./README.md#environment-configuration) |
| Hermes appearing instead of Cockpit | Old routing config | Clear browser cache, check /cockpit route | [frontend/README.md](./frontend/README.md) |
| 429 Rate Limits from OKX | Too many rapid orders | System has anti-429 queue (OKXCommandQueue) | [MASTER_ARCHITECTURE.md](./MASTER_ARCHITECTURE.md) |
| Dashboard not updating | WebSocket connection dead | Check browser console, restart backend | [frontend/README.md](./frontend/README.md) |
| Slots not opening | Regime gate blocking entry | Check ADX regime in STATE.md | [SNIPER_PROTOCOLS.md](./SNIPER_PROTOCOLS.md) |

## 🚀 Deployment Checklist

- [ ] All unit tests passing: `pytest backend/tests/`
- [ ] Environment variables configured: `OKX_EXECUTION_MODE`, API credentials
- [ ] Frontend built: `npm run build`
- [ ] Backend dependencies installed: `pip install -r requirements.txt`
- [ ] Database initialized: `python backend/init_db.py`
- [ ] Start backend: `python main.py`
- [ ] Verify login works: http://localhost:8085/
- [ ] Verify Cockpit dashboard loads: http://localhost:8085/cockpit.html
- [ ] Check WebSocket connection: Open DevTools Network tab, filter by "ws"
- [ ] Test small order: Try opening a $1 position in sandbox first

## 📈 Performance Targets

| KPI | Target | Status |
|-----|--------|--------|
| Dashboard update latency | <100ms | ✅ ~50ms average |
| Signal-to-execution time | <5s | ✅ ~2-3s average |
| OKX API uptime | 99.9% | ✅ OKX SLA |
| Real-time connection uptime | 99.5% | ✅ ~99.7% (session avg) |

## 🔐 Security Notes

- **API Keys**: Never commit `.env` to repository
- **Credentials**: Use environment variables only (no hardcoding)
- **OKX Account**: Create sub-account for bot with reduced permissions
- **Firewall**: Restrict inbound traffic to known IPs
- **Rate Limiting**: All endpoints have rate-limit protections
- **Logging**: Never log full API keys; use truncation

## 🤝 Contributing

1. Read [RULES.md](./RULES.md) for coding standards
2. Create feature branch: `git checkout -b feature/description`
3. Keep PRs focused and small (<300 lines when possible)
4. Add tests for new code
5. Update relevant `.md` docs
6. Reference this index in your PRs

## 📞 Contact & Support

- **Main Repository**: https://github.com/JonatasOliveira1983/1C-7.0
- **Commit History**: https://github.com/JonatasOliveira1983/1C-7.0/commits/main
- **Issues**: https://github.com/JonatasOliveira1983/1C-7.0/issues
- **Latest PR**: Check recent pull requests for active work

---

**Last Updated**: 2026-06-23  
**Current Version**: V112.9  
**Status**: 🟢 Production Ready
