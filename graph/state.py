"""
Shared state schema for the Strategic Workflow.

LangGraph nodes read from and write to a single shared state object. This
module declares that schema as a ``TypedDict`` so every node knows exactly
which keys exist and what types they hold.
"""

from typing import TypedDict, Annotated, List, Dict, Optional
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class StrategicState(TypedDict):
    """The complete, mutable state threaded through every workflow node.

    Plain fields (no reducer) are overwritten by the last node that writes
    them. The ``messages`` field uses the ``add_messages`` reducer so message
    lists accumulate instead of being replaced.
    """

    # The high-level business question being answered (e.g. "build, acquire,
    # or partner for AI capabilities?"). Composed from the CASE.md question,
    # attentions, and constraints.
    strategic_question: str

    # Reference materials (e.g. source URLs) from CASE.md, passed to the
    # Researcher agents so they can cite/consult them.
    research_materials: str

    # The current workflow phase. Phases are logical names ("research",
    # "synthesis", "fact_check", "critique", "competitor", "arbitration",
    # "human_review", "done") — NOT node names. graph/workflow.py maps
    # phase -> node.
    current_phase: str

    # Number of human-review rejections so far; used to cap revision loops.
    iteration: int

    # Hard cap on revision loops before the workflow forces a human review.
    max_iterations: int

    # Research domains chosen by the Orchestrator for the Researcher agents.
    research_domains: List[str]

    # Maps each research domain to its ResearcherAgent report dict.
    research_reports: Dict[str, dict]

    # Set to True once the researcher node has run for all domains.
    research_complete: bool

    # Synthesizer output: {"options": "<text>"}.
    synthesis: Optional[dict]

    # Fact Check agent output: {"fact_check": "<text>", "passed": bool}.
    fact_check: Optional[dict]

    # Number of fact-check re-syntheses so far (bounds the fact-check loop).
    fact_check_iterations: int

    # Critic output: {"critique": "<text>"}.
    critique: Optional[dict]

    # Competitor output: {"simulations": "<text>"}.
    simulations: Optional[dict]

    # Arbiter output: {"decisions": "<text>"}.
    decisions: Optional[dict]

    # Accumulated chat/message history (uses add_messages so it appends).
    messages: Annotated[List[BaseMessage], add_messages]

    # Any errors collected during the run (informational; unused by nodes today).
    errors: List[str]

    # Retry counter placeholder (declared for future use; not currently written).
    retry_count: int
