import json
from types import SimpleNamespace

import anthropic

from config.logger import setup_logging
from core.providers.llm.base import LLMProviderBase

TAG = __name__
logger = setup_logging()

# The server lets OpenAI-style models answer through a `direct_answer` tool.
# Claude answers in plain text instead, so that tool is never offered and any
# direct_answer calls in the history (e.g. few-shot examples) become text.
DIRECT_ANSWER = "direct_answer"


class LLMProvider(LLMProviderBase):
    """Claude via the official Anthropic SDK, with tool use for `Intent: function_call`.

    Config keys: model_name, max_tokens, effort, thinking ("adaptive" or
    "disabled"), fallbacks (e.g. "default"; omit for models without
    server-side fallback such as Claude Haiku 5.5), api_key (empty: the SDK
    reads ANTHROPIC_API_KEY).
    """

    def __init__(self, config):
        self.model_name = config.get("model_name") or "claude-opus-5-5"
        self.max_tokens = int(config.get("max_tokens") or 2048)
        self.effort = config.get("effort") or "low"
        self.thinking = config.get("thinking") or "adaptive"
        self.fallbacks = config.get("fallbacks") or None
        # Kept as a string: the server's key checks do `"..." in llm.api_key`.
        self.api_key = config.get("api_key") or ""
        self.client = anthropic.Anthropic(api_key=self.api_key or None)

    # ---------- dialogue conversion ----------

    @staticmethod
    def _to_messages(dialogue):
        """Turn the server's OpenAI-style dialogue into (system, messages).

        Assistant tool_calls become tool_use blocks and role=tool entries become
        tool_result blocks; unpaired tool blocks are dropped, same-role turns are
        merged, and the list starts and ends with a user turn.
        """
        system_parts = []
        messages = []
        skipped_ids = set()

        for msg in dialogue:
            role = msg.get("role")
            content = msg.get("content") or ""
            if not isinstance(content, str):
                content = str(content)

            if role == "system":
                if content:
                    system_parts.append(content)
            elif role == "user":
                if content:
                    messages.append({"role": "user", "content": [{"type": "text", "text": content}]})
            elif role == "assistant":
                blocks = [{"type": "text", "text": content}] if content else []
                for call in msg.get("tool_calls") or []:
                    fn = call.get("function") or {}
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if not isinstance(args, dict):
                        args = {}
                    if fn.get("name") == DIRECT_ANSWER:
                        skipped_ids.add(call.get("id"))
                        if args.get("response"):
                            blocks.append({"type": "text", "text": str(args["response"])})
                        continue
                    blocks.append({
                        "type": "tool_use",
                        "id": call.get("id"),
                        "name": fn.get("name"),
                        "input": args,
                    })
                if blocks:
                    messages.append({"role": "assistant", "content": blocks})
            elif role == "tool":
                call_id = msg.get("tool_call_id")
                if call_id in skipped_ids:
                    continue
                messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": call_id, "content": content or "ok"}],
                })

        messages = LLMProvider._pair_tool_blocks(LLMProvider._merge(messages))
        while messages and messages[0]["role"] != "user":
            messages.pop(0)
        while messages and messages[-1]["role"] != "user":
            messages.pop()  # no assistant prefill
        return "\n\n".join(system_parts), messages

    @staticmethod
    def _merge(messages):
        merged = []
        for msg in messages:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["content"].extend(msg["content"])
            else:
                merged.append({"role": msg["role"], "content": list(msg["content"])})
        for msg in merged:
            if msg["role"] == "user":
                # tool_result blocks must lead the user turn
                msg["content"].sort(key=lambda b: b["type"] != "tool_result")
        return merged

    @staticmethod
    def _pair_tool_blocks(messages):
        """Keep tool_use only when the next turn answers it, and vice versa."""
        for i, msg in enumerate(messages):
            if msg["role"] != "assistant":
                continue
            nxt = messages[i + 1] if i + 1 < len(messages) else None
            answered = {
                b["tool_use_id"] for b in (nxt["content"] if nxt else []) if b["type"] == "tool_result"
            }
            msg["content"] = [
                b for b in msg["content"] if b["type"] != "tool_use" or b["id"] in answered
            ]
        for i, msg in enumerate(messages):
            if msg["role"] != "user":
                continue
            prev = messages[i - 1] if i > 0 else None
            asked = {
                b["id"] for b in (prev["content"] if prev and prev["role"] == "assistant" else [])
                if b["type"] == "tool_use"
            }
            msg["content"] = [
                b for b in msg["content"] if b["type"] != "tool_result" or b["tool_use_id"] in asked
            ]
        return LLMProvider._merge([m for m in messages if m["content"]])

    @staticmethod
    def _to_tools(functions):
        tools = []
        for f in functions or []:
            fn = f.get("function") or {}
            if not fn.get("name") or fn["name"] == DIRECT_ANSWER:
                continue
            tools.append({
                "name": fn["name"],
                "description": fn.get("description") or "",
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })
        return tools

    # ---------- requests ----------

    def _stream(self, system, messages, tools=None):
        params = {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "messages": messages,
            "output_config": {"effort": self.effort},
            "thinking": {"type": self.thinking},
        }
        if system:
            params["system"] = system
        if tools:
            params["tools"] = tools
        if self.fallbacks:
            # On a policy decline the API retries on a suitable model in the same call.
            return self.client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"], fallbacks=self.fallbacks, **params
            )
        return self.client.messages.stream(**params)

    def _log_final(self, final):
        if final.stop_reason == "refusal":
            logger.bind(tag=TAG).warning(f"Claude declined the request: {final.stop_details}")
        usage = final.usage
        logger.bind(tag=TAG).info(
            f"Claude {final.model}: in {usage.input_tokens}, out {usage.output_tokens}, stop {final.stop_reason}"
        )

    def response(self, session_id, dialogue, **kwargs):
        system, messages = self._to_messages(dialogue)
        if not messages:
            return
        with self._stream(system, messages) as stream:
            for text in stream.text_stream:
                if text:
                    yield text
            final = stream.get_final_message()
        self._log_final(final)

    def response_with_functions(self, session_id, dialogue, functions=None, **kwargs):
        """Yields (text, tool_calls) like the OpenAI provider.

        tool_calls are objects with index/id/function.name/function.arguments,
        the shape the server's _merge_tool_calls expects.
        """
        system, messages = self._to_messages(dialogue)
        if not messages:
            return
        tools = self._to_tools(functions)
        tool_index = {}  # content-block index -> tool-call index

        with self._stream(system, messages, tools) as stream:
            for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "tool_use":
                    idx = tool_index.setdefault(event.index, len(tool_index))
                    block = event.content_block
                    yield None, [SimpleNamespace(
                        index=idx, id=block.id,
                        function=SimpleNamespace(name=block.name, arguments=""),
                    )]
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta" and delta.text:
                        yield delta.text, None
                    elif delta.type == "input_json_delta" and delta.partial_json:
                        yield None, [SimpleNamespace(
                            index=tool_index[event.index], id=None,
                            function=SimpleNamespace(name=None, arguments=delta.partial_json),
                        )]
            final = stream.get_final_message()
        self._log_final(final)
