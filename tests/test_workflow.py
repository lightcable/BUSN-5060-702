import unittest
from unittest import mock

import config as config_module
from agents.base import BaseAgent
from agents.orchestrator import OrchestratorAgent
from graph.workflow import StrategicWorkflow


class FakeResp:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def __init__(self, content="Option A\nOption B\nOption C"):
        self.content = content

    def invoke(self, messages):
        return FakeResp(self.content)


class TestConfig(unittest.TestCase):
    def test_deepseek_fields_exist(self):
        self.assertTrue(hasattr(config_module.Config, "DEEPSEEK_MODEL"))
        self.assertTrue(hasattr(config_module.Config, "DEEPSEEK_API_KEY"))
        self.assertTrue(hasattr(config_module.Config, "DEEPSEEK_BASE_URL"))
        self.assertTrue(hasattr(config_module.Config, "INTERNAL_DOCS_DIR"))

    def test_no_legacy_fields(self):
        self.assertFalse(hasattr(config_module.Config, "MODEL_NAME"))
        self.assertFalse(hasattr(config_module.Config, "OPENAI_API_KEY"))


class TestBaseAgent(unittest.TestCase):
    def test_format_messages_system_only(self):
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()):
            agent = BaseAgent("Tester", "sys prompt")
        msgs = agent._format_messages({})
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].content, "sys prompt")

    def test_format_messages_with_context(self):
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()):
            agent = BaseAgent("Tester", "sys prompt")
        msgs = agent._format_messages({
            "research_reports": {"d": "r"},
            "synthesis": {"options": "o"},
            "critique": {"critique": "c"},
        })
        self.assertEqual(len(msgs), 4)

    def test_invoke_returns_content(self):
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()):
            agent = BaseAgent("Tester", "sys prompt")
        self.assertEqual(agent.invoke("hello"), "Option A\nOption B\nOption C")


class TestOrchestrator(unittest.TestCase):
    def test_decide_next_mapping(self):
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()):
            agent = OrchestratorAgent()
        cases = {
            "research": "researcher",
            "synthesis": "synthesizer",
            "fact_check": "fact_check",
            "critique": "critic",
            "competitor": "competitor",
            "arbitration": "arbiter",
            "human_review": "human_review",
            "done": "finish",
            "bogus": "finish",
        }
        for phase, node in cases.items():
            self.assertEqual(agent.decide_next({"current_phase": phase}), node)

    def test_decide_next_defaults_to_research(self):
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()):
            agent = OrchestratorAgent()
        self.assertEqual(agent.decide_next({}), "researcher")

    def test_plan_workflow_parses_domains(self):
        llm = FakeLLM("1. Market dynamics\n2) Technology trends\n- Regulatory\nFinance\n\n")
        with mock.patch("agents.base.create_llm", return_value=llm):
            agent = OrchestratorAgent()
        plan = agent.plan_workflow("q")
        self.assertEqual(
            plan["domains"],
            ["Market dynamics", "Technology trends", "Regulatory", "Finance"],
        )


class TestWorkflowRouting(unittest.TestCase):
    def test_route_from_orchestrator_phases(self):
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()):
            wf = StrategicWorkflow()
        base = {"iteration": 0, "max_iterations": 5}
        for phase, node in OrchestratorAgent.PHASE_TO_NODE.items():
            self.assertEqual(wf._route_from_orchestrator({**base, "current_phase": phase}), node)

    def test_route_from_orchestrator_iteration_cap(self):
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()):
            wf = StrategicWorkflow()
        state = {"current_phase": "synthesis", "iteration": 5, "max_iterations": 5}
        self.assertEqual(wf._route_from_orchestrator(state), "human_review")

    def test_route_after_human_review(self):
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()):
            wf = StrategicWorkflow()
        self.assertEqual(wf._route_after_human_review({"current_phase": "done"}), "finish")
        self.assertEqual(wf._route_after_human_review({"current_phase": "synthesis"}), "revise")


