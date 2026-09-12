from agents.base import BaseAgent
from tools.search_tools import web_search, internal_search


class ResearcherAgent(BaseAgent):
    """Specialized agent for gathering domain intelligence."""

    def __init__(self, domain: str, token_usage=None, model_key=None):
        super().__init__(
            role=f"Researcher: {domain}",
            system_prompt=f"""You are a Research Specialist focused on {domain}.
Your task is to gather comprehensive, accurate, and actionable intelligence.
You must:
1. Search for relevant data from both public and internal sources
2. Identify key trends, competitors, and market dynamics
3. Cite sources and note any uncertainties
4. Produce a structured research report
Be thorough but concise. Flag any data gaps or contradictions.
""",
            token_usage=token_usage,
            model_key=model_key,
        )
        self.domain = domain

    def research(self, query: str, research_materials: str = None) -> dict:
        """Search the web + internal store, then synthesize a report.

        ``research_materials`` (from CASE.md) is included as reference sources
        the agent should consult/cite when drawing conclusions.
        """
        web_results = web_search(f"{query} {self.domain}")
        internal_results = internal_search(f"{query} {self.domain}")

        materials_section = ""
        if research_materials and research_materials.strip():
            materials_section = (
                "\nReference materials (from the case):\n"
                f"{research_materials.strip()}\n"
                "Use these as primary references where relevant.\n"
            )

        synthesis_prompt = f"""
Research query: {query}
Domain: {self.domain}
{materials_section}
Web search results: {web_results}
Internal data results: {internal_results}

Produce a structured research report with:
1. Executive summary of findings
2. Key data points and trends
3. Notable uncertainties or gaps
4. Sources and confidence levels
"""
        report = self.invoke(synthesis_prompt)

        return {
            "domain": self.domain,
            "report": report,
            "sources": {"web": web_results, "internal": internal_results},
        }
