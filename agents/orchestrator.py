from agents.base import BaseAgent


class OrchestratorAgent(BaseAgent):
    """Director/Manager agent."""

    PHASE_TO_NODE = {
        "research": "researcher",
        "synthesis": "synthesizer",
        "fact_check": "fact_check",
        "critique": "critic",
        "competitor": "competitor",
        "arbitration": "arbiter",
        "human_review": "human_review",
        "done": "finish",
    }

    def __init__(self, token_usage=None, model_key=None):
        super().__init__(
            role="Orchestrator",
            system_prompt="""You are the Orchestrator of a strategic decision-making system.
Your role is to:
1. Break down the strategic question into specific research domains
2. Coordinate the workflow across specialized agents
3. Decide when to proceed to the next phase
4. Synthesize final recommendations

Available agents: RESEARCHER, SYNTHESIZER, FACT CHECK, CRITIC, COMPETITOR, ARBITER.
Respond with the next agent to activate and any instructions.
""",
            token_usage=token_usage,
            model_key=model_key,
        )

    def plan_workflow(self, strategic_question: str) -> dict:
        """Ask the LLM for 3-5 research domains for the given question."""
        response = self.invoke(
            f"Strategic question: {strategic_question}\n"
            "Break this down into 3-5 specific research domains for the Researcher agents. "
            "Reply with ONLY the domain names, one per line. "
            "No numbering, no bullet points, no markdown, no extra explanation."
        )
        domains = []
        for line in response.split("\n"):
            cleaned = line.strip().lstrip("-•*0123456789.) ").strip()
            if cleaned:
                domains.append(cleaned)
        return {"domains": domains[:5]}

    def decide_next(self, state: dict) -> str:
        """Map the current workflow phase to the next node name."""
        phase = state.get("current_phase", "research")
        return self.PHASE_TO_NODE.get(phase, "finish")
