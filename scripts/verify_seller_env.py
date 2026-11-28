"""
Verify that seller environment variables are loaded correctly.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load from repo root (same as sellers do)
repo_root = Path(__file__).resolve().parents[1]
env_path = repo_root / ".env"

print(f"Loading environment from: {env_path}")
print(f"File exists: {env_path.exists()}")
print()

load_dotenv(dotenv_path=env_path)

# Check all relevant environment variables
env_vars = [
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_MODEL",
    "GEMINI_MODEL",
    "MUHR_SELLER_KEY",
    "MUHR_SELLER_ISOLATION",
    "MUHR_REGISTRY_BASE_URL",
    "DEMO_MODE",
]

print("Environment Variables:")
print("-" * 60)
for var in env_vars:
    value = os.getenv(var, "")
    if value:
        # Mask API keys for security
        if "API_KEY" in var or var.endswith("_KEY"):
            masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            print(f"{var}: {masked}")
        else:
            print(f"{var}: {value}")
    else:
        print(f"{var}: (not set)")

print("-" * 60)
print()

# Check if LLM rotation will work
groq_key = os.getenv("GROQ_API_KEY", "").strip()
gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

print("LLM Rotation Status:")
print(f"  Groq configured: {bool(groq_key)}")
print(f"  Gemini configured: {bool(gemini_key)}")
print(f"  Will use: {'hosted LLM (input leaves this machine)' if (groq_key or gemini_key) else 'offline extractive pipeline'}")
