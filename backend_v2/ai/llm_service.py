"""
Backend V2 — Ollama LLM Service

Thin wrapper around the Ollama /api/generate endpoint.
Never interprets or queries data — it only generates natural language.
All data must already be in the prompt before calling this service.
"""
import logging
import requests

logger = logging.getLogger(__name__)


class LLMService:

    def __init__(
        self,
        ollama_url: str,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        timeout_sec: int = 60,
    ):
        self.ollama_url = ollama_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout_sec = timeout_sec

    def generate(self, prompt: str) -> str:
        """
        Sends a prompt to Ollama and returns the generated text.
        Returns a safe fallback message on any error.
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
        try:
            resp = requests.post(
                self.ollama_url,
                json=payload,
                timeout=self.timeout_sec,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("response", "").strip()
            if not text:
                return "I was unable to generate a response. Please try again."
            return text
        except requests.exceptions.Timeout:
            logger.warning(f"Ollama request timed out after {self.timeout_sec}s.")
            return "⚠️ The AI model is taking too long to respond. Please try again."
        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to Ollama. Is it running?")
            return "⚠️ AI model is offline. Please ensure Ollama is running and try again."
        except Exception as e:
            logger.error(f"LLM generation error: {e}", exc_info=True)
            return "⚠️ An error occurred while generating the response. Please try again."

    def is_available(self) -> bool:
        """Checks if Ollama is reachable."""
        try:
            base = self.ollama_url.replace("/api/generate", "")
            r = requests.get(f"{base}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False
