import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

if not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "replace-me":
    raise SystemExit("OPENAI_API_KEY is required.")

from langchain_openai import ChatOpenAI

reply = ChatOpenAI(model=os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-mini-2026-03-17")).invoke("Reply with READY only.")
print("Model preflight:", reply.content)
print("LangSmith tracing:", os.getenv("LANGSMITH_TRACING", "false"))
