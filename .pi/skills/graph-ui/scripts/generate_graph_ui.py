#!/usr/bin/env python3
"""Generate an interactive HTML graph UI for the Strategic Workflow.

Parses ``graph/workflow.py`` to extract nodes, return edges, and the
Orchestrator's phase->node routing, then emits a single self-contained HTML page
(inline SVG + vanilla JS, no CDN) showing:

* the hub-and-spoke agent interaction graph (nodes + directed edges), and
* an execution timeline (steps + the messages exchanged between nodes) with
  time as a dimension, plus playback controls that animate the flow.
"""

import json
import math
import re
import sys
from pathlib import Path

# Phases in the order the workflow traverses them; used to lay out the targets
# clockwise and to label the outgoing edges.
PHASE_ORDER = [
    "research",
    "synthesis",
    "fact_check",
    "critique",
    "competitor",
    "arbitration",
    "human_review",
    "done",
]

# Human-readable descriptions shown in the click-to-inspect info panel.
NODE_INFO = {
    "orchestrator_plan": "Plans research domains on first entry, then routes to the next agent based on the current phase.",
    "researcher": "Gathers public (DuckDuckGo) and internal intelligence for each research domain.",
    "synthesizer": "Combines research reports into 3-5 distinct strategic options.",
    "fact_check": "Fact-checks each option's material claims against evidence; fails unsupported/contradicted claims.",
    "critic": "Devil's-advocate critique of each option against the research.",
    "competitor": "Simulates competitor, customer, regulator, and partner reactions.",
    "arbiter": "Issues PASS / FAIL / PARTIAL decisions per option.",
    "human_review": "Pauses for human approval; approves or sends the run back to synthesis.",
    "END": "Terminal state reached when the phase is 'done'.",
}

# Per-node input messages and output messages (what each node reads and writes).
# Shown in the node info panel and during timeline playback.
NODE_IO = {
    "orchestrator_plan": {
        "inputs": ["strategic_question (question+attentions+constraints)", "current_phase", "research_domains"],
        "outputs": ["research_domains (plan)", "dispatch next node via current_phase"],
    },
    "researcher": {
        "inputs": ["strategic_question", "research_domains", "research_materials (CASE.md)"],
        "outputs": ["research_reports", "research_complete", "current_phase=synthesis"],
    },
    "synthesizer": {
        "inputs": ["research_reports", "strategic_question", "fact_check feedback (revision)"],
        "outputs": ["synthesis (options)", "current_phase=fact_check"],
    },
    "fact_check": {
        "inputs": ["synthesis (options)", "research_reports", "research_materials"],
        "outputs": ["fact_check (PASS/FAIL verdict)", "current_phase=critique (pass) | synthesis (fail)"],
    },
    "critic": {
        "inputs": ["synthesis", "research_reports"],
        "outputs": ["critique", "current_phase=competitor"],
    },
    "competitor": {
        "inputs": ["synthesis", "critique"],
        "outputs": ["simulations", "current_phase=arbitration"],
    },
    "arbiter": {
        "inputs": ["synthesis", "critique", "simulations"],
        "outputs": ["decisions", "current_phase=human_review"],
    },
    "human_review": {
        "inputs": ["decisions", "synthesis", "critique", "simulations"],
        "outputs": [
            "current_phase=done (approve)",
            "current_phase=synthesis + iteration (revise)",
            "messages",
        ],
    },
    "END": {
        "inputs": ["final state"],
        "outputs": [],
    },
}

# Visual role of each node (hub = center, gate = human review, end = terminal).
NODE_KIND = {
    "orchestrator_plan": "hub",
    "human_review": "gate",
    "END": "end",
}

# What the project is trying to do, shown as an objective card on the graph.
PROJECT = {
    "objective": (
        "Turn a high-level strategic business question (e.g. build, acquire, or "
        "partner for AI capabilities) into research, strategic options, "
        "adversarial critique, competitive simulation, and a defensible "
        "recommendation."
    ),
    "pipeline": [
        "research", "synthesis", "fact_check", "critique", "competitor", "arbitration", "human_review",
    ],
}


def find_repo_root():
    """Walk upward from this script until ``graph/workflow.py`` is found."""
    here = Path(__file__).resolve().parent
    for parent in here.parents:
        if (parent / "graph" / "workflow.py").exists():
            return parent
    raise SystemExit("Could not locate repo root (graph/workflow.py not found)")


