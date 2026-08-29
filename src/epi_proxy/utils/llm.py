"""Unified LLM client abstraction for cloud and local inference."""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic
from google import genai
from openai import AsyncOpenAI, OpenAI

from epi_proxy.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_DISCOVERY_MODEL,
    CLAUDE_PARSING_MODEL,
    CLAUDE_VALIDATION_MODEL,
    CLAUDE_VERIFICATION_MODEL,
    GEMINI_API_KEY,
    GEMINI_DEEP_RESEARCH_AGENT,
    LOCAL_DISCOVERY_MODEL,
    LOCAL_INFERENCE_URL,
    LOCAL_MODEL_NAME,
    LOCAL_PARSING_MODEL,
    LOCAL_RESEARCH_MODEL,
    LOCAL_VALIDATION_MODEL,
    LOCAL_VERIFICATION_MODEL,
    OPENAI_API_KEY,
    USE_LOCAL_INFERENCE,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    text: str | None = None
    tool_uses: list[ToolUseBlock] = field(default_factory=list)
    stop_reason: str = "end_turn"
    _raw_assistant_content: Any = None  # provider-specific content for building follow-up messages


class LLMClient:
    """Orchestrates calls to different LLM providers (Anthropic, Google, Local)."""

    def __init__(self, trace_dir: Optional[Path] = None):
        self.use_local = USE_LOCAL_INFERENCE
        self.trace_dir = trace_dir
        if self.trace_dir:
            self.trace_dir.mkdir(parents=True, exist_ok=True)

        # Local / OpenAI-compatible client (only when needed)
        self.openai_client = None
        self.openai_async_client = None
        if self.use_local or OPENAI_API_KEY:
            base_url = LOCAL_INFERENCE_URL if self.use_local else None
            api_key = "local" if self.use_local else OPENAI_API_KEY
            self.openai_client = OpenAI(base_url=base_url, api_key=api_key)
            self.openai_async_client = AsyncOpenAI(base_url=base_url, api_key=api_key)

        # Anthropic client (only when key is available)
        self.anthropic_client = None
        self.anthropic_async_client = None
        if ANTHROPIC_API_KEY:
            self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            self.anthropic_async_client = anthropic.AsyncAnthropic(
                api_key=ANTHROPIC_API_KEY
            )

        # Google client (lazy — only created when needed)
        self._google_client = None

        logger.info(
            "LLMClient initialized: mode=%s trace_dir=%s local_url=%s anthropic=%s openai=%s",
            "local" if self.use_local else "cloud",
            str(self.trace_dir or "N/A"),
            LOCAL_INFERENCE_URL if self.use_local else "N/A",
            self.anthropic_client is not None,
            self.openai_client is not None,
        )

    @property
    def google_client(self):
        if self._google_client is None:
            self._google_client = genai.Client(api_key=GEMINI_API_KEY)
        return self._google_client

    def _get_model(self, requested_model: str) -> str:
        """Map cloud model name to local model override if local inference is enabled."""
        if not self.use_local:
            logger.debug("Model resolution: %s → %s (cloud mode)", requested_model, requested_model)
            return requested_model

        mapping = {
            GEMINI_DEEP_RESEARCH_AGENT: LOCAL_RESEARCH_MODEL,
            CLAUDE_PARSING_MODEL: LOCAL_PARSING_MODEL,
            CLAUDE_DISCOVERY_MODEL: LOCAL_DISCOVERY_MODEL,
            CLAUDE_VERIFICATION_MODEL: LOCAL_VERIFICATION_MODEL,
            CLAUDE_VALIDATION_MODEL: LOCAL_VALIDATION_MODEL,
        }

        resolved = mapping.get(requested_model, LOCAL_MODEL_NAME)
        logger.info(
            "Model resolution: %s → %s (local mode, fallback=%s)",
            requested_model, resolved, LOCAL_MODEL_NAME,
        )
        return resolved

    @staticmethod
    def _convert_tools_to_openai(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """Convert Anthropic-format tools to OpenAI-format tools for local inference.

        Anthropic format:  {"name": ..., "description": ..., "input_schema": {...}}
        OpenAI format:     {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}

        Idempotent: tools already in OpenAI format (with "type": "function") are passed through.
        """
        if not tools:
            return tools
        converted = []
        for tool in tools:
            if tool.get("type") == "function":
                converted.append(tool)
            else:
                converted.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {}),
                    },
                })
        return converted

    def _log_trace(
        self,
        call_type: str,
        model: str,
        provider: str,
        request: Dict[str, Any],
        response: Dict[str, Any],
        duration_ms: float,
        error: Optional[Exception] = None,
    ) -> None:
        """Write a JSONL trace entry for a single LLM interaction."""
        if not self.trace_dir:
            return
        trace: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "call_type": call_type,
            "model": model,
            "provider": provider,
            "request": request,
            "response": response,
            "duration_ms": round(duration_ms, 1),
        }
        if error:
            trace["error"] = str(error)
        trace_path = self.trace_dir / "llm_traces.jsonl"
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace, default=str, ensure_ascii=False) + "\n")

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        **kwargs,
    ) -> str:
        """Asynchronous chat completion."""
        actual_model = self._get_model(model)
        t0 = time.monotonic()
        request_info: Dict[str, Any] = {
            "messages": messages, "system": system, "max_tokens": max_tokens,
        }
        provider = None
        content = None

        try:
            if self.use_local:
                provider = "local"
                logger.info(
                    "Chat completion: provider=local model=%s max_tokens=%d messages=%d",
                    actual_model, max_tokens, len(messages),
                )
                combined_messages = messages
                if system:
                    combined_messages = [{"role": "system", "content": system}] + messages
                response = await self.openai_async_client.chat.completions.create(
                    model=actual_model, messages=combined_messages, max_tokens=max_tokens, **kwargs,
                )
                content = response.choices[0].message.content

            elif model.startswith("claude"):
                if self.anthropic_async_client is None:
                    raise ValueError(
                        "ANTHROPIC_API_KEY not set and USE_LOCAL_INFERENCE is false. "
                        "Set one of these to use Claude models."
                    )
                provider = "anthropic"
                logger.info(
                    "Chat completion: provider=anthropic model=%s max_tokens=%d",
                    actual_model, max_tokens,
                )
                response = await self.anthropic_async_client.messages.create(
                    model=actual_model, messages=messages, system=system or "", max_tokens=max_tokens, **kwargs,
                )
                content = response.content[0].text

            elif self.openai_async_client is not None:
                provider = "openai"
                logger.info(
                    "Chat completion: provider=openai model=%s max_tokens=%d",
                    actual_model, max_tokens,
                )
                combined_messages = messages
                if system:
                    combined_messages = [{"role": "system", "content": system}] + messages
                response = await self.openai_async_client.chat.completions.create(
                    model=actual_model, messages=combined_messages, max_tokens=max_tokens, **kwargs,
                )
                content = response.choices[0].message.content

            else:
                raise ValueError(f"No configuration found for model: {model}")

            duration = (time.monotonic() - t0) * 1000
            self._log_trace("chat_completion", actual_model, provider, request_info, {"text": content}, duration)
            return content

        except Exception as e:
            duration = (time.monotonic() - t0) * 1000
            self._log_trace("chat_completion", actual_model, provider or "unknown", request_info, {"error": str(e)}, duration, error=e)
            raise

    def chat_completion_sync(
        self,
        model: str,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        **kwargs,
    ) -> str:
        """Synchronous chat completion."""
        actual_model = self._get_model(model)
        t0 = time.monotonic()
        request_info: Dict[str, Any] = {
            "messages": messages, "system": system, "max_tokens": max_tokens,
        }
        provider = None
        content = None

        try:
            if self.use_local:
                provider = "local"
                logger.info(
                    "Chat completion (sync): provider=local model=%s max_tokens=%d",
                    actual_model, max_tokens,
                )
                combined_messages = messages
                if system:
                    combined_messages = [{"role": "system", "content": system}] + messages
                response = self.openai_client.chat.completions.create(
                    model=actual_model, messages=combined_messages, max_tokens=max_tokens, **kwargs,
                )
                content = response.choices[0].message.content

            elif model.startswith("claude"):
                if self.anthropic_client is None:
                    raise ValueError(
                        "ANTHROPIC_API_KEY not set and USE_LOCAL_INFERENCE is false. "
                        "Set one of these to use Claude models."
                    )
                provider = "anthropic"
                logger.info(
                    "Chat completion (sync): provider=anthropic model=%s max_tokens=%d",
                    actual_model, max_tokens,
                )
                response = self.anthropic_client.messages.create(
                    model=actual_model, messages=messages, system=system or "", max_tokens=max_tokens, **kwargs,
                )
                content = response.content[0].text

            elif self.openai_client is not None:
                provider = "openai"
                logger.info(
                    "Chat completion (sync): provider=openai model=%s max_tokens=%d",
                    actual_model, max_tokens,
                )
                combined_messages = messages
                if system:
                    combined_messages = [{"role": "system", "content": system}] + messages
                response = self.openai_client.chat.completions.create(
                    model=actual_model, messages=combined_messages, max_tokens=max_tokens, **kwargs,
                )
                content = response.choices[0].message.content

            else:
                raise ValueError(f"No configuration found for model: {model}")

            duration = (time.monotonic() - t0) * 1000
            self._log_trace("chat_completion_sync", actual_model, provider, request_info, {"text": content}, duration)
            return content

        except Exception as e:
            duration = (time.monotonic() - t0) * 1000
            self._log_trace("chat_completion_sync", actual_model, provider or "unknown", request_info, {"error": str(e)}, duration, error=e)
            raise

    def run_deep_research(self, prompt: str, model: str) -> Any:
        """Run deep research (Gemini only for now)."""
        if self.use_local:
            logger.warning(
                "Local inference requested for Deep Research. Falling back to standard completion."
            )
            # For now, just do a normal completion if local is requested for research
            return self.chat_completion_sync(
                model=LOCAL_MODEL_NAME, messages=[{"role": "user", "content": prompt}]
            )

        # Gemini deep research — trace submission but response comes via polling
        t0 = time.monotonic()
        request_info: Dict[str, Any] = {"prompt": prompt, "agent": model}
        try:
            interaction = self.google_client.interactions.create(
                input=prompt,
                agent=model,
                background=True,
            )
            interaction_id = getattr(interaction, "name", str(interaction))
            duration = (time.monotonic() - t0) * 1000
            self._log_trace("deep_research", model, "gemini", request_info, {"interaction_id": interaction_id}, duration)
            return interaction
        except Exception as e:
            duration = (time.monotonic() - t0) * 1000
            self._log_trace("deep_research", model, "gemini", request_info, {"error": str(e)}, duration, error=e)
            raise

    def get_research_interaction(self, interaction_id: str) -> Any:
        """Get research interaction status (Gemini only)."""
        return self.google_client.interactions.get(interaction_id)

    async def chat_with_tools(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 8192,
        **kwargs,
    ) -> LLMResponse:
        """Chat completion with tool-calling support (async).

        Returns a unified LLMResponse regardless of provider.
        """
        actual_model = self._get_model(model)
        t0 = time.monotonic()
        request_info: Dict[str, Any] = {
            "messages": messages, "system": system, "tools": tools, "max_tokens": max_tokens,
        }
        provider = None
        result = None

        try:
            if self.use_local:
                provider = "local"
                logger.info(
                    "Chat with tools: provider=local model=%s tools=%d messages=%d",
                    actual_model, len(tools) if tools else 0, len(messages),
                )
                combined_messages = messages
                if system:
                    combined_messages = [{"role": "system", "content": system}] + messages

                openai_tools = self._convert_tools_to_openai(tools)
                response = await self.openai_async_client.chat.completions.create(
                    model=actual_model,
                    messages=combined_messages,
                    tools=openai_tools,
                    max_tokens=max_tokens,
                    **kwargs,
                )

                msg = response.choices[0].message
                tool_uses = []
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments)
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                        tool_uses.append(ToolUseBlock(
                            id=tc.id,
                            name=tc.function.name,
                            input=args,
                        ))

                stop_reason_map = {
                    "stop": "end_turn",
                    "tool_calls": "tool_use",
                    "length": "max_tokens",
                }
                result = LLMResponse(
                    text=msg.content or "",
                    tool_uses=tool_uses,
                    stop_reason=stop_reason_map.get(
                        response.choices[0].finish_reason, "end_turn"
                    ),
                )
                result._raw_assistant_content = msg

            else:
                # Anthropic
                if self.anthropic_async_client is None:
                    raise ValueError(
                        "ANTHROPIC_API_KEY not set and USE_LOCAL_INFERENCE is false. "
                        "Set one of these to use Claude models."
                    )
                provider = "anthropic"
                logger.info(
                    "Chat with tools: provider=anthropic model=%s tools=%d messages=%d",
                    actual_model, len(tools) if tools else 0, len(messages),
                )
                response = await self.anthropic_async_client.messages.create(
                    model=actual_model,
                    messages=messages,
                    system=system or "",
                    tools=tools,
                    max_tokens=max_tokens,
                    **kwargs,
                )

                text = ""
                tool_uses = []
                for block in response.content:
                    if block.type == "text":
                        text += block.text
                    elif block.type == "tool_use":
                        tool_uses.append(ToolUseBlock(
                            id=block.id,
                            name=block.name,
                            input=block.input,
                        ))

                result = LLMResponse(
                    text=text,
                    tool_uses=tool_uses,
                    stop_reason=response.stop_reason,
                )
                result._raw_assistant_content = response.content

            duration = (time.monotonic() - t0) * 1000
            self._log_trace(
                "chat_with_tools", actual_model, provider, request_info,
                {
                    "text": result.text,
                    "tool_uses": [{"name": tu.name, "input": tu.input} for tu in result.tool_uses],
                    "stop_reason": result.stop_reason,
                },
                duration,
            )
            return result

        except Exception as e:
            duration = (time.monotonic() - t0) * 1000
            self._log_trace("chat_with_tools", actual_model, provider or "unknown", request_info, {"error": str(e)}, duration, error=e)
            raise

    def build_assistant_message(self, response: LLMResponse) -> Dict[str, Any]:
        """Build the assistant message dict to append to the conversation.

        Provider-agnostic: returns the correct format for the current backend.
        """
        if self.use_local:
            msg = {"role": "assistant", "content": response.text or ""}
            if response.tool_uses:
                msg["tool_calls"] = [
                    {
                        "id": tu.id,
                        "type": "function",
                        "function": {
                            "name": tu.name,
                            "arguments": json.dumps(tu.input),
                        },
                    }
                    for tu in response.tool_uses
                ]
            return msg
        return {"role": "assistant", "content": response._raw_assistant_content}

    def build_tool_result_messages(
        self, results: List[tuple[str, str, str]]
    ) -> List[Dict[str, Any]]:
        """Build tool result message(s) to append to the conversation.

        Args:
            results: List of (tool_use_id, tool_name, result_content) tuples.

        Returns:
            List of message dicts to append.
        """
        if self.use_local:
            return [
                {"role": "tool", "tool_call_id": tid, "content": content}
                for tid, _name, content in results
            ]
        return [{
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": content}
                for tid, _name, content in results
            ],
        }]
