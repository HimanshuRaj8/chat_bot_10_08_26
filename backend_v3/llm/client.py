"""
Backend V3 — Ollama LLM Client
"""
import logging
from typing import Optional
import requests

logger = logging.getLogger(__name__)


class LLMClient:

    def __init__(
        self,
        ollama_url: str,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.1,
        timeout_sec: int = 60,
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout_sec = timeout_sec

    def generate(self, prompt: str, system: Optional[str] = None, format_json: bool = False) -> str:
        """
        Sends a prompt to Ollama and returns the generated text response.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": self.max_tokens,
                "temperature": self.temperature,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
            },
        }
        if system:
            payload["system"] = system
        if format_json:
            payload["format"] = "json"

        try:
            resp = requests.post(
                self.ollama_url,
                json=payload,
                timeout=self.timeout_sec,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()
        except requests.exceptions.Timeout:
            logger.warning(f"Ollama request timed out after {self.timeout_sec}s.")
            raise TimeoutError("Ollama connection timed out.")
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            raise ConnectionError(f"Ollama generation failed: {e}")

    def is_available(self) -> bool:
        """Checks if local Ollama server is running and reachable."""
        try:
            base = self.ollama_url.replace("/api/generate", "")
            r = requests.get(f"{base}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False
