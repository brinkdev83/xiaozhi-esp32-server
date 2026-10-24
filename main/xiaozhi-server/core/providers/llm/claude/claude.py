import anthropic

from config.logger import setup_logging
from core.providers.llm.base import LLMProviderBase

TAG = __name__
logger = setup_logging()


class LLMProvider(LLMProviderBase):
    """Claude via the official Anthropic SDK.

    The API key comes from `api_key` in the config or, when that is empty, from
    the ANTHROPIC_API_KEY environment variable (the SDK's default lookup).
    Function calling is not wired up: pair this provider with `Intent: nointent`.
    """

    def __init__(self, config):
        self.model_name = config.get("model_name") or "claude-opus-5-5"
        self.max_tokens = int(config.get("max_tokens") or 2048)
        # Spoken small talk: low effort keeps the first token fast.
        self.effort = config.get("effort") or "low"
        api_key = config.get("api_key") or None
        self.client = anthropic.Anthropic(api_key=api_key)

    @staticmethod
    def _to_messages(dialogue):
        """Split the server's OpenAI-style dialogue into (system, messages).

        System entries become the system prompt; tool entries are dropped (no
        function calling); consecutive turns of the same role are merged and the
        list is made to start with a user turn, as the Messages API requires.
        """
        system_parts = []
        messages = []
        for msg in dialogue:
            role = msg.get("role")
            content = msg.get("content") or ""
            if not isinstance(content, str):
                content = str(content)
            if role == "system":
                if content:
                    system_parts.append(content)
                continue
            if role not in ("user", "assistant") or not content:
                continue
            if messages and messages[-1]["role"] == role:
                messages[-1]["content"] += "\n" + content
            else:
                messages.append({"role": role, "content": content})
        while messages and messages[0]["role"] != "user":
            messages.pop(0)
        return "\n\n".join(system_parts), messages

    def response(self, session_id, dialogue, **kwargs):
        system, messages = self._to_messages(dialogue)
        if not messages:
            return

        params = {
            "model": self.model_name,
            "max_tokens": kwargs.get("max_tokens") or self.max_tokens,
            "messages": messages,
            "output_config": {"effort": self.effort},
            # Server-side fallback: on a policy decline the API retries on a
            # suitable model inside the same call instead of returning nothing.
            "betas": ["server-side-fallback-2026-07-01"],
            "fallbacks": "default",
        }
        if system:
            params["system"] = system

        with self.client.beta.messages.stream(**params) as stream:
            for text in stream.text_stream:
                if text:
                    yield text
            final = stream.get_final_message()

        if final.stop_reason == "refusal":
            logger.bind(tag=TAG).warning(f"Claude declined the request: {final.stop_details}")
        usage = final.usage
        logger.bind(tag=TAG).info(
            f"Claude {final.model}: in {usage.input_tokens}, out {usage.output_tokens}"
        )
