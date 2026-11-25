"""The only module allowed to call a language model.

The rest of the app talks to the model through one small interface:

    reply = client.chat(messages, tools)   # -> ModelReply(content, tool_calls)

Messages and tools use a provider-neutral format. Each provider (Ollama now,
the Claude API later) gets an adapter class that translates to and from its
own HTTP format, so switching provider never touches the agent code.

Configuration comes from environment variables (see .env.example):
    MODEL_PROVIDER  "ollama" (default)
    OLLAMA_MODEL    default "qwen2.5:3b" (text + tools)
    OLLAMA_VISION_MODEL default "qwen3-vl:2b-instruct" (receipt photos)
    OLLAMA_URL      default "http://localhost:11434"
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, List, Optional


class ModelUnavailable(Exception):
    """The model server could not be reached or returned an unusable answer."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ModelReply:
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)


def _http_post_json(url: str, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class OllamaClient:
    """Adapter for a local Ollama server (https://ollama.com)."""

    def __init__(
        self,
        model: Optional[str] = None,
        url: Optional[str] = None,
        timeout: float = 180,
        post: Callable[[str, dict, float], dict] = _http_post_json,
        vision_model: Optional[str] = None,
    ):
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
        self.vision_model = vision_model or os.environ.get("OLLAMA_VISION_MODEL", "qwen3-vl:2b-instruct")
        self.url = (url or os.environ.get("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.timeout = timeout
        self._post = post  # replaced by a fake in tests

    def chat(self, messages: List[dict], tools: List[dict]) -> ModelReply:
        payload = {
            "model": self.model,
            "messages": [self._to_ollama(m) for m in messages],
            "tools": [{"type": "function", "function": t} for t in tools],
            "stream": False,
            "options": {"temperature": 0.2},  # low = more predictable answers
            "keep_alive": "30m",  # keep the model in memory between questions
        }
        try:
            data = self._post(f"{self.url}/api/chat", payload, self.timeout)
        except (OSError, urllib.error.URLError, ValueError) as error:
            raise ModelUnavailable(f"Cannot reach Ollama at {self.url}: {error}") from error

        message = data.get("message") or {}
        calls = []
        for i, call in enumerate(message.get("tool_calls") or []):
            function = call.get("function", {})
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):  # some models send JSON as a string
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {}
            calls.append(ToolCall(id=f"call_{i}", name=function.get("name", ""), arguments=arguments))
        return ModelReply(content=(message.get("content") or "").strip(), tool_calls=calls)

    def read_image(self, prompt: str, image_base64: str, schema: dict) -> dict:
        """Ask the vision model about one image; the answer is forced into `schema` (JSON).

        Returns the parsed JSON, or {} if the model's answer is not valid JSON.
        """
        payload = {
            "model": self.vision_model,
            "messages": [{"role": "user", "content": prompt, "images": [image_base64]}],
            "format": schema,  # structured output: Ollama constrains the answer to this JSON shape
            "stream": False,
            "options": {"temperature": 0},
            "keep_alive": "30m",
        }
        try:
            data = self._post(f"{self.url}/api/chat", payload, self.timeout)
        except (OSError, urllib.error.URLError, ValueError) as error:
            raise ModelUnavailable(f"Cannot reach Ollama at {self.url}: {error}") from error
        try:
            parsed = json.loads((data.get("message") or {}).get("content") or "")
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _to_ollama(message: dict) -> dict:
        role = message["role"]
        if role == "tool":
            return {"role": "tool", "tool_name": message["name"], "content": message["content"]}
        converted = {"role": role, "content": message.get("content", "")}
        if message.get("tool_calls"):
            converted["tool_calls"] = [
                {"function": {"name": c.name, "arguments": c.arguments}} for c in message["tool_calls"]
            ]
        return converted


def get_model_client():
    """Build the client chosen by MODEL_PROVIDER. Add a ClaudeClient here later."""
    provider = os.environ.get("MODEL_PROVIDER", "ollama")
    if provider == "ollama":
        return OllamaClient()
    raise ValueError(f"Unknown MODEL_PROVIDER {provider!r}")
