---
name: beautify-cli
description: Beautifies the Strategic Workflow CLI output into a styled, self-contained HTML report (node sections, notices, final recommendation). Markdown comparison tables are reformatted into aligned, readable HTML tables. python main.py already writes this report; use this skill to convert an existing log (--input) or re-render one. Use when asked to beautify, format, or render the terminal output as a web page.
---

# Beautify CLI Output

Turns the plain-text output of `python main.py` into a clean, self-contained
HTML report (no CDN or extra dependencies).

> **Integrated:** `python main.py` now runs the workflow **and** writes the HTML
> report in one step. This skill remains for converting an existing log file
> (or re-rendering one) without re-running the pipeline.

## Usage

```bash
# Beautify an already-captured log (fast, no LLM/network calls)
python .pi/skills/beautify-cli/scripts/generate_cli_report.py --input cli.log

# Re-run the workflow and render a fresh report (uses main.py --no-report)
python .pi/skills/beautify-cli/scripts/generate_cli_report.py

# Choose the output path
python .pi/skills/beautify-cli/scripts/generate_cli_report.py --input cli.log --out custom.html
```

- Default output: `reports/strategic-workflow-run.html`
- Open the file in a browser to view the report.

## What it does

1. Reads a captured log (`--input`) or runs `python main.py --no-report` to
   capture the clean CLI stream.
2. Parses the CLI stream into:
   - `--- node ---` execution sections with `key: value` fields,
   - `[TAG]` run notices (e.g. `[HUMAN REVIEW]`, `[DEMO]`),
   - the `FINAL RECOMMENDATION` and `Strategic Options:` block.
3. Reuses the shared `reporting.py` module to emit a single self-contained HTML
   file with:
   - a summary header (node count, notices, timestamp),
   - collapsible node cards with key/value tables,
   - a notices banner,
   - the case sections (Question, Attentions, Constraints, Research Materials),
   - a lightly markdown-rendered final recommendation where **Markdown tables**
     (e.g. "Side-by-Side Comparison" matrices) are reformatted into aligned HTML
     tables (styled header, zebra striping, per-column alignment, horizontal
     scroll for wide tables) instead of pipe-delimited paragraphs.

## When to run

After `python main.py`, or whenever the user asks to "beautify the CLI output",
"turn the run into an HTML report", or "render the terminal output as a page".
