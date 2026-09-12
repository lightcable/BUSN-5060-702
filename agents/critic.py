from agents.base import BaseAgent


class CriticAgent(BaseAgent):
    """Rigorously challenges proposals."""

    def __init__(self, token_usage=None, model_key=None):
        super().__init__(
            role="Critic",
            system_prompt="""You are the Strategic Critic - a devil's advocate.
Your role is to:
1. Identify logical fallacies, inconsistencies, and unsupported claims
2. Challenge assumptions behind each strategic option
3. Test for internal consistency across options
4. Flag any fabricated evidence or dubious data
Be rigorous but constructive.
""",
            token_usage=token_usage,
            model_key=model_key,
        )

    def critique(self, synthesis: dict, research_reports: dict) -> dict:
        prompt = f"""
Strategic options to critique:
{synthesis['options']}

Research reports for reference:
{research_reports}

For each option, provide:
1. The strongest argument AGAINST this option
2. The weakest assumption that needs validation
3. Any data that contradicts the rationale
4. Potential internal inconsistencies

Then provide an overall assessment.
"""
        response = self.invoke(prompt)
        return {"critique": response}
