"""
Fact Check agent: verifies the factual claims behind proposed options.

The workflow can propose options whose premises are wrong (for example, "there is
no proven evidence that converging broadband and mobile services reduces churn",
when public reports show the opposite). This agent is accountable for checking
those material claims against evidence and issuing a PASS/FAIL verdict so a
failing option is sent back for revision.
"""

from agents.base import BaseAgent
from tools.search_tools import web_search, internal_search

# Verdict tokens the agent must end its answer with, so the workflow can parse
# a machine-readable pass/fail without a second LLM call.
PASS_VERDICT = "VERDICT: PASS"
FAIL_VERDICT = "VERDICT: FAIL"


def parse_verdict(text: str) -> bool:
    """Return True only if the last ``VERDICT:`` line says PASS.

    A missing verdict is treated as a failure so the option is re-checked
    (the workflow bounds the retries).
    """
    verdict_lines = [
        line for line in (text or "").splitlines() if "VERDICT:" in line.upper()
    ]
    if not verdict_lines:
        return False
    return "PASS" in verdict_lines[-1].upper()


def _search_query(strategic_question: str, options: str) -> str:
    """Build a short web-search query from the question (or the options)."""
    base = (strategic_question or "").strip().split("\n")[0].strip()
    if not base:
        base = (options or "").strip().replace("\n", " ")
    return (base[:160] + " evidence").strip()


class FactCheckAgent(BaseAgent):
    """Checks the material factual claims of each proposed option."""

    def __init__(self, token_usage=None, model_key=None):
        super().__init__(
            role="Fact Checker",
            system_prompt="""You are a rigorous Fact Checker for a strategic decision system.
Your job is to verify the material factual claims behind each proposed option against the
evidence provided, and to flag claims that are contradicted by public evidence or stated as
unsupported absolutes (for example: "there is no proven evidence that X"). You are skeptical,
evidence-driven, and precise, and you never invent sources.
""",
            token_usage=token_usage,
            model_key=model_key,
        )

    def fact_check(self, synthesis: dict, research_reports: dict = None,
                   research_materials: str = None, strategic_question: str = "") -> dict:
        """Verify the options' factual claims and return ``{fact_check, passed}``.

        Args:
            synthesis: Synthesizer output, ``{"options": "<text>"}``.
            research_reports: Research reports gathered earlier in the run.
            research_materials: The CASE.md research materials.
            strategic_question: The brief, used to build a targeted web query.

        Returns:
            ``{"fact_check": "<text>", "passed": bool}``.
        """
        options = (synthesis or {}).get("options", "")

        # Gather public + internal evidence to check the claims against.
        query = _search_query(strategic_question, options)
        web_evidence = web_search(query, max_results=5)
        internal_evidence = internal_search(query)

        prompt = f"""Fact-check the proposed options below.

Options:
{options}

Supporting research reports:
{research_reports}

Case reference materials:
{research_materials}

External web evidence:
{web_evidence}

Internal evidence:
{internal_evidence}

Do the following:
1. Extract the material factual claims behind each option.
2. Classify each claim as SUPPORTED, CONTRADICTED, or UNVERIFIED against the evidence above, and cite the source.
3. Pay special attention to sweeping negative claims (e.g. "there is no proven evidence that ..."). If public evidence shows the opposite, mark them CONTRADICTED.
4. Be concise and do not invent sources.

End your answer with exactly one line:
{FAIL_VERDICT} if any material claim is CONTRADICTED or rests on an unsupported absolute;
otherwise {PASS_VERDICT}.
"""
        response = self.invoke(prompt)
        return {"fact_check": response, "passed": parse_verdict(response)}
