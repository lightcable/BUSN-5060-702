# Strategic Workflow

A multi-agent strategic decision-making system that turns a high-level business
question into research, strategic options, adversarial critique, competitive
simulation, and a defensible recommendation — orchestrated as a state machine
with [LangGraph](https://langchain-ai.github.io/langgraph/) and powered by
configurable LLM providers (DeepSeek, Qwen, Kimi, Gemini, and any
OpenAI-compatible model), where **each role can use a different model**.

## What It Does

Given a strategic question (e.g. *"should we build, acquire, or partner for AI
capabilities?"*), the system runs a pipeline of specialized LLM agents:

1. **Orchestrator** — breaks the question into research domains and routes the
   workflow between phases.
2. **Researcher** — gathers intelligence per domain from public web search
   (DuckDuckGo) and internal data (local keyword search), and produces
   structured reports.
3. **Synthesizer** — combines the research into 3–5 distinct strategic options
   (rationale, actions, risks, resources, success metrics).
4. **Fact Check** — verifies the material factual claims behind each option
   against the research and public evidence; if an option fails (e.g. a claim
   contradicted by public reports), it is sent back to the Synthesizer for
   revision (bounded loop).
5. **Critic** — acts as devil's advocate, challenging assumptions and flagging
   weak evidence.
6. **Competitor** — simulates how competitors, customers, regulators, and
   partners would react to each option.
7. **Arbiter** — issues a `PASS` / `FAIL` / `PARTIAL` decision per option with
   rationale.
8. **Human Review** — pauses (via LangGraph's `interrupt`) for a human to
   approve the decisions or send the analysis back for revision.

The result is a full decision record: research reports → options → fact check →
critique → simulations → final decisions. Token usage (input/output/total) is
tracked across the whole run.

## Strategy-Making Method: Seven Steps

The pipeline follows the **"Seven Steps to Strategy Making"** from *Bringing Science to
the Art of Strategy* (Lafley, Martin, Rivkin & Siggelkow, HBR 2012):

| Step | Where the workflow does it |
|------|----------------------------|
| 1. Move from Issues to Choice | `CASE.md` frames the `Strategic Question`; the Orchestrator turns it into a decision and plans the research domains. |
| 2. Generate Strategic Possibilities | Synthesizer produces 3–5 distinct strategic options. |
| 3. Specify the Conditions for Success | Synthesizer states, per option, what must be true for it to succeed. |
| 4. Identify the Barriers to Choice | Critic ranks the conditions least likely to hold. |
| 5. Design Tests for the Barrier Conditions | Critic specifies the test that would resolve each barrier. |
| 6. Conduct the Tests | Researcher (evidence), Fact Check (claims and conditions), and Competitor (stakeholder reactions) run the tests. |
| 7. Make the Choice | Arbiter issues PASS/FAIL/PARTIAL per option and selects the option with the fewest barriers to success; Human Review approves. |

## Architecture

```
strategic_question
        │
        ▼
  Orchestrator   (hub — plans domains and routes each phase;
        │         every agent returns here)
        ▼
  Researcher
        │
        ▼
  Synthesizer ◀──────────────────┐
        │                        │
        ▼                        │
  Fact Check ───── fails (≤2 retries) ────┘
        │
        │ pass
        ▼
  Critic
        │
        ▼
  Competitor
        │
        ▼
  Arbiter
        │
        ▼
  Human Review
        │
        ├── approved ──▶ END
        │
        └── no ──▶ back to Synthesizer
```

The workflow is a `StateGraph` where each agent is a node. After every node,
control returns to the Orchestrator, which decides the next phase. A human
review gate sits before finalization, and iterations are capped.

## Design Requirements

- **Agents run independently (no context leaking).** Each role must execute in
  isolation: an agent's model call is built only from its own system prompt and
  the artifacts explicitly handed to it (e.g. the question, research reports, or
  synthesis). Agents must not share conversation history, chat memory, or any
  other agent's intermediate state, so one agent's context cannot bleed into
  another's. The shared state object passes only declared artifacts between
  nodes — never a shared message/transcript.
- **Per-role model selection.** Each role may use a different LLM, configured in
  `.env` (see [Per-Agent LLM Models](#per-agent-llm-models)).

## Project Structure

```
.
├── agents/              # One class per specialized agent
│   ├── base.py          # Shared LLM initialization + token-usage tracking
│   ├── orchestrator.py  # Plans domains and routes phases
│   ├── researcher.py    # Web + internal search per domain
│   ├── synthesizer.py   # Generates strategic options
│   ├── critic.py        # Devil's-advocate critique
│   ├── competitor.py    # Stakeholder/competitor simulation
│   └── arbiter.py       # PASS/FAIL/PARTIAL decisions
├── graph/
│   ├── state.py         # StrategicState (TypedDict) shared schema
│   └── workflow.py      # LangGraph state machine + run loop
├── tools/
│   └── search_tools.py  # DuckDuckGo web search + local keyword internal search
├── reporting.py         # CLI-output → self-contained HTML report
├── .pi/skills/          # Local pi skills (graph-ui, beautify-cli)
├── memory/              # Checkpoint storage (currently in-memory)
├── config.py            # Environment-based configuration
├── main.py              # Single entry point (run + report)
└── requirements.txt
```

## Tech Stack

- **LangGraph / LangChain** — workflow orchestration, state, and checkpoints
- **Pluggable LLM providers** (DeepSeek, Qwen, Kimi, Gemini, and any OpenAI-compatible API) — each agent role can use a different model, configured entirely in `.env`
- **DuckDuckGo (`ddgs`)** — free, no-key web search for research
- **Local keyword search** — dependency-free placeholder for internal document search
- **Pydantic / python-dotenv** — config and environment management

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` from the committed template and fill in your keys (all configuration is env-driven — `config.py` has no hardcoded parameters):

```bash
cp .env.example .env
```

## Usage

```bash
python main.py                       # run workflow + report (interactive review)
python main.py --auto-approve        # non-interactive demo (auto-approve review)
python main.py --auto-gen-graph      # also regenerate the workflow graph UI
python main.py --no-report           # CLI output only
python main.py --out out.html        # custom report path
```

`python main.py` runs the full pipeline and, in one step, also beautifies its CLI
output into a self-contained HTML report at
`reports/strategic-workflow-run.html` (set `REPORTS_DIR` in `.env` to change the
directory). By default it pauses at the
human-review step and asks you to approve or request a revision; pass
`--auto-approve` to skip that prompt. Pass `--auto-gen-graph` to also regenerate
the workflow graph (`reports/strategic-workflow-graph.html`) via the
`graph-ui` skill.

The case (question, attentions, constraints, and research materials) is defined
in `CASE.md`. `main.py` reads it, composes the brief (question + attentions +
constraints), and passes the research materials to the Researcher agents. If the
`Strategic Question` section is empty, `main.py` skips the run and reminds you to
fill it in `CASE.md`.

Token usage is tracked across the entire run: the CLI output ends with a
`token_usage` summary (input/output/total tokens, LLM calls, and estimated
cost) plus a `run_info` summary (start/end timestamps and elapsed seconds). The
HTML report shows these as header chips and node cards.

Or programmatically:

```python
from graph.workflow import StrategicWorkflow

workflow = StrategicWorkflow()
result = workflow.run(
    "Should we build, acquire, or partner for AI capabilities?",
    config={"configurable": {"thread_id": "strategy_session_1"}},
    auto_approve=True,   # set to False (default) to prompt for review
)
print(result["decisions"]["decisions"])
```

The workflow pauses at the human-review step, allowing a human to approve the
decisions or send them back for another iteration.

## Local Skills

- **`graph-ui`** — generate an interactive HTML diagram of the workflow's nodes,
  edges, phase routing, and an execution timeline of steps/messages over time.
  ```bash
  python .pi/skills/graph-ui/scripts/generate_graph_ui.py
  ```
- **`beautify-cli`** — beautify an existing CLI log (or re-run) into an HTML
  report.
  ```bash
  python .pi/skills/beautify-cli/scripts/generate_cli_report.py --input cli.log
  ```

## Configuration

All configuration is read from `.env` (see the committed `.env.example` template).
`config.py` contains no hardcoded parameters.

Required:

| Variable            | Purpose                          |
| ------------------- | -------------------------------- |
| `DEFAULT_MODEL`     | Profile used when an agent has no explicit assignment |
| `MODEL_PROFILES`    | Comma-separated list of model profiles, e.g. `deepseek,pro,qwen,kimi,gemini` |
| `AGENT_MODELS`      | Agent→profile map, e.g. `orchestrator:kimi,synthesizer:kimi,...` |
| `TEMPERATURE`       | LLM sampling temperature (non-reasoning models) |
| `MAX_ITERATIONS`    | Max revision loops before review |
| `INTERNAL_DOCS_DIR` | Directory of internal text files |
| `CASE_FILE`         | Path to the case file (default `CASE.md`) |

The case content is read from the file named by `CASE_FILE`, not from `.env`:

| `CASE.md` section | Purpose |
| ----------------- | ------- |
| `Strategic Question` | The question the agents answer |
| `Attentions` | Business areas agents must pay attention to (folded into the brief) |
| `Constraints` | Boundaries agents must respect (folded into the brief) |
| `Research Materials` | Reference sources passed to the Researcher agents |
| `Objectives` | Optional study objectives (informational) |

Each profile reads `<PREFIX>_MODEL`, `<PREFIX>_API_KEY`, `<PREFIX>_BASE_URL`,
`<PREFIX>_INPUT_PRICE_PER_M`, `<PREFIX>_OUTPUT_PRICE_PER_M`, and optional
`<PREFIX>_REASONING_EFFORT` from `.env`.

## Per-Agent LLM Models

Each agent can use a different model. The agent→profile map lives in the
`AGENT_MODELS` env var; agents not listed use `DEFAULT_MODEL`.

To choose a model for an agent, just edit `.env` — no code changes are needed:

1. Point the agent at a profile in `AGENT_MODELS` (e.g. `orchestrator:kimi`).
2. Either use an existing profile (`deepseek`, `pro`, `qwen`, `kimi`, `gemini`) or add a new
   one: any profile referenced in `AGENT_MODELS` is auto-registered, and its
   parameters are read from `<PREFIX>_MODEL`, `<PREFIX>_API_KEY`,
   `<PREFIX>_BASE_URL`, `<PREFIX>_INPUT_PRICE_PER_M`,
   `<PREFIX>_OUTPUT_PRICE_PER_M` (and optional `<PREFIX>_REASONING_EFFORT`).

Example — add an Anthropic model for the researcher:
```ini
AGENT_MODELS=orchestrator:kimi,synthesizer:kimi,critic:kimi,researcher:anthropic,competitor:pro,arbiter:pro
ANTHROPIC_MODEL=claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_BASE_URL=https://api.anthropic.com/v1
```

Default assignments:

| Agent | Profile | Model |
|-------|---------|-------|
| Orchestrator, Synthesizer, Critic | `kimi` | `KIMI_MODEL` (e.g. kimi-k3) |
| Researcher, Competitor, Fact Check | `pro` | `PRO_MODEL` (e.g. deepseek-reasoner) |
| Arbiter | `gemini` | `GEMINI_MODEL` (e.g. gemini-flash-lite-latest) |
| unlisted | `DEFAULT_MODEL` | `DEEPSEEK_MODEL` |

Pricing is broken down per profile (`Config.PRICING`, USD per 1M tokens):

| Profile | Model                | Input $/1M | Output $/1M | Override env vars |
|---------|----------------------|-----------|-------------|-------------------|
| `deepseek` | `deepseek-chat` | 0.27 | 1.10 | `DEEPSEEK_INPUT/OUTPUT_PRICE_PER_M` |
| `pro` | `deepseek-reasoner` | 0.55 | 2.19 | `PRO_INPUT/OUTPUT_PRICE_PER_M` |
| `qwen` | `qwen-plus` | 0.80 | 2.00 | `QWEN_INPUT/OUTPUT_PRICE_PER_M` |
| `kimi` | `kimi-k3` | 0.0 (set yours) | 0.0 (set yours) | `KIMI_INPUT/OUTPUT_PRICE_PER_M` |
| `gemini` | `gemini-flash-lite-latest` | 0.075 | 0.30 | `GEMINI_INPUT/OUTPUT_PRICE_PER_M` |

These are estimates; set the env vars to match your billing. Kimi also supports
`KIMI_REASONING_EFFORT` (e.g. `max`), which is forwarded to the API and causes
temperature to be omitted for that reasoning model.

## Known Limitations

- Internal search (`tools/search_tools.py`) is a keyword-search placeholder
  over local text files in `INTERNAL_DOCS_DIR`; wire it to a real vector store
  when internal documents are available.
- Checkpointing currently uses in-memory `MemorySaver` (`memory/` is empty);
  switch to a durable checkpointer for production use.


## Results

- SKILLs output should go to `./reports`.
- `main.py` output should go to `./reports`.
