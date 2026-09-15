"""
Single entry point for the Strategic Workflow.

Running ``python main.py`` does two things in one step:

1. Executes the multi-agent workflow (Orchestrator → Researcher → Synthesizer →
   Critic → Competitor → Arbiter → Human review) and prints the final
   recommendation to the terminal.
2. Captures that CLI output and beautifies it into a self-contained HTML report
   (``reports/strategic-workflow-run.html``) via the shared ``reporting`` module.

Flags:
    --out PATH            Write the HTML report to PATH.
    --no-report           Skip HTML report generation (CLI output only).
    --auto-approve        Auto-approve the human-review step (non-interactive demo).
                          By default the workflow won't pause for an interactive review.
    --auto-gen-graph      Regenerate the workflow graph UI after the run.
    --no-auto-gen-graph   Skip graph UI regeneration (default).
"""

import argparse
import io
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

from graph.workflow import StrategicWorkflow
from reporting import write_report
from config import Config


class Tee:
    """Write to several streams at once (console + capture buffer)."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def main(argv=None):
    """Run the workflow and, unless disabled, write the HTML report."""
    default_out = Path(Config.REPORTS_DIR) / "strategic-workflow-run.html"
    parser = argparse.ArgumentParser(
        description="Run the strategic workflow and write an HTML report."
    )
    parser.add_argument(
        "--out",
        help=f"HTML report output path (default: {default_out})",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip HTML report generation (CLI output only).",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve the human-review step (non-interactive demo).",
    )
    parser.add_argument(
        "--auto-gen-graph",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Regenerate the workflow graph UI after the run (default: off).",
    )
    args = parser.parse_args(argv)

    # The case (question, attentions, constraints, research materials) is read
    # from CASE.md by config.py.
    question = (Config.STRATEGIC_QUESTION or "").strip()
    if not question:
        print("No strategic question found in CASE.md.")
        print("Please set the 'Strategic Question' section in CASE.md and run again.")
        return

    attentions = (Config.STRATEGIC_ATTENTIONS or "").strip()
    constraints = (Config.STRATEGIC_CONSTRAINTS or "").strip()
    research_materials = (Config.RESEARCH_MATERIALS or "").strip()

    # CASE.md requires agents to read the Attentions and Constraints, so both
    # are folded into the brief handed to the workflow.
    brief = question
    if attentions:
        brief = f"{brief}\n\nAttentions:\n{attentions}"
    if constraints:
        brief = f"{brief}\n\nAdditional constraints:\n{constraints}"

    # Record the wall-clock start time for the run metrics.
    started_at = datetime.now()

    # thread_id lets the in-memory checkpointer resume this exact conversation
    # across multiple runs (useful for the human-review interrupt/resume flow).
    config = {"configurable": {"thread_id": "strategy_session_1"}}

    workflow = StrategicWorkflow()

    # Capture everything printed while running, and mirror it to the console.
    captured = io.StringIO()
    with redirect_stdout(Tee(sys.stdout, captured)):
        # Interactive by default: the workflow pauses at the human-review
        # gate. Pass --auto-approve for a non-interactive demo run.
        result = workflow.run(
            brief,
            config,
            auto_approve=args.auto_approve,
            research_materials=research_materials,
        )

        # Timestamp + running time, printed before the final recommendation so
        # the report parser captures it as a run_info section.
        finished_at = datetime.now()
        elapsed_seconds = (finished_at - started_at).total_seconds()
        print("\n--- run_info ---")
        print(f"started_at: {started_at:%Y-%m-%d %H:%M:%S}")
        print(f"finished_at: {finished_at:%Y-%m-%d %H:%M:%S}")
        print(f"elapsed_seconds: {elapsed_seconds:.2f}")

        print("\n" + "=" * 60)
        print("FINAL RECOMMENDATION")
        print("=" * 60)
        if result and result.get("decisions"):
            print(result["decisions"]["decisions"])
        if result and result.get("synthesis"):
            print("\nStrategic Options:\n", result["synthesis"]["options"])

    # Beautify the captured CLI output into an HTML report.
    if not args.no_report:
        report_path = write_report(
            captured.getvalue(),
            source="python main.py",
            out=args.out or default_out,
            question=question,
            constraints=constraints,
            attentions=attentions,
            research_materials=research_materials,
        )
        print(f"\n[report] HTML report written to: {report_path}")

    # Optionally invoke the graph-ui skill to refresh the workflow diagram.
    if args.auto_gen_graph:
        print("\n[graph-ui] Regenerating the workflow graph...")
        repo_root = Path(__file__).resolve().parent
        graph_skill = repo_root / ".pi" / "skills" / "graph-ui" / "scripts" / "generate_graph_ui.py"
        subprocess.run([sys.executable, str(graph_skill)], cwd=repo_root, check=False)


if __name__ == "__main__":
    main()
