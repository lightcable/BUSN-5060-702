---
name: graph-ui
description: Generates a self-contained interactive HTML page visualizing the Strategic Workflow's LangGraph nodes, edges, phase routing, and an execution timeline of steps/messages over time (with playback). Use when asked to diagram, visualize, animate, or explain the workflow's node/edge interactions, or after graph/workflow.py changes.
---

# Graph UI Generator

Produces a dependency-free, interactive HTML graph for this repo's LangGraph
workflow (`graph/workflow.py`): every node (agents + `END`), the directed edges,
the phase labels that route the Orchestrator to the next agent, and an execution
timeline that shows each step and the messages exchanged between nodes with time
as a dimension (plus ▶ playback that animates the flow).

The output is a single `.html` file with inline SVG + vanilla JavaScript — no
CDN or network access required, so it opens in any plain browser.

## Usage

```bash
python .pi/skills/graph-ui/scripts/generate_graph_ui.py            # default output
python .pi/skills/graph-ui/scripts/generate_graph_ui.py --out custom.html
```

- Default output: `docs/graph-ui/strategic-workflow-graph.html`
- Open the file in a browser to inspect the graph.

## What it does

1. Parses `graph/workflow.py` to extract:
   - `add_node(...)` → nodes,
   - `add_edge(...)` → return edges back to the Orchestrator,
   - the `routing = {...}` dict in `_route_from_orchestrator` → phase → next node.
   It also reads the env-driven model config (`Config.AGENT_MODELS` / `Config.MODELS`)
   to resolve the LLM model used by each role (falling back gracefully if the
   project config is unavailable).
2. Builds a hub-and-spoke graph: `orchestrator_plan` in the center, each agent
   around it, and `END` for the terminal `done` phase.
3. Builds the ordered execution trace (13 steps): Orchestrator plans domains,
   each agent emits a message back to the Orchestrator, and the Orchestrator
   routes to the next phase — each step maps 1:1 onto a graph edge.
4. Emits one self-contained HTML file with:
   - a project objective card (what the project is trying to do + pipeline),
   - hover a node → highlight its incoming/outgoing edges,
   - click a node → info panel (description + model + incoming/outgoing list),
   - a timeline strip (time →) of step cards showing step #, phase, the
     message exchanged, and the LLM model for the step; click a card to jump to
     that step,
   - ▶ playback, ⏮/⏭ step controls, and a time slider that highlight the active
     node/edge and show the message in the info panel over time,
   - edge hover tooltips and phase labels,
   - a legend, zoom (wheel / buttons), and drag-to-pan.

## When to run

Run after changing `graph/workflow.py` (nodes, edges, or routing) to refresh the
diagram, or whenever the user asks to "visualize the workflow", "show the nodes
and edges", or "draw the agent interaction graph".