def parse_workflow(source, orchestrator_source):
    """Extract nodes, edges, routing, hub, and human-review edges.

    Nodes and the hub come from ``graph/workflow.py``; the phase->node routing
    labels come from ``OrchestratorAgent.PHASE_TO_NODE`` in
    ``agents/orchestrator.py``.
    """
    nodes = re.findall(r'add_node\(\s*"([^"]+)"', source)

    # Plain return edges: both literal add_edge("a","b") and the loop form
    # ``for node in ("researcher", ...): workflow.add_edge(node, hub)``.
    plain_edges = re.findall(r'add_edge\(\s*"([^"]+)"\s*,\s*"([^"]+)"', source)
    loop = re.search(
        r'for\s+node\s+in\s*\((.*?)\):\s*\n\s*workflow\.add_edge\(node,\s*"([^"]+)"\)',
        source,
        re.S,
    )
    if loop:
        for name in re.findall(r'"([^"]+)"', loop.group(1)):
            plain_edges.append((name, loop.group(2)))

    # phase -> node routing (used for edge labels and the timeline).
    routing = {}
    routing_match = re.search(r'PHASE_TO_NODE\s*=\s*\{(.*?)\n\s*\}', orchestrator_source, re.S)
    if routing_match:
        routing = dict(re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', routing_match.group(1)))

    hub_match = re.search(r'add_conditional_edges\(\s*\n?\s*"([^"]+)"', source)
    hub = hub_match.group(1) if hub_match else "orchestrator_plan"

    # human_review conditional edges, e.g. {"finish": END, "revise": "orchestrator_plan"}.
    human_edges = {}
    hm = re.search(
        r'add_conditional_edges\(\s*\n?\s*"human_review"\s*,\s*\n?\s*[^,\n]+\s*,\s*\n?\s*\{(.*?)\}\s*\)',
        source,
        re.S,
    )
    if hm:
        for key, val in re.findall(r'"([^"]+)"\s*:\s*(END|"[^"]+")', hm.group(1)):
            human_edges[key] = "END" if val == "END" else val.strip('"')

    return nodes, plain_edges, routing, hub, human_edges


def load_agent_models(root):
    """Return node-name -> LLM model name from the project's env-driven config.

    Reads ``Config.AGENT_MODELS`` / ``Config.MODELS`` (which come from ``.env``)
    so the diagram reflects the same per-role model assignments the workflow
    uses. Falls back to ``{}`` (no model info) if config/.env is unavailable, so
    the skill still runs standalone.
    """
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from config import Config  # imported lazily; requires the project config
    except Exception:
        return {}

    def model_for(agent):
        profile = Config.AGENT_MODELS.get(agent) or Config.DEFAULT_MODEL
        entry = Config.MODELS.get(profile) or {}
        return entry.get("model") or ""

    return {
        "orchestrator_plan": model_for("orchestrator"),
        "researcher": model_for("researcher"),
        "synthesizer": model_for("synthesizer"),
        "fact_check": model_for("fact_check"),
        "critic": model_for("critic"),
        "competitor": model_for("competitor"),
        "arbiter": model_for("arbiter"),
        "human_review": "n/a (no LLM call)",
        "END": "—",
    }


def build_graph(nodes, plain_edges, routing, hub, human_edges, models=None):
    """Assemble node/edge records with radial layout coordinates."""
    def target_of(name):
        return "END" if name == "finish" else name

    # Union of every node mentioned anywhere in the workflow.
    all_nodes = set(nodes) | {hub} | {"END"}
    for target in routing.values():
        all_nodes.add(target_of(target))
    for src, dst in plain_edges:
        all_nodes |= {src, target_of(dst)}

    # Order the radial targets by the workflow's phase sequence so the diagram
    # reads clockwise in execution order.
    targets = []
    for phase in PHASE_ORDER:
        if phase in routing:
            node = target_of(routing[phase])
            if node not in targets:
                targets.append(node)
    for node in sorted(all_nodes):
        if node != hub and node not in targets:
            targets.append(node)

    # Deterministic radial layout: hub in the center, targets on a circle.
    cx, cy, radius = 480, 320, 240
    positions = {hub: (cx, cy)}
    count = len(targets)
    for i, node in enumerate(targets):
        angle = math.radians(-90 + i * (360.0 / count))
        positions[node] = (
            cx + radius * math.cos(angle),
            cy + radius * math.sin(angle),
        )

    node_records = []
    for name in sorted(all_nodes, key=lambda s: (s != hub, s)):
        x, y = positions[name]
        io = NODE_IO.get(name, {"inputs": [], "outputs": []})
        node_records.append({
            "id": name,
            "label": name,
            "kind": NODE_KIND.get(name, "agent"),
            "x": round(x, 1),
            "y": round(y, 1),
            "info": NODE_INFO.get(name, "No description provided."),
            "inputs": io["inputs"],
            "outputs": io["outputs"],
            "model": (models or {}).get(name, ""),
        })

    edge_records = []
    # Outgoing phase-routed edges from the hub for research..human_review.
    # ("done" is not routed from the hub: human_review -> END handles approval.)
    for phase in PHASE_ORDER[:-1]:
        if phase not in routing:
            continue
        edge_records.append({
            "from": hub,
            "to": target_of(routing[phase]),
            "label": phase,
            "kind": "route",
        })
    # Return edges: every plain edge is agent -> orchestrator.
    for src, dst in plain_edges:
        edge_records.append({
            "from": src,
            "to": target_of(dst),
            "label": "",
            "kind": "return",
        })
    # human_review conditional edges: approve -> END, revise -> orchestrator.
    for key, target in human_edges.items():
        edge_records.append({
            "from": "human_review",
            "to": target_of(target),
            "label": "approve" if key == "finish" else key,
            "kind": "route" if key == "finish" else "return",
        })

    return {"nodes": node_records, "edges": edge_records, "hub": hub}


def build_trace(routing, hub):
    """Build the ordered execution steps (messages exchanged over time).

    Mirrors ``graph/workflow.py``'s fixed pipeline: the Orchestrator plans
    domains, each agent runs and returns a message, and the Orchestrator routes
    to the next phase. Each step maps 1:1 onto a graph edge.
    """
    def target_of(name):
        return "END" if name == "finish" else name

    trace = []

    # Step 1: entry — Orchestrator plans the research domains.
    trace.append({
        "from": hub,
        "to": target_of(routing.get("research", "researcher")),
        "message": "plans research_domains (3-5 domains)",
        "phase": "research",
        "kind": "route",
    })

    # Each agent: runs -> returns a message to the hub -> hub routes onward.
    agents = [
        ("researcher", "research_reports", "synthesis"),
        ("synthesizer", "synthesis (options)", "fact_check"),
        ("fact_check", "fact_check (PASS/FAIL verdict)", "critique"),
        ("critic", "critique", "competitor"),
        ("competitor", "simulations", "arbitration"),
        ("arbiter", "decisions", "human_review"),
    ]
    for agent, field, next_phase in agents:
        trace.append({
            "from": agent,
            "to": hub,
            "message": "emits " + field + " · sets phase=" + next_phase,
            "phase": next_phase,
            "kind": "return",
        })
        trace.append({
            "from": hub,
            "to": target_of(routing.get(next_phase, agent)),
            "message": "routes on phase=" + next_phase,
            "phase": next_phase,
            "kind": "route",
        })

    # Final step: human review approves and the graph ends.
    trace.append({
        "from": "human_review",
        "to": "END",
        "message": "emits interrupt → approve · sets phase=done",
        "phase": "done",
        "kind": "route",
    })

    return trace


# Single self-contained HTML template. __GRAPH_DATA__ is replaced at generation
# time with the parsed graph JSON (JSON is valid JavaScript object syntax).
TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Strategic Workflow — Node & Edge Interaction</title>
<style>
  :root {
    --bg: #f8fafc; --panel: #ffffff; --border: #e2e8f0; --text: #0f172a; --muted: #64748b;
    --hub: #1d4ed8; --agent: #dcfce7; --agent-line: #16a34a; --agent-text: #14532d;
    --gate: #fef3c7; --gate-line: #d97706; --gate-text: #92400e;
    --end: #f1f5f9; --end-line: #64748b; --end-text: #334155;
    --route: #2563eb; --return: #94a3b8; --step: #f59e0b;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); }
  header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; padding: .8rem 1.25rem; background: var(--panel); border-bottom: 1px solid var(--border); }
  header h1 { margin: 0 0 .25rem; font-size: 1.15rem; }
  header p { margin: 0; color: var(--muted); font-size: .85rem; max-width: 60ch; }
  #toolbar { display: flex; gap: .35rem; flex-shrink: 0; }
  #toolbar button { border: 1px solid var(--border); background: #fff; border-radius: 8px; padding: .35rem .7rem; font-size: .85rem; cursor: pointer; }
  #toolbar button:hover { background: #f1f5f9; }
  #stage { position: relative; height: calc(100vh - 240px); min-height: 320px; display: flex; }
  #graph { flex: 1; height: 100%; cursor: grab; }
  #graph:active { cursor: grabbing; }
  #info { width: 320px; padding: 1rem; background: var(--panel); border-left: 1px solid var(--border); overflow: auto; }
  #info .placeholder { color: var(--muted); font-size: .9rem; }
  #info h2 { margin: 0 0 .4rem; font-size: 1rem; word-break: break-word; }
  #info h3 { margin: 1rem 0 .3rem; font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
  #info p { margin: 0 0 .5rem; font-size: .88rem; color: #334155; }
  #info ul { margin: 0; padding-left: 1.1rem; font-size: .85rem; }
  #info li { margin: .15rem 0; }
  #info em { color: var(--route); font-style: normal; font-weight: 600; }
  #legend { position: absolute; left: 1rem; bottom: 1rem; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: .7rem .9rem; font-size: .8rem; box-shadow: 0 1px 4px rgba(15,23,42,.08); }
  #legend .row { display: flex; align-items: center; gap: .5rem; margin: .25rem 0; }
  #legend .swatch { width: 14px; height: 14px; border-radius: 4px; border: 1px solid rgba(0,0,0,.15); }
  #legend .line { width: 18px; height: 0; border-top: 2px solid var(--route); }
  #legend .line.return { border-top-style: dashed; border-top-color: var(--return); }
  .node rect { stroke: var(--agent-line); stroke-width: 2; fill: var(--agent); }
  .node.hub rect { stroke: var(--hub); fill: var(--hub); }
  .node.gate rect { stroke: var(--gate-line); fill: var(--gate); }
  .node.end rect { stroke: var(--end-line); fill: var(--end); }
  .node text { font: 600 12px system-ui, sans-serif; fill: var(--agent-text); pointer-events: none; }
  .node.hub text { fill: #ffffff; }
  .node.gate text { fill: var(--gate-text); }
  .node.end text { fill: var(--end-text); }
  .node { cursor: pointer; transition: opacity .15s ease; }
  .node.dim { opacity: .22; }
  .node.selected rect { stroke-width: 4; }
  .node.step-active rect { stroke: var(--step); stroke-width: 5; }
  .edge { fill: none; stroke: var(--return); stroke-width: 1.6; opacity: .9; }
  .edge.route { stroke: var(--route); stroke-width: 2; }
  .edge.active { stroke-width: 3.5; }
  .edge.dim { opacity: .12; }
  .edge.step-active { stroke: var(--step) !important; stroke-width: 3.5; }
  .edge-label { font: 500 11px system-ui, sans-serif; fill: var(--route); pointer-events: none; }

  /* --- project objective card --- */
  #objective { position: absolute; top: 1rem; left: 1rem; max-width: 360px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: .8rem 1rem; box-shadow: 0 1px 6px rgba(15,23,42,.08); font-size: .82rem; z-index: 2; }
  #objective h2 { margin: 0 0 .35rem; font-size: .9rem; }
  #objective p { margin: 0 0 .5rem; color: #334155; }
  #objective .pipeline { display: flex; flex-wrap: wrap; align-items: center; gap: .25rem; }
  #objective .phase-pill { background: #dbeafe; color: #1e40af; border-radius: 999px; padding: .05rem .55rem; font-size: .72em; font-weight: 600; }
  #objective .arrow { color: var(--muted); }

  /* --- timeline (time dimension) --- */
  #timelinePanel { height: 168px; border-top: 1px solid var(--border); background: var(--panel); display: flex; flex-direction: column; }
  #playbackBar { display: flex; align-items: center; gap: .6rem; padding: .5rem 1rem; border-bottom: 1px solid var(--border); font-size: .82rem; color: var(--muted); }
  #playbackBar button { border: 1px solid var(--border); background: #fff; border-radius: 8px; padding: .3rem .6rem; cursor: pointer; font-size: .85rem; }
  #playbackBar button:hover { background: #f1f5f9; }
  #playbackBar input[type=range] { flex: 1; max-width: 320px; }
  #stepLabel { min-width: 150px; }
  #stepStrip { display: flex; gap: .6rem; padding: .6rem 1rem; overflow-x: auto; flex: 1; align-items: stretch; }
  .step-card { min-width: 220px; max-width: 220px; border: 1px solid var(--border); border-radius: 10px; padding: .5rem .7rem; background: #fff; cursor: pointer; font-size: .78rem; flex-shrink: 0; transition: border-color .15s, box-shadow .15s; }
  .step-card:hover { border-color: var(--route); }
  .step-card.active { border-color: var(--step); box-shadow: 0 0 0 2px rgba(245,158,11,.28); }
  .step-card .step-num { font-weight: 700; color: var(--route); }
  .step-card .step-phase { display: inline-block; background: #dbeafe; color: #1e40af; border-radius: 999px; padding: 0 .5rem; font-size: .7em; margin-left: .3rem; }
  .step-card .step-msg { color: #334155; margin: .3rem 0; }
  .step-card .step-route { color: var(--muted); font-size: .72rem; }
  .step-card .step-model { color: #7c3aed; font-size: .72rem; margin-top: .15rem; }
</style>
</head>
<body>
<header>
  <div>
    <h1>Strategic Workflow — Node &amp; Edge Interaction</h1>
    <p>Hub-and-spoke LangGraph state machine. Hover a node to highlight its edges; click to inspect. The timeline below shows the execution steps and the messages exchanged between nodes over time — press ▶ to animate. Scroll to zoom, drag to pan.</p>
  </div>
  <div id="toolbar">
    <button id="zoomIn" title="Zoom in">+</button>
    <button id="zoomOut" title="Zoom out">−</button>
    <button id="reset" title="Reset view">Reset</button>
  </div>
</header>
<div id="stage">
  <svg id="graph" viewBox="0 0 960 640" preserveAspectRatio="xMidYMid meet">
    <defs>
      <marker id="arrow-route" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse" orient="auto">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#2563eb"/>
      </marker>
      <marker id="arrow-return" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse" orient="auto">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8"/>
      </marker>
    </defs>
  </svg>
  <div id="objective">
    <h2>🎯 What this project does</h2>
    <p id="objectiveText"></p>
    <div class="pipeline" id="objectivePipeline"></div>
  </div>
  <aside id="info"><div class="placeholder">Click a node to inspect it — or press ▶ to watch the steps and messages flow over time.</div></aside>
  <div id="legend">
    <div class="row"><span class="swatch" style="background:#1d4ed8"></span> Orchestrator (hub)</div>
    <div class="row"><span class="swatch" style="background:#dcfce7;border-color:#16a34a"></span> Agent node</div>
    <div class="row"><span class="swatch" style="background:#fef3c7;border-color:#d97706"></span> Human review (gate)</div>
    <div class="row"><span class="swatch" style="background:#f1f5f9;border-color:#64748b"></span> END (terminal)</div>
    <div class="row"><span class="line"></span> Phase-routed edge</div>
    <div class="row"><span class="line return"></span> Return edge (message)</div>
    <div class="row"><span class="swatch" style="background:#f59e0b"></span> Active step (time)</div>
  </div>
</div>
<div id="timelinePanel">
  <div id="playbackBar">
    <button id="stepPrev" title="Previous step">⏮</button>
    <button id="playPause" title="Play / pause">▶</button>
    <button id="stepNext" title="Next step">⏭</button>
    <input type="range" id="stepSlider" min="0" max="0" value="0">
    <span id="stepLabel">step 0 / 0</span>
  </div>
  <div id="stepStrip"></div>
</div>
<script>
(function () {
  const DATA = __GRAPH_DATA__;
  const TRACE = DATA.trace || [];
  const svg = document.getElementById('graph');
  const NS = 'http://www.w3.org/2000/svg';
  const viewport = document.createElementNS(NS, 'g');
  viewport.setAttribute('id', 'viewport');
  svg.appendChild(viewport);

  const nodeById = {};
  DATA.nodes.forEach(function (n) { nodeById[n.id] = n; });

  // Approximate node radius used to trim edges so arrowheads stop at the border.
  const dims = {
    hub: { w: 170, h: 46, r: 78 },
    agent: { w: 128, h: 44, r: 60 },
    gate: { w: 128, h: 44, r: 60 },
    end: { w: 90, h: 44, r: 44 }
  };
  function dimOf(n) { return dims[n.kind] || dims.agent; }

  function trim(a, b, rA, rB) {
    const dx = b.x - a.x, dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len;
    return { sx: a.x + ux * rA, sy: a.y + uy * rA, ex: b.x - ux * rB, ey: b.y - uy * rB };
  }

  // --- nodes ---
  DATA.nodes.forEach(function (n) {
    const d = dimOf(n);
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'node ' + n.kind);
    g.setAttribute('data-id', n.id);
    g.setAttribute('transform', 'translate(' + n.x + ',' + n.y + ')');

    const rect = document.createElementNS(NS, 'rect');
    rect.setAttribute('x', -d.w / 2);
    rect.setAttribute('y', -d.h / 2);
    rect.setAttribute('width', d.w);
    rect.setAttribute('height', d.h);
    rect.setAttribute('rx', 12);
    g.appendChild(rect);

    const text = document.createElementNS(NS, 'text');
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dominant-baseline', 'middle');
    text.textContent = n.label;
    g.appendChild(text);

    const title = document.createElementNS(NS, 'title');
    title.textContent = n.label + ' — ' + n.info;
    g.appendChild(title);

    g.addEventListener('click', function () { selectNode(n.id); });
    g.addEventListener('mouseenter', function () { highlight(n.id); });
    g.addEventListener('mouseleave', function () { clearHighlight(); });
    viewport.appendChild(g);
  });

  // --- edges ---
  const edgeEls = [];
  const edgeElByKey = {};
  DATA.edges.forEach(function (e) {
    const a = nodeById[e.from];
    const b = nodeById[e.to];
    const da = dimOf(a), db = dimOf(b);
    let path, midX, midY;
    if (e.kind === 'route') {
      const t = trim(a, b, da.r, db.r);
      path = 'M ' + t.sx + ' ' + t.sy + ' L ' + t.ex + ' ' + t.ey;
      midX = (a.x + b.x) / 2;
      midY = (a.y + b.y) / 2;
    } else {
      const t = trim(a, b, da.r, db.r);
      const dx = b.x - a.x, dy = b.y - a.y;
      const len = Math.hypot(dx, dy) || 1;
      const bulge = 28;
      const cx = (a.x + b.x) / 2 + (-dy / len) * bulge;
      const cy = (a.y + b.y) / 2 + (dx / len) * bulge;
      path = 'M ' + t.sx + ' ' + t.sy + ' Q ' + cx + ' ' + cy + ' ' + t.ex + ' ' + t.ey;
    }

    const p = document.createElementNS(NS, 'path');
    p.setAttribute('d', path);
    p.setAttribute('class', 'edge ' + e.kind);
    p.setAttribute('marker-end', 'url(#arrow-' + e.kind + ')');
    p.setAttribute('data-from', e.from);
    p.setAttribute('data-to', e.to);
    const title = document.createElementNS(NS, 'title');
    title.textContent = e.from + ' → ' + e.to + (e.label ? ' (' + e.label + ')' : '');
    p.appendChild(title);
    p.addEventListener('mouseenter', function () { p.classList.add('active'); });
    p.addEventListener('mouseleave', function () { p.classList.remove('active'); });
    viewport.appendChild(p);
    edgeEls.push(p);
    edgeElByKey[e.from + '>' + e.to] = p;

    if (e.label) {
      const lbl = document.createElementNS(NS, 'text');
      lbl.setAttribute('class', 'edge-label');
      lbl.setAttribute('x', midX);
      lbl.setAttribute('y', midY - 6);
      lbl.setAttribute('text-anchor', 'middle');
      lbl.textContent = e.label;
      viewport.appendChild(lbl);
    }
  });

  // --- interaction: hover highlight ---
  function highlight(id) {
    clearHighlight();
    const neighbors = {};
    DATA.edges.forEach(function (e) {
      if (e.from === id) neighbors[e.to] = true;
      if (e.to === id) neighbors[e.from] = true;
    });
    DATA.nodes.forEach(function (n) {
      const el = viewport.querySelector('.node[data-id="' + n.id + '"]');
      if (el && n.id !== id && !neighbors[n.id]) el.classList.add('dim');
    });
    edgeEls.forEach(function (p) {
      if (p.getAttribute('data-from') !== id && p.getAttribute('data-to') !== id) p.classList.add('dim');
    });
  }
  function clearHighlight() {
    viewport.querySelectorAll('.dim').forEach(function (el) { el.classList.remove('dim'); });
  }

  // --- interaction: info panel ---
  const info = document.getElementById('info');
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function selectNode(id) {
    const n = nodeById[id];
    const out = DATA.edges.filter(function (e) { return e.from === id; });
    const inc = DATA.edges.filter(function (e) { return e.to === id; });
    let html = '<h2>' + escapeHtml(n.label) + '</h2><p>' + escapeHtml(n.info) + '</p>';
    html += '<p><strong>Model:</strong> ' + escapeHtml(n.model || '—') + '</p>';
    html += '<h3>Inputs</h3><ul>';
    (n.inputs || []).forEach(function (x) { html += '<li>' + escapeHtml(x) + '</li>'; });
    html += '</ul><h3>Outputs</h3><ul>';
    (n.outputs || []).forEach(function (x) { html += '<li>' + escapeHtml(x) + '</li>'; });
    html += '</ul><h3>Outgoing</h3><ul>';
    out.forEach(function (e) {
      html += '<li>→ ' + escapeHtml(e.to) + (e.label ? ' <em>(' + escapeHtml(e.label) + ')</em>' : '') + '</li>';
    });
    html += '</ul><h3>Incoming</h3><ul>';
    inc.forEach(function (e) {
      html += '<li>← ' + escapeHtml(e.from) + (e.label ? ' <em>(' + escapeHtml(e.label) + ')</em>' : '') + '</li>';
    });
    html += '</ul>';
    info.innerHTML = html;

    viewport.querySelectorAll('.node.selected').forEach(function (el) { el.classList.remove('selected'); });
    const selected = viewport.querySelector('.node[data-id="' + id + '"]');
    if (selected) selected.classList.add('selected');
  }

  // --- timeline: steps + messages over time ---
  const stepDuration = 1200; // ms per step
  let stepIndex = 0;
  let playing = false;
  let timer = null;

  function stepModel(s) {
    // The model that runs this step: the non-hub endpoint of the step.
    const nodeId = (s.from === DATA.hub) ? s.to : s.from;
    const node = nodeById[nodeId];
    return (node && node.model) ? node.model : '—';
  }

  function renderTimeline() {
    const strip = document.getElementById('stepStrip');
    TRACE.forEach(function (s, idx) {
      const card = document.createElement('div');
      card.className = 'step-card';
      card.innerHTML =
        '<div><span class="step-num">#' + (idx + 1) + '</span>' +
        '<span class="step-phase">' + escapeHtml(s.phase) + '</span></div>' +
        '<div class="step-msg">' + escapeHtml(s.message) + '</div>' +
        '<div class="step-model">model: ' + escapeHtml(stepModel(s)) + '</div>' +
        '<div class="step-route">' + escapeHtml(s.from) + ' → ' + escapeHtml(s.to) + '</div>';
      card.addEventListener('click', function () { pause(); showStep(idx); });
      strip.appendChild(card);
    });
  }

  function showStep(i) {
    if (!TRACE.length) return;
    stepIndex = Math.max(0, Math.min(TRACE.length - 1, i));
    const s = TRACE[stepIndex];

    // Clear previous step highlights.
    viewport.querySelectorAll('.node.step-active').forEach(function (el) { el.classList.remove('step-active'); });
    edgeEls.forEach(function (p) { p.classList.remove('step-active'); });
    document.querySelectorAll('.step-card.active').forEach(function (c) { c.classList.remove('active'); });

    // Highlight the source and target nodes plus the edge carrying the message.
    const src = viewport.querySelector('.node[data-id="' + s.from + '"]');
    const dst = viewport.querySelector('.node[data-id="' + s.to + '"]');
    if (src) src.classList.add('step-active');
    if (dst) dst.classList.add('step-active');
    const edgeEl = edgeElByKey[s.from + '>' + s.to];
    if (edgeEl) edgeEl.classList.add('step-active');

    // Update the timeline card, slider, and time label.
    const cards = document.querySelectorAll('.step-card');
    if (cards[stepIndex]) {
      cards[stepIndex].classList.add('active');
      cards[stepIndex].scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    }
    document.getElementById('stepSlider').value = stepIndex;
    const t = (stepIndex + 1) * stepDuration / 1000;
    document.getElementById('stepLabel').textContent =
      'step ' + (stepIndex + 1) + ' / ' + TRACE.length + ' · t=' + t.toFixed(1) + 's';

    // Show the exchanged message in the info panel.
    // Show the exchanged message plus the source node's outputs and the
    // target node's inputs for a detailed view of the interaction.
    const srcNode = nodeById[s.from];
    const dstNode = nodeById[s.to];
    const srcOut = (srcNode && srcNode.outputs && srcNode.outputs.length) ? srcNode.outputs.join(', ') : '—';
    const dstIn = (dstNode && dstNode.inputs && dstNode.inputs.length) ? dstNode.inputs.join(', ') : '—';
    info.innerHTML =
      '<h2>' + escapeHtml(s.from) + ' → ' + escapeHtml(s.to) + '</h2>' +
      '<p><strong>Message:</strong> ' + escapeHtml(s.message) + '</p>' +
      '<p><strong>Phase:</strong> ' + escapeHtml(s.phase) + '</p>' +
      '<p><strong>Model:</strong> ' + escapeHtml(stepModel(s)) + '</p>' +
      '<p><strong>' + escapeHtml(s.from) + ' outputs:</strong> ' + escapeHtml(srcOut) + '</p>' +
      '<p><strong>' + escapeHtml(s.to) + ' inputs:</strong> ' + escapeHtml(dstIn) + '</p>' +
      '<p class="placeholder">' + escapeHtml('Step ' + (stepIndex + 1) + ' of ' + TRACE.length) + '</p>';
  }

  function play() {
    if (playing || !TRACE.length) return;
    playing = true;
    document.getElementById('playPause').textContent = '⏸';
    timer = setInterval(function () {
      if (stepIndex >= TRACE.length - 1) { pause(); return; }
      showStep(stepIndex + 1);
    }, stepDuration);
  }
  function pause() {
    playing = false;
    clearInterval(timer);
    timer = null;
    document.getElementById('playPause').textContent = '▶';
  }

  document.getElementById('stepPrev').addEventListener('click', function () { pause(); showStep(stepIndex - 1); });
  document.getElementById('stepNext').addEventListener('click', function () { pause(); showStep(stepIndex + 1); });
  document.getElementById('playPause').addEventListener('click', function () { playing ? pause() : play(); });
  const slider = document.getElementById('stepSlider');
  slider.max = Math.max(0, TRACE.length - 1);
  slider.addEventListener('input', function () { pause(); showStep(parseInt(this.value, 10)); });

  // --- zoom / pan ---
  let tx = 0, ty = 0, scale = 1;
  function apply() { viewport.setAttribute('transform', 'translate(' + tx + ',' + ty + ') scale(' + scale + ')'); }
  svg.addEventListener('wheel', function (e) {
    e.preventDefault();
    scale = Math.min(3, Math.max(0.3, scale * (e.deltaY < 0 ? 1.1 : 0.9)));
    apply();
  });
  let dragging = false, startX = 0, startY = 0;
  svg.addEventListener('mousedown', function (e) { dragging = true; startX = e.clientX - tx; startY = e.clientY - ty; });
  window.addEventListener('mousemove', function (e) { if (dragging) { tx = e.clientX - startX; ty = e.clientY - startY; apply(); } });
  window.addEventListener('mouseup', function () { dragging = false; });
  document.getElementById('zoomIn').addEventListener('click', function () { scale = Math.min(3, scale * 1.2); apply(); });
  document.getElementById('zoomOut').addEventListener('click', function () { scale = Math.max(0.3, scale / 1.2); apply(); });
  document.getElementById('reset').addEventListener('click', function () { tx = 0; ty = 0; scale = 1; apply(); });

  // --- init ---
  if (DATA.project) {
    document.getElementById('objectiveText').textContent = DATA.project.objective;
    const pills = DATA.project.pipeline.map(function (p) {
      return '<span class="phase-pill">' + escapeHtml(p) + '</span>';
    }).join('<span class="arrow">→</span>');
    document.getElementById('objectivePipeline').innerHTML = pills;
  }
  renderTimeline();
  showStep(0);
})();
</script>
</body>
</html>
"""


def main():
    root = find_repo_root()
    source = (root / "graph" / "workflow.py").read_text()
    orchestrator_source = (root / "agents" / "orchestrator.py").read_text()
    nodes, plain_edges, routing, hub, human_edges = parse_workflow(source, orchestrator_source)
    graph = build_graph(nodes, plain_edges, routing, hub, human_edges,
                        models=load_agent_models(root))
    graph["trace"] = build_trace(routing, hub)
    graph["project"] = PROJECT

    out = root / "docs" / "graph-ui" / "strategic-workflow-graph.html"
    if len(sys.argv) == 3 and sys.argv[1] == "--out":
        out = Path(sys.argv[2])

    html = TEMPLATE.replace("__GRAPH_DATA__", json.dumps(graph))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)

    print(f"Wrote {out} ({len(graph['nodes'])} nodes, {len(graph['edges'])} edges, {len(graph['trace'])} steps)")
    print("Nodes:", ", ".join(n["id"] for n in graph["nodes"]))
    print("Edges:")
    for e in graph["edges"]:
        label = f" ({e['label']})" if e["label"] else ""
        print(f"  {e['from']} -> {e['to']}{label}")
    print("Steps (time order):")
    for i, s in enumerate(graph["trace"], 1):
        print(f"  #{i} {s['from']} -> {s['to']} [{s['phase']}] {s['message']}")


if __name__ == "__main__":
    main()
