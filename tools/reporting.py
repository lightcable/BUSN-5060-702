"""Shared CLI-output beautifier used by ``main.py`` and the ``beautify-cli`` skill.

Parses the workflow's plain-text CLI stream into node sections, run notices, and
the final recommendation, then renders a single self-contained HTML report.
"""

import html as html_mod
import re
from datetime import datetime
from pathlib import Path

# Default report output path (relative to the repo root when running main.py).
DEFAULT_OUT = Path("docs") / "cli-report" / "strategic-workflow-run.html"


def parse_output(text):
    """Parse the CLI stream into node sections, notices, and the final block.

    Returns ``(sections, notices, final)`` where:

    * ``sections`` is a list of ``{"name": str, "fields": [{"key", "value"}, ...]}``,
    * ``notices`` is a list of ``{"tag": str, "text": str}``,
    * ``final`` is ``{"decisions": [line, ...], "options": [line, ...]}``.
    """
    sections = []
    notices = []
    final = {"decisions": [], "options": []}
    current = None
    mode = "node"            # "node" or "final"
    final_part = "decisions"

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if mode == "node":
            # The final banner (===...== or the title) switches to final mode.
            if re.match(r"^={5,}$", stripped) or stripped == "FINAL RECOMMENDATION":
                mode = "final"
                final_part = "decisions"
                continue
            if stripped == "":
                continue
            # "--- node ---" starts a new node section.
            m = re.match(r"^--- (.+?) ---$", stripped)
            if m:
                current = {"name": m.group(1).strip(), "fields": []}
                sections.append(current)
                continue
            # "[TAG] message" is a run-level notice.
            nm = re.match(r"^\[(.+?)\]\s*(.*)$", stripped)
            if nm:
                notices.append({"tag": nm.group(1), "text": nm.group(2)})
                continue
            # "key: value" is a field emitted by the current node.
            kv = re.match(r"^([A-Za-z_][\w]*):\s*(.*)$", stripped)
            if kv:
                if current is None:
                    current = {"name": "_preamble", "fields": []}
                    sections.append(current)
                current["fields"].append({"key": kv.group(1), "value": kv.group(2)})
                continue
            continue  # ignore any other line in node mode

        # Final mode: keep everything except banner bars/titles.
        if re.match(r"^={5,}$", stripped) or stripped == "FINAL RECOMMENDATION":
            continue
        if stripped == "Strategic Options:":
            final_part = "options"
            continue
        final[final_part].append(line)

    return sections, notices, final


def inline_md(text):
    """Apply the small Markdown subset the LLM output uses (escape first)."""
    s = html_mod.escape(text)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


_TABLE_SEP_CELL = re.compile(r"^:?-{2,}:?$")


def _split_table_row(line):
    """Split a Markdown table row into trimmed cells."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def _is_separator_row(line):
    """True for a Markdown table separator row (e.g. ``| --- | :--: |``)."""
    if "|" not in line:
        return False
    cells = _split_table_row(line)
    return bool(cells) and all(_TABLE_SEP_CELL.match(cell) for cell in cells)


def _column_alignments(separator_cells):
    """Derive per-column alignment from the separator row's colons."""
    alignments = []
    for cell in separator_cells:
        if cell.startswith(":") and cell.endswith(":"):
            alignments.append("center")
        elif cell.endswith(":"):
            alignments.append("right")
        else:
            alignments.append("left")
    return alignments


def _render_table(header, alignments, rows):
    """Render a Markdown table as a clean, aligned HTML table."""
    def cell(tag, content, index):
        alignment = alignments[index] if index < len(alignments) else "left"
        style = f' style="text-align:{alignment}"' if alignment != "left" else ""
        return f"<{tag}{style}>{inline_md(content)}</{tag}>"

    head = "<tr>" + "".join(cell("th", c, i) for i, c in enumerate(header)) + "</tr>"
    body = ""
    width = len(header)
    for row in rows:
        row = (row + [""] * width)[:width]
        body += "<tr>" + "".join(cell("td", c, i) for i, c in enumerate(row)) + "</tr>"
    return (
        '<div class="table-wrap"><table class="md-table"><thead>'
        + head + "</thead><tbody>" + body + "</tbody></table></div>"
    )


