import sys
sys.path.append("backend")
from backend.config import settings

print("EXECUTION_MODE:", settings.OKX_EXECUTION_MODE)
print("API_KEY_MASTER:", settings.OKX_API_KEY_MASTER)
print("IS NOT PAPER:", settings.OKX_EXECUTION_MODE != "PAPER")
