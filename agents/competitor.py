from agents.base import BaseAgent


class CompetitorAgent(BaseAgent):
    """Simulates external stakeholder responses."""

    def __init__(self, token_usage=None, model_key=None):
        super().__init__(
            role="Competitor Simulator",
            system_prompt="""You simulate how external actors would respond to strategic options.
Adopt the personas of:
1. Competitors - How would they attack or counter this?
2. Customers - How would they react? What would they love/hate?
3. Regulators - What concerns would they raise?
4. Partners/Suppliers - How would they respond?
Be realistic and specific.
""",
            token_usage=token_usage,
            model_key=model_key,
        )

    def simulate(self, synthesis: dict, critique: dict) -> dict:
        prompt = f"""
Strategic options:
{synthesis['options']}

Identified weaknesses:
{critique['critique']}

For EACH option, simulate responses from:
1. A major competitor
2. A skeptical customer segment
3. A regulator
4. A key supplier or partner

For each, describe their likely reaction and how to address it.
"""
        response = self.invoke(prompt)
        return {"simulations": response}
