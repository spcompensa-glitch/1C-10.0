"""
Script para aplicar as modificações V112.12 no captain.py.
Arquivo muito grande para str_replace, então usamos substituição programática.
"""
import re

CAPTAIN_PATH = "backend/services/agents/captain.py"

with open(CAPTAIN_PATH, "r", encoding="utf-8") as f:
    content = f.read()

changes_made = 0

# ============================================================
# CHANGE 1: DECOR SHADOW em TRENDING - regime gate
# ============================================================
old_regime_gate = '''        # 1. Filtro por regime de volatilidade (LATERAL vs TRENDING)
        if current_regime == "LATERAL":
            if strategy_class in ("VELOCITY FLOW", "ALPHA SHIELD"):
                logger.warning(f"🚫 [CAPTAIN-REGIME-BLOCK] {symbol} {strategy_class} rejeitado em mercado LATERAL.")
                return
        else:
            if strategy_class == "DECOR SHADOW":
                logger.warning(f"🚫 [CAPTAIN-REGIME-BLOCK] {symbol} DECOR SHADOW rejeitado em mercado em TENDÊNCIA.")
                return'''

new_regime_gate = '''        # 1. Filtro por regime de volatilidade (LATERAL vs TRENDING)
        # [V112.12] DECOR_SHADOW agora permitido em TRENDING se descolado do BTC
        if current_regime == "LATERAL":
            if strategy_class in ("VELOCITY FLOW", "ALPHA SHIELD"):
                logger.warning(f"🚫 [CAPTAIN-REGIME-BLOCK] {symbol} {strategy_class} rejeitado em mercado LATERAL.")
                return
        else:
            if strategy_class == "DECOR SHADOW":
                try:
                    d_res = await signal_generator.detect_btc_decorrelation(symbol)
                    if d_res.get('is_decorrelated', False) and d_res.get('confidence', 0) >= 60:
                        logger.info(f"🔓 [V112.12 DECOR-TREND] {symbol} DECOR SHADOW liberado em tendência. Corr={d_res.get('correlation', 0):.2f} Conf={d_res.get('confidence', 0):.0f}")
                        best_signal["is_decorrelated"] = True
                    else:
                        logger.warning(f"🚫 [CAPTAIN-REGIME-BLOCK] {symbol} DECOR SHADOW rejeitado em mercado em TENDÊNCIA (corr={d_res.get('correlation', 0):.2f}).")
                        return
                except:
                    logger.warning(f"🚫 [CAPTAIN-REGIME-BLOCK] {symbol} DECOR SHADOW rejeitado em TENDÊNCIA (erro decorr).")
                    return'''

if old_regime_gate in content:
    content = content.replace(old_regime_gate, new_regime_gate)
    changes_made += 1
    print("[OK] CHANGE 1: Regime gate DECOR_TRENDING aplicado")
else:
    print("[FAIL] CHANGE 1: Regime gate nao encontrado")

# ============================================================
# CHANGE 2: MACRO FILTER com BYPASS
# ============================================================
old_macro_filter = '''        # 2. Filtro de Direção Macro (Trend Bias Filter)
        # Isenções:
        # - Estratégia DECOR SHADOW é imune à direção macro do BTC em qualquer regime.
        # - Se o mercado for LATERAL (ADX < 25), todos os bloqueios direcionais de tendência do BTC são ignorados.
        is_decor_shadow = strategy_class == "DECOR SHADOW"
        if not is_decor_shadow and current_regime != "LATERAL":
            if macro_trend == "BEARISH" and side.lower() in ("buy", "long", "b"):
                logger.warning(f"🚫 [CAPTAIN-MACRO-BLOCK] {symbol} {strategy_class} LONG rejeitado. Tendência Macro do BTC é BEARISH.")
                return
            elif macro_trend == "BULLISH" and side.lower() in ("sell", "short", "s"):
                logger.warning(f"🚫 [CAPTAIN-MACRO-BLOCK] {symbol} {strategy_class} SHORT rejeitado. Tendência Macro do BTC é BULLISH.")
                return
        else:
            logger.info(f"🔓 [CAPTAIN-MACRO-PASS] {symbol} {strategy_class} {side} liberado (D.S={is_decor_shadow}, Regime={current_regime}).")'''

