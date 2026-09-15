from agents.base import BaseAgent


class SynthesizerAgent(BaseAgent):
    """Creates strategic options from research."""

    def __init__(self, token_usage=None, model_key=None):
        super().__init__(
            role="Synthesizer",
            system_prompt="""You are the Strategic Synthesizer.
Your role is to:
1. Combine research from multiple domains into coherent strategic options
2. Generate 3-5 distinct strategic alternatives
3. For each option, outline: rationale, key actions, risks, and resources needed
4. Present options in a structured, comparable format
5. For each option, specify its Conditions for Success — what must be true for the
   option to work. This is Step 3 of the Seven Steps to Strategy Making.
Think creatively but stay grounded in the research.
""",
            token_usage=token_usage,
            model_key=model_key,
        )

    def synthesize(self, research_reports: dict, strategic_question: str,
                   feedback: str = None) -> dict:
        """Generate strategic options from the research reports.

        ``feedback`` (optional) carries fact-check findings from a previous
        pass; when present the model must correct those issues.

        Returns {"options": "<text>"}.
        """
        reports_text = "\n\n".join([
            f"Domain: {r['domain']}\n{r['report']}"
            for r in research_reports.values()
        ])
        feedback_section = ""
        if feedback:
            feedback_section = (
                "\nA previous fact-check flagged the following issues; your revised "
                f"options MUST correct them:\n{feedback}\n"
            )
        prompt = f"""
Strategic question: {strategic_question}

Research reports:
{reports_text}
{feedback_section}
Generate 3-5 distinct strategic options. For each option provide:
- Name and one-line description
- Core rationale (why this could work)
- Key actions required
- Major risks
- Resources/capabilities needed
- Success metrics
- Conditions for Success (what must be true for this option to succeed)

Format each option clearly.
"""
        response = self.invoke(prompt)
        return {"options": response}
