"""
Fixes minor issues found in code review for V112.12.
"""
import re

# Fix 1: Signal generator - remove unused volumes variable
SG_PATH = "backend/services/signal_generator.py"
with open(SG_PATH, "r", encoding="utf-8") as f:
    sg_content = f.read()

old_volumes = "            volumes = [float(c[5]) for c in candles]\n            current_price = closes[-1]"
new_volumes = "            current_price = closes[-1]"

if old_volumes in sg_content:
    sg_content = sg_content.replace(old_volumes, new_volumes)
    with open(SG_PATH, "w", encoding="utf-8") as f:
        f.write(sg_content)
    print("[OK] Fix 1: Removed unused volumes variable")
else:
    print("[FAIL] Fix 1: volumes variable not found in expected context")

# Fix 2: Captain - bare except in DECOR regime gate
CAP_PATH = "backend/services/agents/captain.py"
with open(CAP_PATH, "r", encoding="utf-8") as f:
    cap_content = f.read()

old_except = """                except:
                    logger.warning(f\"🚫 [CAPTAIN-REGIME-BLOCK] {symbol} DECOR SHADOW rejeitado em TENDÊNCIA (erro decorr).\")
                    return"""

new_except = """                except Exception as decor_err:
                    logger.warning(f\"🚫 [CAPTAIN-REGIME-BLOCK] {symbol} DECOR SHADOW rejeitado em TENDÊNCIA (erro: {decor_err}).\")
                    return"""

if old_except in cap_content:
    cap_content = cap_content.replace(old_except, new_except)
    with open(CAP_PATH, "w", encoding="utf-8") as f:
        f.write(cap_content)
    print("[OK] Fix 2: Bare except replaced with logged exception")
else:
    print("[FAIL] Fix 2: Bare except pattern not found")
