"""
Configuration for the Strategic Workflow.

Environment (``.env``) supplies all run parameters and model profiles, while
case-specific content (question, attentions, constraints, research materials)
is read from the Markdown file named by the ``CASE_FILE`` env var (``CASE.md``).
``config.py`` contains no hardcoded model names, URLs, keys, prices, or agent
assignments. The set of model profiles is discovered dynamically: a profile is
registered when it appears in ``MODEL_PROFILES``, ``AGENT_MODELS``, or
``DEFAULT_MODEL``, so users can add/switch models purely by editing ``.env``.
"""

import os

from dotenv import load_dotenv

from case import load_case

load_dotenv()


def _req(name):
    """Return a required env var, failing fast with a clear message."""
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Missing required .env variable: {name}")
    return value


def _env(name):
    """Return an optional env var (empty string when unset)."""
    return os.getenv(name) or ""


def _env_float(name):
    """Return a numeric env var; empty/unparseable values become 0.0."""
    try:
        return float(os.getenv(name) or 0.0)
    except ValueError:
        return 0.0


class Config:
    # ---- Generic run parameters (required, from .env) ----
    TEMPERATURE = float(_req("TEMPERATURE"))
    MAX_ITERATIONS = int(_req("MAX_ITERATIONS"))
    INTERNAL_DOCS_DIR = _req("INTERNAL_DOCS_DIR")

    # ---- Strategic inputs (read from the CASE.md file named by CASE_FILE) ----
    CASE_FILE = _req("CASE_FILE")
    _case = load_case(CASE_FILE)
    CASE_OBJECTIVES = _case["objectives"]
    STRATEGIC_QUESTION = _case["strategic_question"]
    STRATEGIC_ATTENTIONS = _case["attentions"]
    STRATEGIC_CONSTRAINTS = _case["constraints"]
    RESEARCH_MATERIALS = _case["research_materials"]

    # ---- Provider credentials & defaults (from .env) ----
    DEEPSEEK_API_KEY = _env("DEEPSEEK_API_KEY")
    DEEPSEEK_MODEL = _env("DEEPSEEK_MODEL")
    DEEPSEEK_BASE_URL = _env("DEEPSEEK_BASE_URL")
    QWEN_API_KEY = _env("QWEN_API_KEY")
    QWEN_MODEL = _env("QWEN_MODEL")
    QWEN_BASE_URL = _env("QWEN_BASE_URL")
    KIMI_API_KEY = _env("KIMI_API_KEY")
    KIMI_MODEL = _env("KIMI_MODEL")
    KIMI_BASE_URL = _env("KIMI_BASE_URL")

    # ---- Model profiles (list, default, credential sharing from .env) ----
    MODEL_PROFILES = [p.strip() for p in _env("MODEL_PROFILES").split(",") if p.strip()]
    DEFAULT_MODEL = _req("DEFAULT_MODEL")
    # Profiles allowed to reuse the shared DeepSeek credentials when they do not
    # define their own <PREFIX>_API_KEY / <PREFIX>_BASE_URL.
    DEEPSEEK_FAMILY = {p.strip() for p in _env("DEEPSEEK_FAMILY").split(",") if p.strip()}

    # ---- Agent -> model profile assignments (from .env) ----
    AGENT_MODELS = {}
    for _pair in _env("AGENT_MODELS").split(","):
        if ":" in _pair:
            _agent, _profile = _pair.split(":", 1)
            AGENT_MODELS[_agent.strip()] = _profile.strip()

    # Auto-register every profile referenced anywhere (MODEL_PROFILES, agent
    # assignments, or the default), so adding a new model in .env "just works".
    _ALL_PROFILES = []
    for _profile in MODEL_PROFILES + list(AGENT_MODELS.values()) + [DEFAULT_MODEL]:
        if _profile and _profile not in _ALL_PROFILES:
            _ALL_PROFILES.append(_profile)

    # Build MODELS / PRICING dynamically. Every value (model, key, base URL,
    # prices, reasoning effort) comes from ``<PREFIX>_*`` env vars.
    MODELS = {}
    PRICING = {}
    for _profile in _ALL_PROFILES:
        _prefix = _profile.upper()
        _key = _env(f"{_prefix}_API_KEY")
        _base = _env(f"{_prefix}_BASE_URL")
        if _profile in DEEPSEEK_FAMILY:
            _key = _key or DEEPSEEK_API_KEY
            _base = _base or DEEPSEEK_BASE_URL
        MODELS[_profile] = {
            "model": _env(f"{_prefix}_MODEL"),
            "api_key": _key,
            "base_url": _base,
            "reasoning_effort": _env(f"{_prefix}_REASONING_EFFORT"),
        }
        PRICING[_profile] = {
            "input_price_per_m": _env_float(f"{_prefix}_INPUT_PRICE_PER_M"),
            "output_price_per_m": _env_float(f"{_prefix}_OUTPUT_PRICE_PER_M"),
        }
