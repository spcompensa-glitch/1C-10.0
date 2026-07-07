import asyncio
import sys
sys.path.append("backend")

print("Checking imports...")
try:
    from services.sandbox_service import SandboxService
    print("SandboxService imported successfully!")
except Exception as e:
    print("Error importing SandboxService:", e)
    sys.exit(1)

print("All imports OK!")