new_macro_filter = '''        # 2. [V112.12] Filtro de Direção Macro com BYPASS por confluência
        # DECOR SHADOW é imune à direção macro. LATERAL ignora bloqueios direcionais.
        # MACRO_BYPASS: sinais >=75 score com CVD exhaustion ou zona S/R podem furar.
        is_decor_shadow = strategy_class == "DECOR SHADOW"
        if not is_decor_shadow and current_regime != "LATERAL":
            if macro_trend == "BEARISH" and side.lower() in ("buy", "long", "b"):
                bypass = False
                try:
                    sig_score = float(best_signal.get("score", 0) or 0)
                    if sig_score >= 75:
                        cvd_total = okx_ws_public_service.get_cvd_score(symbol)
                        cvd_15m = okx_ws_public_service.get_cvd_score_time(symbol, 900)
                        cvd_exhausted = cvd_total < -80000 and cvd_15m > -20000
                        zones = await signal_generator.get_15m_zones(symbol)
                        near_support = zones.get("near_zone", False) and zones.get("support", 0) > 0
                        if cvd_exhausted or near_support:
                            bypass = True
                            best_signal["is_mean_reversion"] = True
                            best_signal["macro_bypass_reason"] = "CVD_EXHAUSTION" if cvd_exhausted else "SUPPORT_BOUNCE"
                            logger.info(f"🔓 [V112.12 MACRO-BYPASS] {symbol} LONG liberado. Score={sig_score:.0f} Motivo={best_signal['macro_bypass_reason']}")
                except Exception as be:
                    logger.warning(f"[V112.12 MACRO-BYPASS] Erro {symbol}: {be}")
                if not bypass:
                    logger.warning(f"🚫 [CAPTAIN-MACRO-BLOCK] {symbol} {strategy_class} LONG rejeitado. Macro BEARISH sem bypass.")
                    return
            elif macro_trend == "BULLISH" and side.lower() in ("sell", "short", "s"):
                bypass = False
                try:
                    sig_score = float(best_signal.get("score", 0) or 0)
                    if sig_score >= 75:
                        cvd_total = okx_ws_public_service.get_cvd_score(symbol)
                        cvd_15m = okx_ws_public_service.get_cvd_score_time(symbol, 900)
                        cvd_exhausted = cvd_total > 80000 and cvd_15m < 20000
                        zones = await signal_generator.get_15m_zones(symbol)
                        near_resistance = zones.get("near_zone", False) and zones.get("resistance", 0) > 0
                        if cvd_exhausted or near_resistance:
                            bypass = True
                            best_signal["is_mean_reversion"] = True
                            best_signal["macro_bypass_reason"] = "CVD_EXHAUSTION" if cvd_exhausted else "RESISTANCE_REJECTION"
                            logger.info(f"🔓 [V112.12 MACRO-BYPASS] {symbol} SHORT liberado. Score={sig_score:.0f}")
                except Exception as be:
                    logger.warning(f"[V112.12 MACRO-BYPASS] Erro {symbol}: {be}")
                if not bypass:
                    logger.warning(f"🚫 [CAPTAIN-MACRO-BLOCK] {symbol} {strategy_class} SHORT rejeitado. Macro BULLISH sem bypass.")
                    return
        else:
            logger.info(f"🔓 [CAPTAIN-MACRO-PASS] {symbol} {strategy_class} {side} liberado (D.S={is_decor_shadow}, Regime={current_regime}).")'''

if old_macro_filter in content:
    content = content.replace(old_macro_filter, new_macro_filter)
    changes_made += 1
    print("[OK] CHANGE 2: MACRO_BYPASS aplicado")
else:
    print("[FAIL] CHANGE 2: MACRO_BYPASS nao encontrado")

# ============================================================
# CHANGE 3: _run_user_execution_logic - DECOR em TRENDING
# ============================================================
old_decor_trending = '''                else:
                    # Em mercado em TENDÊNCIA, apenas VELOCITY FLOW e ALPHA SHIELD são permitidas
                    if strategy in ("DECOR SHADOW", "DECOR_HUNTER"):
                        msg = f"[TREND_FOCUS] {symbol} ({strategy}) bloqueado em mercado em TENDÊNCIA (ADX >= 25)."
                        logger.info(msg)
                        await firebase_service.update_signal_outcome(best_signal.get("id"), "TREND_FOCUS_TRENDING_BLOCK")
                        self.active_tocaias.discard(symbol)
                        return'''

new_decor_trending = '''                else:
                    # Em mercado em TENDÊNCIA, VELOCITY FLOW e ALPHA SHIELD são prioritárias
                    # [V112.12] DECOR_HUNTER/DECOR SHADOW permitidos se descolados do BTC
                    if strategy in ("DECOR SHADOW", "DECOR_HUNTER"):
                        if best_signal.get("btc_correlation", 1.0) < 0.5 or best_signal.get("is_decorrelated", False):
                            logger.info(f"🔓 [V112.12 DECOR-TREND] {symbol} ({strategy}) liberado em tendência (corr baixa).")
                        else:
                            msg = f"[TREND_FOCUS] {symbol} ({strategy}) bloqueado em TENDÊNCIA (corr alta)."
                            logger.info(msg)
                            await firebase_service.update_signal_outcome(best_signal.get("id"), "TREND_FOCUS_TRENDING_BLOCK")
                            self.active_tocaias.discard(symbol)
                            return'''

if old_decor_trending in content:
    content = content.replace(old_decor_trending, new_decor_trending)
    changes_made += 1
    print("[OK] CHANGE 3: DECOR em TRENDING (run_user_execution) aplicado")
else:
    print("[FAIL] CHANGE 3: DECOR em TRENDING nao encontrado")

# ============================================================
# Save
# ============================================================
if changes_made > 0:
    with open(CAPTAIN_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n[OK] {changes_made} alteracoes aplicadas em {CAPTAIN_PATH}")
else:
    print("\n[FAIL] Nenhuma alteracao foi aplicada!")
