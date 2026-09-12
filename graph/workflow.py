"""
LangGraph orchestration for the Strategic Workflow.

This module wires the specialized agents (Orchestrator, Researcher,
Synthesizer, Critic, Competitor, Arbiter) into a state machine. Each agent is a
node; after every node, control returns to the Orchestrator, which routes to
the next phase. A human-review node sits before the end and can either approve
the result or send the workflow back to synthesis for another iteration.
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from graph.state import StrategicState
from agents.base import TokenUsage, model_key_for
from agents.orchestrator import OrchestratorAgent
from agents.researcher import ResearcherAgent
from agents.synthesizer import SynthesizerAgent
from agents.fact_checker import FactCheckAgent
from agents.critic import CriticAgent
from agents.competitor import CompetitorAgent
from agents.arbiter import ArbiterAgent


# Bounds the fact-check revision loop: after this many failed fact-checks the
# run proceeds to critique rather than looping forever.
MAX_FACT_CHECKS = 2


class StrategicWorkflow:
    """Builds and runs the multi-agent strategic decision-making graph."""

    @staticmethod
    def _model_key(agent: str) -> str:
        """Resolve the Config.MODELS profile key for an agent name."""
        return model_key_for(agent)

    def __init__(self):
        # Shared token-usage counter aggregated across every LLM call in a run.
        self.token_usage = TokenUsage()

        # Instantiate each specialized agent once, passing the shared counter
        # and each agent's assigned model profile (Config.AGENT_MODELS).
        self.orchestrator = OrchestratorAgent(
            token_usage=self.token_usage, model_key=self._model_key("orchestrator"))
        self.synthesizer = SynthesizerAgent(
            token_usage=self.token_usage, model_key=self._model_key("synthesizer"))
        self.fact_checker = FactCheckAgent(
            token_usage=self.token_usage, model_key=self._model_key("fact_check"))
        self.critic = CriticAgent(
            token_usage=self.token_usage, model_key=self._model_key("critic"))
        self.competitor = CompetitorAgent(
            token_usage=self.token_usage, model_key=self._model_key("competitor"))
        self.arbiter = ArbiterAgent(
            token_usage=self.token_usage, model_key=self._model_key("arbiter"))

        # Record which AI model powers each agent (reference for the report).
        # The researcher's model is filled in when it is instantiated.
        self.agent_models = {
            "orchestrator_plan": self.orchestrator.model_name,
            "researcher": None,
            "synthesizer": self.synthesizer.model_name,
            "fact_check": self.fact_checker.model_name,
            "critic": self.critic.model_name,
            "competitor": self.competitor.model_name,
            "arbiter": self.arbiter.model_name,
            "human_review": "n/a (no LLM call)",
        }

        # Tracks the most recent LangGraph interrupt so run() can resume it.
        self._last_interrupt = None
        self.graph = self._build_graph()
        self.memory = MemorySaver()
        self.app = self.graph.compile(checkpointer=self.memory)

    def _build_graph(self):
        """Define the nodes, entry point, and edges of the state machine."""
        workflow = StateGraph(StrategicState)

        workflow.add_node("orchestrator_plan", self._orchestrator_plan)
        workflow.add_node("researcher", self._researcher_node)
        workflow.add_node("synthesizer", self._synthesizer_node)
        workflow.add_node("fact_check", self._fact_check_node)
        workflow.add_node("critic", self._critic_node)
        workflow.add_node("competitor", self._competitor_node)
        workflow.add_node("arbiter", self._arbiter_node)
        workflow.add_node("human_review", self._human_review_node)

        workflow.set_entry_point("orchestrator_plan")

        # From the orchestrator, decide the next node based on the phase.
        workflow.add_conditional_edges(
            "orchestrator_plan",
            self._route_from_orchestrator,
            {
                "researcher": "researcher",
                "synthesizer": "synthesizer",
                "fact_check": "fact_check",
                "critic": "critic",
                "competitor": "competitor",
                "arbiter": "arbiter",
                "human_review": "human_review",
                "finish": END
            }
        )

        # After each specialized node, control returns to the orchestrator.
        for node in ("researcher", "synthesizer", "fact_check", "critic", "competitor", "arbiter"):
            workflow.add_edge(node, "orchestrator_plan")

        # Human review either finishes or loops back for revision.
        workflow.add_conditional_edges(
            "human_review",
            self._route_after_human_review,
            {"finish": END, "revise": "orchestrator_plan"}
        )

        return workflow

    # ---- Node implementations ----

    def _orchestrator_plan(self, state: StrategicState) -> dict:
        """Plan research domains on first entry; otherwise leave state alone."""
        if not state.get("research_domains"):
            plan = self.orchestrator.plan_workflow(state["strategic_question"])
            return {"research_domains": plan["domains"], "current_phase": "research"}
        # The previous node advanced current_phase; the router dispatches.
        return {}

    def _researcher_node(self, state: StrategicState) -> dict:
        """Run one ResearcherAgent per planned domain and collect reports."""
        reports = {}
        for domain in state.get("research_domains", []):
            researcher = ResearcherAgent(
                domain,
                token_usage=self.token_usage,
                model_key=self._model_key("researcher"),
            )
            self.agent_models["researcher"] = researcher.model_name
            reports[domain] = researcher.research(
                state["strategic_question"],
                state.get("research_materials", ""),
            )
        return {
            "research_reports": reports,
            "research_complete": True,
            "current_phase": "synthesis"
        }

    def _synthesizer_node(self, state: StrategicState) -> dict:
        """Generate options; feed prior fact-check findings back in on a revision."""
        previous = state.get("fact_check")
        feedback = previous.get("fact_check") if previous and not previous.get("passed") else None
        synthesis = self.synthesizer.synthesize(
            state["research_reports"],
            state["strategic_question"],
            feedback=feedback,
        )
        return {"synthesis": synthesis, "current_phase": "fact_check"}

    def _fact_check_node(self, state: StrategicState) -> dict:
        """Verify the options' factual claims; on failure, loop back to synthesis."""
        result = self.fact_checker.fact_check(
            state["synthesis"],
            state.get("research_reports"),
            state.get("research_materials", ""),
            state.get("strategic_question", ""),
        )
        iterations = state.get("fact_check_iterations", 0) + 1
        # Advance once the claims pass, or once the revision budget is spent.
        if result["passed"] or iterations >= MAX_FACT_CHECKS:
            return {
                "fact_check": result,
                "fact_check_iterations": iterations,
                "current_phase": "critique",
            }
        return {
            "fact_check": result,
            "fact_check_iterations": iterations,
            "current_phase": "synthesis",
            "messages": [
                "Fact-check failed; revising options. " + str(result["fact_check"])[:200]
            ],
        }

    def _critic_node(self, state: StrategicState) -> dict:
        critique = self.critic.critique(
            state["synthesis"],
            state["research_reports"]
        )
        return {"critique": critique, "current_phase": "competitor"}

    def _competitor_node(self, state: StrategicState) -> dict:
        simulations = self.competitor.simulate(
            state["synthesis"],
            state["critique"]
        )
        return {"simulations": simulations, "current_phase": "arbitration"}

    def _arbiter_node(self, state: StrategicState) -> dict:
        decisions = self.arbiter.arbitrate(
            state["synthesis"],
            state["critique"],
            state["simulations"]
        )
        return {"decisions": decisions, "current_phase": "human_review"}

    def _human_review_node(self, state: StrategicState) -> dict:
        """Pause for human approval; approve or send back for revision."""
        review_data = interrupt({
            "question": "Review the strategic decisions before finalizing.",
            "decisions": state.get("decisions"),
            "synthesis": state.get("synthesis"),
            "critique": state.get("critique"),
            "simulations": state.get("simulations")
        })
        # Approve, or force approval once the revision budget is exhausted.
        if review_data.get("approved") or state.get("iteration", 0) >= state.get("max_iterations", 5):
            return {"current_phase": "done"}
        return {
            "current_phase": "synthesis",
            "iteration": state.get("iteration", 0) + 1,
            "messages": [f"Revision requested: {review_data.get('feedback', '')}"]
        }

    def _route_from_orchestrator(self, state: StrategicState) -> str:
        """Route to the next node; force human review when out of iterations."""
        if state.get("iteration", 0) >= state.get("max_iterations", 5):
            return "human_review"
        return self.orchestrator.decide_next(state)

    def _route_after_human_review(self, state: StrategicState) -> str:
        return "finish" if state.get("current_phase") == "done" else "revise"

    def _print_token_usage(self):
        """Print the accumulated input/output token totals for the run."""
        u = self.token_usage
        print("\n--- token_usage ---")
        print(f"input_tokens: {u.input_tokens}")
        print(f"output_tokens: {u.output_tokens}")
        print(f"total_tokens: {u.total_tokens}")
        print(f"llm_calls: {u.calls}")
        # Per-model breakdown (each model priced separately).
        for model_key in u.by_model:
            bucket = u.by_model[model_key]
            print(f"{model_key}_input_tokens: {bucket['input_tokens']}")
            print(f"{model_key}_output_tokens: {bucket['output_tokens']}")
            print(f"{model_key}_estimated_cost_usd: {u.cost_for(model_key):.6f}")
        print(f"estimated_cost_usd: {u.estimated_cost_usd:.6f}")

    def _print_agent_models(self):
        """Print which AI model powers each agent (for report reference)."""
        print("\n--- agent_models ---")
        for agent, model in self.agent_models.items():
            print(f"{agent}: {model}")

    # ---- Runner ----

    def run(self, strategic_question: str, config: dict = None,
            auto_approve: bool = False, reviewer=None,
            research_materials: str = None) -> dict:
        """Run the workflow and return the final state.

        Args:
            strategic_question: The business question to analyze (question +
                attentions + constraints composed by the caller).
            config: LangGraph runtime config (e.g. thread_id for checkpoints).
            auto_approve: If True, auto-approve the human-review interrupt
                (non-interactive demo mode).
            reviewer: Optional callable(review_data) -> decision dict. When
                omitted and auto_approve is False, prompts on the terminal.
            research_materials: Reference material (from CASE.md) given to the
                Researcher agents.
        """
        initial_state = {
            "strategic_question": strategic_question,
            "research_materials": research_materials or "",
            "current_phase": "research",
            "iteration": 0,
            "max_iterations": 5,
            "fact_check_iterations": 0,
            "research_reports": {},
            "messages": [],
            "errors": []
        }
        config = config or {"configurable": {"thread_id": "strategy_session_1"}}

        self._consume(self.app.stream(initial_state, config))

        # Resume any human-review interrupts until the graph reaches END.
        while self._last_interrupt is not None:
            print("[HUMAN REVIEW] Workflow paused for approval.")
            review_data = self._last_interrupt.value
            if reviewer is not None:
                decision = reviewer(review_data)
            elif auto_approve:
                print("[DEMO] Auto-approving the decision to complete the run...")
                decision = {"approved": True, "notes": "Auto-approved (demo mode)"}
            else:
                decision = self._prompt_reviewer(review_data)
            self._last_interrupt = None
            self._consume(self.app.stream(Command(resume=decision), config))

        final = self.app.get_state(config)
        self._print_agent_models()
        self._print_token_usage()
        return final.values if final else None

    def _consume(self, events):
        """Drain one stream of events, printing node output and capturing interrupts."""
        self._last_interrupt = None
        for event in events:
            for node_name, node_output in event.items():
                if node_name == "__interrupt__":
                    self._last_interrupt = node_output[0]
                    continue
                print(f"\n--- {node_name} ---")
                if isinstance(node_output, dict):
                    for key, value in node_output.items():
                        if key != "messages" and value:
                            print(f"{key}: {str(value)[:200]}...")

    @staticmethod
    def _prompt_reviewer(review_data: dict) -> dict:
        """Interactively ask a human to approve or request a revision."""
        print("\n" + "=" * 60)
        print("HUMAN REVIEW REQUIRED")
        print("=" * 60)
        for key in ("decisions", "synthesis", "critique", "simulations"):
            if review_data.get(key):
                print(f"\n[{key}]\n{str(review_data[key])[:800]}")
        answer = input("\nApprove the decisions? [y/N]: ").strip().lower()
        if answer in ("y", "yes", "approve"):
            return {"approved": True, "notes": "approved by human"}
        feedback = input("Feedback for revision (optional): ").strip()
        return {"approved": False, "feedback": feedback or "revise"}
