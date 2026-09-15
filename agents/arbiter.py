from agents.base import BaseAgent


class ArbiterAgent(BaseAgent):
    """Makes PASS/FAIL/PARTIAL decisions."""

    def __init__(self, token_usage=None, model_key=None):
        super().__init__(
            role="Arbiter",
            system_prompt="""You are the Arbiter - the final decision authority.
Your role is to evaluate strategic options against:
1. Strategic fit with company objectives
2. Feasibility (resources, capabilities, timeline)
3. Risk-adjusted return potential
4. Resilience to competitive responses

For each option, decide: PASS, FAIL, or PARTIAL.
Provide clear rationale. Choose the option with the fewest barriers to success
(Step 7 of the Seven Steps to Strategy Making).
""",
            token_usage=token_usage,
            model_key=model_key,
        )

    def arbitrate(self, synthesis: dict, critique: dict, simulations: dict) -> dict:
        prompt = f"""
Strategic options:
{synthesis['options']}

Critiques:
{critique['critique']}

Simulated responses:
{simulations['simulations']}

For EACH option, provide:
- Decision: PASS / FAIL / PARTIAL
- Rationale (2-3 sentences)
- If PARTIAL: specific revision requirements

Then select the recommended option with the fewest barriers to success.
Prioritize options with strong strategic fit, feasibility, and resilience.
"""
        response = self.invoke(prompt)
        return {"decisions": response}
