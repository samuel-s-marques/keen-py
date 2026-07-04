"""LLM provider adapters for the Thinking Partner engine.

Each provider implements a common interface — ``build_request`` returns the
``(url, headers, payload)`` for a chat completion, and ``parse_response``
extracts the assistant text from the decoded JSON. New providers are added by
defining an adapter and registering it in ``PROVIDERS`` — no edits to the engine.
"""

from typing import Any


class LLMProvider:
    """Base adapter. Subclasses implement request-building and response-parsing."""

    name = "base"

    def build_request(
        self,
        model: str,
        api_key: str,
        base_url: str,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, dict, dict]:
        raise NotImplementedError

    def parse_response(self, data: dict) -> str:
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    name = "openai"

    def build_request(self, model, api_key, base_url, system_prompt, user_prompt):
        url = "https://api.openai.com/v1/chat/completions"
        if base_url:
            url = base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        return url, headers, payload

    def parse_response(self, data: dict) -> str:
        return data["choices"][0]["message"]["content"]


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def build_request(self, model, api_key, base_url, system_prompt, user_prompt):
        url = "https://api.anthropic.com/v1/messages"
        if base_url:
            url = base_url.rstrip("/") + "/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0.2,
        }
        return url, headers, payload

    def parse_response(self, data: dict) -> str:
        return data["content"][0]["text"]


class OpenAICompatibleProvider(LLMProvider):
    """Generic local/custom provider (Ollama, LM Studio, KoboldCpp, ...).

    Most speak the OpenAI chat-completions format. Used as the default fallback
    for any unrecognized provider name.
    """

    name = "openai-compatible"

    def build_request(self, model, api_key, base_url, system_prompt, user_prompt):
        url = "http://localhost:1234/v1/chat/completions"  # Default LM Studio
        if base_url:
            url = base_url.rstrip("/")
            if "/v1" not in url:
                url = url + "/v1"
            if not url.endswith("/chat/completions"):
                url = url + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        return url, headers, payload

    def parse_response(self, data: dict) -> str:
        return data["choices"][0]["message"]["content"]


# Registry of named providers; anything else falls back to the OpenAI-compatible
# adapter (preserving the previous if/elif "else" behavior).
PROVIDERS: dict[str, LLMProvider] = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
}
_DEFAULT_PROVIDER = OpenAICompatibleProvider()


def get_provider(name: Any) -> LLMProvider:
    """Return the adapter for ``name`` (case-insensitive), or the default."""
    return PROVIDERS.get(str(name or "").lower(), _DEFAULT_PROVIDER)
