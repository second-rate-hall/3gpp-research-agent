from __future__ import annotations

import json
import os
import ssl
import time
import urllib.request
from urllib.error import HTTPError, URLError


DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "deepseek-ai/deepseek-v4-flash"


class NvidiaClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY", "")
        self.base_url = (base_url or os.getenv("NVIDIA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.getenv("NVIDIA_MODEL") or DEFAULT_MODEL
        if not self.api_key:
            raise RuntimeError("NVIDIA_API_KEY is not set. Export it or create a local .env loader before running ask.")

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 1800,
        retries: int = 5,
        timeout: int = 300,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                message = body["choices"][0]["message"]
                return message.get("content") or message.get("reasoning_content") or json.dumps(message, ensure_ascii=False)
            except HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"NVIDIA API HTTP {exc.code}: {details}") from exc
            except (URLError, TimeoutError, OSError, ssl.SSLError) as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(min(20, 2 * attempt))
                    continue
        raise RuntimeError(f"NVIDIA API request failed after {retries} attempts: {last_error}") from last_error


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
