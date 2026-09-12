"""
Shared LLM plumbing for all agents.

Every agent subclasses ``BaseAgent``, which owns a DeepSeek-backed chat model
(``ChatOpenAI`` pointed at DeepSeek's OpenAI-compatible endpoint), a helper for
building a message list, and a shared ``TokenUsage`` counter that records input
and output tokens for every LLM call in the run.
"""

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from config import Config


class TokenUsage:
    """Accumulates LLM token usage across the whole workflow run.

    Tokens are also tracked per model profile (``flash``/``pro``/``qwen``) so
    the estimated cost can use each model's own per-1M-token price.
    """

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        # model profile key -> {"input_tokens", "output_tokens", "calls"}
        self.by_model = {}

    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens

    def add(self, input_tokens, output_tokens, model_key=None):
        input_tokens = int(input_tokens or 0)
        output_tokens = int(output_tokens or 0)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1
        if model_key:
            bucket = self.by_model.setdefault(
                model_key, {"input_tokens": 0, "output_tokens": 0, "calls": 0})
            bucket["input_tokens"] += input_tokens
            bucket["output_tokens"] += output_tokens
            bucket["calls"] += 1

    @staticmethod
    def _prices(model_key):
        pricing = Config.PRICING.get(model_key) or Config.PRICING[Config.DEFAULT_MODEL]
        return pricing["input_price_per_m"], pricing["output_price_per_m"]

    def cost_for(self, model_key):
        """Estimated cost (USD) for one model profile."""
        bucket = self.by_model.get(model_key)
        if not bucket:
            return 0.0
        input_price, output_price = self._prices(model_key)
        return (
            bucket["input_tokens"] / 1_000_000 * input_price
            + bucket["output_tokens"] / 1_000_000 * output_price
        )

    @property
    def estimated_cost_usd(self):
        """Estimated API cost summed across all models (per-model pricing)."""
        return sum(self.cost_for(key) for key in self.by_model)


def create_llm(temperature: float = Config.TEMPERATURE, model_key: str = None):
    """Build a chat model from the given ``Config.MODELS`` profile.

    ``model_key`` names a profile registered in ``Config.MODELS`` (e.g.
    "deepseek", "pro", "qwen", "kimi", or any profile a user added in .env);
    defaults to ``Config.DEFAULT_MODEL``.
    """
    model_key = model_key or Config.DEFAULT_MODEL
    profile = Config.MODELS.get(model_key) or Config.MODELS[Config.DEFAULT_MODEL]
    if not profile.get("api_key"):
        raise ValueError(
            f"No API key configured for model profile '{model_key}'. "
            f"Please set {model_key.upper()}_API_KEY in .env and run again."
        )
    kwargs = {}
    if profile.get("reasoning_effort"):
        # Reasoning models (e.g. Moonshot Kimi) only accept temperature=1 and
        # are steered via reasoning_effort; omit temperature in that case.
        kwargs["extra_body"] = {"reasoning_effort": profile["reasoning_effort"]}
        temperature = None
    if temperature is not None:
        kwargs["temperature"] = temperature
    return ChatOpenAI(
        model=profile["model"],
        api_key=profile["api_key"],
        base_url=profile["base_url"],
        **kwargs,
    )


def model_key_for(agent: str) -> str:
    """Resolve the model profile key for a workflow agent name."""
    return Config.AGENT_MODELS.get(agent) or Config.DEFAULT_MODEL


class BaseAgent:
    """Base class with common LLM initialization, usage tracking, and messages."""

    def __init__(self, role: str, system_prompt: str, temperature: float = 0.2,
                 token_usage: TokenUsage = None, model_key: str = None):
        # role is a human-readable label used for logging/debugging.
        self.role = role
        self.system_prompt = system_prompt
        # Which Config.MODELS profile this agent uses (flash by default).
        self.model_key = model_key or Config.DEFAULT_MODEL
        self.llm = create_llm(temperature, model_key=self.model_key)
        # Shared counter (owned by StrategicWorkflow) so token usage is
        # aggregated across every agent in a single run.
        self.token_usage = token_usage

    @property
    def model_name(self):
        """The model name this agent's LLM is configured with."""
        return getattr(self.llm, "model_name", None) or Config.DEEPSEEK_MODEL

    def _invoke(self, messages):
        """Invoke the LLM and record token usage on the shared counter."""
        response = self.llm.invoke(messages)
        self._record_usage(response)
        return response

    def _record_usage(self, response):
        """Extract input/output tokens from the response and accumulate them."""
        if self.token_usage is None:
            return

        # LangChain 1.x exposes a standardized usage_metadata dict.
        usage = getattr(response, "usage_metadata", None) or {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")

        # Fall back to the OpenAI-style token_usage metadata if needed.
        if input_tokens is None or output_tokens is None:
            token_usage = (getattr(response, "response_metadata", None) or {}).get("token_usage") or {}
            input_tokens = input_tokens if input_tokens is not None else token_usage.get("prompt_tokens")
            output_tokens = output_tokens if output_tokens is not None else token_usage.get("completion_tokens")

        if input_tokens is not None or output_tokens is not None:
            self.token_usage.add(input_tokens, output_tokens, model_key=self.model_key)

    def invoke(self, human_content: str, context: dict = None) -> str:
        """Invoke the LLM with the system prompt + a human message.

        Returns the response text (``str``) and records token usage.
        """
        messages = self._format_messages(context or {})
        messages.append(HumanMessage(content=human_content))
        return self._invoke(messages).content

    def _format_messages(self, context: dict) -> list:
        """Assemble a message list: system prompt + optional context blocks.

        Args:
            context: Optional dict that may contain "research_reports",
                "synthesis", and/or "critique" keys. Each present, non-empty
                key is appended as a HumanMessage for the LLM.
        """
        # The system prompt defines the agent's persona and instructions.
        messages = [SystemMessage(content=self.system_prompt)]

        # Append any context the caller supplied.
        if context.get("research_reports"):
            messages.append(HumanMessage(
                content=f"Research reports:\n{context['research_reports']}"
            ))
        if context.get("synthesis"):
            messages.append(HumanMessage(
                content=f"Current synthesis:\n{context['synthesis']}"
            ))
        if context.get("critique"):
            messages.append(HumanMessage(
                content=f"Previous critique:\n{context['critique']}"
            ))
        return messages
