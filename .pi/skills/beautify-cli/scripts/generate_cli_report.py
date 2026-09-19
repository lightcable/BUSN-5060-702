#!/usr/bin/env python3
"""Beautify the Strategic Workflow CLI output into an HTML report.

Thin wrapper around the shared ``reporting`` module. Either beautifies an
already-captured log (``--input``) or runs ``python main.py --no-report`` and
beautifies its live output. ``python main.py`` alone already writes the report,
so this skill is most useful for converting an existing log file.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def find_repo_root():
    """Walk upward from this script until ``main.py`` is found."""
    here = Path(__file__).resolve().parent
    for parent in here.parents:
        if (parent / "main.py").exists() and (parent / "graph" / "workflow.py").exists():
            return parent
    raise SystemExit("Could not locate repo root (main.py not found)")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Beautify python main.py CLI output into HTML."
    )
    parser.add_argument(
        "--input",
        help="Path to an already-captured CLI log (default: run python main.py).",
    )
    parser.add_argument(
        "--out",
        help="Output HTML path (default: <REPORTS_DIR>/strategic-workflow-run.html).",
    )
    parser.add_argument(
        "--question",
        help="The strategic question to show in the report header (optional).",
    )
    args = parser.parse_args(argv)

    root = find_repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # Import after sys.path is set so the shared module resolves from the repo.
    from tools.reporting import write_report
    from tools.config import Config

    errors = ""
    if args.input:
        text = Path(args.input).read_text()
        source = "captured log: " + str(args.input)
    else:
        # Use --no-report because main.py itself already writes the report;
        # here we capture its clean CLI stream and render our own copy.
        proc = subprocess.run(
            [sys.executable, "main.py", "--no-report"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=900,
        )
        text = proc.stdout
        errors = proc.stderr
        source = "live run: python main.py"

    out = Path(args.out) if args.out else root / Config.REPORTS_DIR / "strategic-workflow-run.html"
    # Case sections come from CASE.md (via config) unless overridden.
    path = write_report(
        text,
        source=source,
        out=out,
        errors=errors,
        question=args.question or Config.STRATEGIC_QUESTION,
        attentions=Config.STRATEGIC_ATTENTIONS,
        constraints=Config.STRATEGIC_CONSTRAINTS,
        research_materials=Config.RESEARCH_MATERIALS,
    )
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