class TestFactCheck(unittest.TestCase):
    def test_parse_verdict(self):
        from agents.fact_checker import parse_verdict
        self.assertTrue(parse_verdict("analysis\nVERDICT: PASS"))
        self.assertFalse(parse_verdict("analysis\nVERDICT: FAIL"))
        # A missing verdict is treated as a failure so the option is re-checked.
        self.assertFalse(parse_verdict("no verdict here"))

    def test_fact_check_node_pass_advances_to_critique(self):
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()), \
             mock.patch("agents.fact_checker.web_search", return_value="evidence"), \
             mock.patch("agents.fact_checker.internal_search", return_value="evidence"):
            wf = StrategicWorkflow()
            wf.fact_checker.llm = FakeLLM("ok\nVERDICT: PASS")
            out = wf._fact_check_node({"synthesis": {"options": "o"}, "fact_check_iterations": 0})
        self.assertTrue(out["fact_check"]["passed"])
        self.assertEqual(out["current_phase"], "critique")

    def test_fact_check_node_fail_loops_to_synthesis(self):
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()), \
             mock.patch("agents.fact_checker.web_search", return_value="evidence"), \
             mock.patch("agents.fact_checker.internal_search", return_value="evidence"):
            wf = StrategicWorkflow()
            wf.fact_checker.llm = FakeLLM("bad\nVERDICT: FAIL")
            out = wf._fact_check_node({"synthesis": {"options": "o"}, "fact_check_iterations": 0})
        self.assertFalse(out["fact_check"]["passed"])
        self.assertEqual(out["current_phase"], "synthesis")

    def test_fact_check_loop_is_capped(self):
        from graph.workflow import MAX_FACT_CHECKS
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()), \
             mock.patch("agents.fact_checker.web_search", return_value="evidence"), \
             mock.patch("agents.fact_checker.internal_search", return_value="evidence"):
            wf = StrategicWorkflow()
            wf.fact_checker.llm = FakeLLM("bad\nVERDICT: FAIL")
            out = wf._fact_check_node({
                "synthesis": {"options": "o"},
                "fact_check_iterations": MAX_FACT_CHECKS - 1,
            })
        self.assertEqual(out["current_phase"], "critique")


class TestSevenSteps(unittest.TestCase):
    """The workflow should explicitly produce the Seven Steps artifacts."""

    def test_agent_prompts_embed_seven_steps(self):
        from agents.synthesizer import SynthesizerAgent
        from agents.critic import CriticAgent
        from agents.competitor import CompetitorAgent
        from agents.arbiter import ArbiterAgent
        from agents.fact_checker import FactCheckAgent
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()):
            synth = SynthesizerAgent()
            crit = CriticAgent()
            comp = CompetitorAgent()
            arb = ArbiterAgent()
            fact = FactCheckAgent()
        # Step 3: conditions for success.
        self.assertIn("Conditions for Success", synth.system_prompt)
        # Steps 4-5: barriers and tests.
        self.assertIn("Barriers to Choice", crit.system_prompt)
        self.assertIn("Tests", crit.system_prompt)
        # Step 6: simulations/fact-check are tests.
        self.assertIn("test", comp.system_prompt.lower())
        self.assertIn("test", fact.system_prompt.lower())
        # Step 7: choose the option with the fewest barriers.
        self.assertIn("fewest barriers", arb.system_prompt.lower())

    def test_critic_prompt_requests_barriers_and_tests(self):
        captured = {}

        class RecordingLLM:
            def invoke(self, messages):
                captured["prompt"] = str(messages)
                class R:
                    content = "ok"
                return R()

        with mock.patch("agents.base.create_llm", return_value=RecordingLLM()):
            from agents.critic import CriticAgent
            CriticAgent().critique({"options": "o"}, {"d": "r"})
        self.assertIn("Barriers to Choice", captured["prompt"])
        self.assertIn("Tests to Run", captured["prompt"])


class TestReportsDir(unittest.TestCase):
    """Generated reports must default to the ./reports directory."""

    def test_default_cli_report_is_under_reports(self):
        from reporting import DEFAULT_OUT
        self.assertEqual(DEFAULT_OUT.parent.name, "reports")
        self.assertEqual(DEFAULT_OUT.name, "strategic-workflow-run.html")

    def test_config_reports_dir(self):
        import os
        from config import Config
        self.assertEqual(Config.REPORTS_DIR, os.getenv("REPORTS_DIR") or "reports")


class TestSearchTools(unittest.TestCase):
    def test_module_imports_without_openai_key(self):
        # Import must succeed even when OPENAI_API_KEY is not set.
        import tools.search_tools  # noqa: F401

    def test_internal_search_graceful_fallback(self):
        from tools import search_tools
        result = search_tools.internal_search("anything")
        self.assertIsInstance(result, str)


class TestEndToEnd(unittest.TestCase):
    def test_full_run_produces_decisions(self):
        with mock.patch("agents.base.create_llm", return_value=FakeLLM()), \
             mock.patch("agents.researcher.web_search", return_value="web snippet"), \
             mock.patch("agents.researcher.internal_search", return_value="internal snippet"), \
             mock.patch("agents.fact_checker.web_search", return_value="web snippet"), \
             mock.patch("agents.fact_checker.internal_search", return_value="internal snippet"):
            wf = StrategicWorkflow()
            result = wf.run(
                "Should we build, acquire, or partner?",
                config={"configurable": {"thread_id": "e2e_test_1"}},
                reviewer=lambda review_data: {"approved": True, "notes": "test"},
            )

        self.assertIsNotNone(result)
        self.assertIn("decisions", result)
        self.assertIn("synthesis", result)
        self.assertEqual(result["current_phase"], "done")
        self.assertTrue(result["research_complete"])


if __name__ == "__main__":
    unittest.main()