def render_markdown(lines):
    """Render a list of lines as light HTML (headings, lists, tables, paragraphs).

    Markdown tables (including "side-by-side comparison" matrices) are rendered
    as real aligned HTML tables instead of pipe-delimited paragraphs.
    """
    out = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    index = 0
    total = len(lines)
    while index < total:
        stripped = lines[index].strip()
        if stripped == "":
            close_list()
            index += 1
            continue

        # Markdown table: a header row followed by a separator row.
        if "|" in stripped and index + 1 < total and _is_separator_row(lines[index + 1]):
            close_list()
            header = _split_table_row(stripped)
            alignments = _column_alignments(_split_table_row(lines[index + 1]))
            rows = []
            index += 2
            while index < total and lines[index].strip() and "|" in lines[index]:
                rows.append(_split_table_row(lines[index]))
                index += 1
            out.append(_render_table(header, alignments, rows))
            continue

        if stripped.startswith("### "):
            close_list()
            out.append("<h4>" + inline_md(stripped[4:]) + "</h4>")
        elif stripped.startswith("## "):
            close_list()
            out.append("<h3>" + inline_md(stripped[3:]) + "</h3>")
        elif stripped.startswith("# "):
            close_list()
            out.append("<h3>" + inline_md(stripped[2:]) + "</h3>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + inline_md(stripped[2:]) + "</li>")
        else:
            close_list()
            out.append("<p>" + inline_md(stripped) + "</p>")
        index += 1

    close_list()
    return "\n".join(out)


def render_node(section):
    """Render one node section as a collapsible card."""
    name = section["name"] if section["name"] != "_preamble" else "Run preamble"
    rows = []
    for f in section["fields"]:
        rows.append(
            '<tr><td class="key">' + html_mod.escape(f["key"]) +
            '</td><td class="val"><code>' + html_mod.escape(f["value"]) + "</code></td></tr>"
        )
    table = (
        "<table>" + "".join(rows) + "</table>"
        if rows
        else '<p class="empty">(no fields)</p>'
    )
    return (
        '<details class="node" open><summary><span class="node-name">' +
        html_mod.escape(name) + '</span><span class="count">' +
        str(len(section["fields"])) + " field(s)</span></summary>" + table + "</details>"
    )


def render_notices(notices):
    """Render run notices as a banner list."""
    if not notices:
        return ""
    items = "".join(
        '<div class="notice"><span class="tag">' + html_mod.escape(n["tag"]) +
        '</span> ' + html_mod.escape(n["text"]) + "</div>"
        for n in notices
    )
    return '<section class="notices"><h2>Run notices</h2>' + items + "</section>"


def render_final(final):
    """Render the final recommendation block."""
    decisions = render_markdown(final["decisions"]) if final["decisions"] else '<p class="empty">(none)</p>'
    options = render_markdown(final["options"]) if final["options"] else '<p class="empty">(none)</p>'
    return (
        '<section class="final"><h2>Final Recommendation</h2>'
        '<div class="final-block"><h3>Decisions</h3><div class="md">' + decisions + "</div></div>"
        '<div class="final-block"><h3>Strategic Options</h3><div class="md">' + options + "</div></div>"
        "</section>"
    )


CSS = r"""
:root { --bg:#f6f8fb; --panel:#ffffff; --border:#e2e8f0; --text:#0f172a; --muted:#64748b; --accent:#2563eb; --accent2:#0f766e; }
* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--text); }
header { background:linear-gradient(135deg,#1e3a8a,#0f766e); color:#fff; padding:1.4rem 1.5rem; }
header h1 { margin:0 0 .3rem; font-size:1.3rem; }
header p { margin:0; opacity:.85; font-size:.9rem; }
.meta { display:flex; flex-wrap:wrap; gap:.5rem; margin-top:.8rem; }
.chip { background:rgba(255,255,255,.15); border:1px solid rgba(255,255,255,.25); border-radius:999px; padding:.15rem .7rem; font-size:.8rem; }
main { max-width:960px; margin:1.2rem auto; padding:0 1rem 3rem; }
section { margin-bottom:1.5rem; }
h2 { font-size:1.05rem; border-bottom:2px solid var(--border); padding-bottom:.35rem; }
details.node { background:var(--panel); border:1px solid var(--border); border-radius:10px; margin-bottom:.6rem; overflow:hidden; }
details.node summary { cursor:pointer; padding:.6rem .9rem; display:flex; justify-content:space-between; align-items:center; font-weight:600; }
details.node summary:hover { background:#f1f5f9; }
.node-name { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
.count { color:var(--muted); font-size:.78rem; font-weight:500; }
details.node table { width:100%; border-collapse:collapse; font-size:.85rem; }
details.node td { border-top:1px solid var(--border); padding:.5rem .9rem; vertical-align:top; }
td.key { width:190px; color:var(--accent); font-weight:600; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
td.val code { display:block; white-space:pre-wrap; word-break:break-word; color:#334155; font-size:.8rem; }
.empty { color:var(--muted); font-size:.85rem; }
.notices { background:#fffbeb; border:1px solid #fcd34d; border-radius:10px; padding:.8rem 1rem; }
.notices h2 { border:none; margin:0 0 .5rem; font-size:.95rem; color:#92400e; }
.notice { margin:.3rem 0; font-size:.88rem; }
.notice .tag { display:inline-block; background:#f59e0b; color:#fff; border-radius:6px; padding:0 .5rem; font-size:.72rem; font-weight:700; margin-right:.4rem; }
.final { background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:1rem 1.2rem; }
.final-block { margin-top:.8rem; }
.final-block h3 { color:var(--accent2); font-size:.95rem; margin:.4rem 0; }
.md h4 { margin:.8rem 0 .3rem; color:#1e3a8a; }
.md h3 { margin:.8rem 0 .3rem; color:#1e3a8a; }
.md p { margin:.4rem 0; line-height:1.5; }
.md ul { margin:.4rem 0 .4rem 1.2rem; padding:0; }
.md li { margin:.2rem 0; line-height:1.45; }
.md code { background:#f1f5f9; border-radius:4px; padding:.05rem .3rem; font-size:.88em; }
/* Markdown tables (e.g. side-by-side comparison matrices) */
.table-wrap { overflow-x:auto; margin:.7rem 0; }
.md-table { border-collapse:collapse; width:100%; font-size:.82rem; }
.md-table th, .md-table td { border:1px solid #cbd5e1; padding:.45rem .6rem; vertical-align:top; text-align:left; }
.md-table thead th { background:#0f766e; color:#fff; position:sticky; top:0; font-weight:600; white-space:nowrap; }
.md-table tbody tr:nth-child(even) { background:#f8fafc; }
.md-table tbody tr:hover { background:#f0fdfa; }
.md-table td:first-child { font-weight:600; color:#0f172a; }
.errors pre { background:#fef2f2; border:1px solid #fca5a5; border-radius:10px; padding:1rem; white-space:pre-wrap; font-size:.82rem; }
.question pre { background:#eff6ff; border:1px solid #bfdbfe; border-radius:10px; padding:1rem; white-space:pre-wrap; font-size:.88rem; color:#1e3a8a; }
.constraints pre { background:#fffbeb; border:1px solid #fcd34d; border-radius:10px; padding:1rem; white-space:pre-wrap; font-size:.88rem; color:#92400e; }
.attentions pre { background:#f0fdfa; border:1px solid #5eead4; border-radius:10px; padding:1rem; white-space:pre-wrap; font-size:.88rem; color:#115e59; }
.materials pre { background:#f8fafc; border:1px solid #cbd5e1; border-radius:10px; padding:1rem; white-space:pre-wrap; font-size:.82rem; color:#334155; }
.models table { width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--border); border-radius:10px; overflow:hidden; font-size:.88rem; }
.models th { background:#f0fdfa; text-align:left; }
.models th, .models td { border-bottom:1px solid var(--border); padding:.5rem .9rem; }
.models code { background:#f1f5f9; border-radius:4px; padding:.05rem .4rem; }
footer { color:var(--muted); font-size:.8rem; text-align:center; padding:1rem; }
"""


def extract_tokens(sections):
    """Return token-usage totals if a ``token_usage`` section was parsed."""
    for section in sections:
        if section["name"] == "token_usage":
            fields = {f["key"]: f["value"] for f in section["fields"]}
            return {
                "input": fields.get("input_tokens", "0"),
                "output": fields.get("output_tokens", "0"),
                "total": fields.get("total_tokens", "0"),
                "calls": fields.get("llm_calls", "0"),
                "cost": fields.get("estimated_cost_usd", "0"),
            }
    return None


def extract_run_info(sections):
    """Return run timing if a ``run_info`` section was parsed."""
    for section in sections:
        if section["name"] == "run_info":
            fields = {f["key"]: f["value"] for f in section["fields"]}
            return {
                "started": fields.get("started_at", ""),
                "finished": fields.get("finished_at", ""),
                "elapsed": fields.get("elapsed_seconds", ""),
            }
    return None


def extract_agent_models(sections):
    """Return an ordered (agent, model) list if an ``agent_models`` section exists."""
    for section in sections:
        if section["name"] == "agent_models":
            return [(f["key"], f["value"]) for f in section["fields"]]
    return []


def build_html(sections, notices, final, meta, errors="", tokens=None, question=None, run_info=None, constraints=None, agent_models=None, attentions=None, research_materials=None):
    """Assemble the full self-contained HTML document."""
    nodes_html = "".join(render_node(s) for s in sections)
    notices_html = render_notices(notices)
    final_html = render_final(final)
    errors_html = ""
    if errors:
        errors_html = (
            '<section class="errors"><h2>Errors (stderr)</h2><pre>' +
            html_mod.escape(errors) + "</pre></section>"
        )
    question_html = ""
    if question:
        question_html = (
            '<section class="question"><h2>Strategic Question</h2><pre>' +
            html_mod.escape(question.strip()) + "</pre></section>"
        )
    attentions_html = ""
    if attentions:
        attentions_html = (
            '<section class="attentions"><h2>Attentions</h2><pre>' +
            html_mod.escape(attentions.strip()) + "</pre></section>"
        )
    constraints_html = ""
    if constraints:
        constraints_html = (
            '<section class="constraints"><h2>Strategic Constraints</h2><pre>' +
            html_mod.escape(constraints.strip()) + "</pre></section>"
        )
    materials_html = ""
    if research_materials:
        materials_html = (
            '<section class="materials"><h2>Research Materials</h2><pre>' +
            html_mod.escape(research_materials.strip()) + "</pre></section>"
        )
    models_html = ""
    if agent_models:
        rows = "".join(
            "<tr><td>" + html_mod.escape(agent) + "</td><td><code>" +
            html_mod.escape(model) + "</code></td></tr>"
            for agent, model in agent_models
        )
        models_html = (
            '<section class="models"><h2>AI Models (reference)</h2>'
            "<table><thead><tr><th>Agent</th><th>Model</th></tr></thead><tbody>"
            + rows + "</tbody></table></section>"
        )
    token_chips = ""
    if tokens:
        token_chips = (
            '<span class="chip">input tokens: ' + str(tokens["input"]) + "</span>"
            '<span class="chip">output tokens: ' + str(tokens["output"]) + "</span>"
            '<span class="chip">total tokens: ' + str(tokens["total"]) + "</span>"
            '<span class="chip">llm calls: ' + str(tokens["calls"]) + "</span>"
            '<span class="chip">est. cost: $' + str(tokens["cost"]) + "</span>"
        )
    run_chips = ""
    if run_info:
        run_chips = (
            '<span class="chip">duration: ' + str(run_info["elapsed"]) + "s</span>"
            '<span class="chip">started: ' + str(run_info["started"]) + "</span>"
        )
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Strategic Workflow — Run Report</title><style>" + CSS + "</style></head><body>"
        "<header><h1>Strategic Workflow — Run Report</h1><p>" +
        html_mod.escape(meta["source"]) + " · " + meta["timestamp"] + "</p>"
        '<div class="meta">'
        '<span class="chip">' + str(len(sections)) + " node sections</span>"
        '<span class="chip">' + str(len(notices)) + " notices</span>"
        + run_chips
        + token_chips
        + '<span class="chip">decisions: ' + ("yes" if final["decisions"] else "no") + "</span>"
        '<span class="chip">options: ' + ("yes" if final["options"] else "no") + "</span>"
        "</div></header><main>"
        + question_html
        + attentions_html
        + constraints_html
        + materials_html
        + models_html
        + errors_html
        + notices_html
        + '<section class="execution"><h2>Execution</h2>' + nodes_html + "</section>"
        + final_html
        + "</main><footer>Generated by the integrated <code>main.py</code> / "
        "<code>beautify-cli</code> report pipeline</footer></body></html>"
    )


def write_report(text, source, out=None, errors="", question=None, constraints=None, agent_models=None, attentions=None, research_materials=None):
    """Parse ``text`` and write the HTML report.

    Returns the resolved output ``Path``.
    """
    sections, notices, final = parse_output(text)
    meta = {
        "source": source,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    tokens = extract_tokens(sections)
    run_info = extract_run_info(sections)
    agent_models = agent_models if agent_models is not None else extract_agent_models(sections)
    html_doc = build_html(
        sections, notices, final, meta,
        errors=errors, tokens=tokens, question=question, run_info=run_info,
        constraints=constraints, agent_models=agent_models,
        attentions=attentions, research_materials=research_materials,
    )

    out = Path(out) if out else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc)
    return out
