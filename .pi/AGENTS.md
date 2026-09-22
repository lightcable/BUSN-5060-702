# Working in Blueprint

Blueprint encodes world-class software engineering and agentic engineering practice: spec when decisions matter, plan when work needs splitting, test before ship, review before merge.

If you are an AI agent working in this repo, follow this guidance.

## The Flow

Use `spec -> plan -> implement -> review` for changes that touch contracts, schemas, multiple files, user-visible behavior, or invariants. Skip stages only when explicitly told to or when the change is trivial and decision-complete.

Exploration is allowed without creating docs or issue tracker entries. Do not manufacture fake specs, plans, or issues for spikes.

Execute all skills in the `.pi/skills/` directory accordingly

## Skills
- `spec`: write the technical design before coding.
- `plan`: break a spec, brief, or request into agent-sized tasks.
- `implement`: execute one scoped change with tests and verification.
- `tdd`: test-first variant of implement.
- `review`: pre-merge review for correctness, security, simplicity, robustness, and tests.
- `browser-verify`: verify browser-rendered work in a real browser.
- `explain-visually`: create a responsive HTML explainer for a repo, spec, PR, architecture, or concept.
- `compress`: shorten over-long instructions without changing behavior.
- `branch`: create a traceable Git branch with the ticket ID when available.
- `commit`: stage intended changes and write one clear Conventional Commit.
- `graph-ui`: generate an interactive HTML diagram of the LangGraph workflow's nodes, edges, phase routing, and a timeline of steps/messages over time.
- `beautify-cli`: capture `python main.py` CLI output and convert it into a styled self-contained HTML report.

### Skill Location
- All active local skills are stored in the `.pi/skills/` directory

### `graph-ui` Skill
- **Purpose:** generate a self-contained, dependency-free interactive HTML diagram of the workflow's LangGraph nodes, edges, and phase routing, plus a project objective card and an execution timeline of steps and messages with time as a dimension (playback animation).
- **Location:** `.pi/skills/graph-ui/` (`SKILL.md` + `scripts/generate_graph_ui.py`).
- **Run:** `python .pi/skills/graph-ui/scripts/generate_graph_ui.py [--out PATH]`
- **Default output:** `docs/graph-ui/strategic-workflow-graph.html`
- **When:** re-run after changing `graph/workflow.py`, or when asked to visualize/animate the workflow's node/edge interactions.

### `beautify-cli` Skill
- **Purpose:** beautify the workflow's CLI output into a styled, self-contained HTML report. `python main.py` now does this automatically (single executable); this skill converts an existing log (`--input`) or re-renders one.
- **Location:** `.pi/skills/beautify-cli/` (`SKILL.md` + `scripts/generate_cli_report.py`); shared logic in `reporting.py`.
- **Run:** `python .pi/skills/beautify-cli/scripts/generate_cli_report.py [--input FILE] [--out PATH]`
- **Default output:** `reports/strategic-workflow-run.html`
- **When:** to beautify an existing log file, or after `python main.py` when a report needs re-rendering.

## Guidance

- One spec per feature, at `docs/<feature-slug>/spec.html`.
- Plans default to `docs/<feature-slug>/plan.html`. Push tasks to an issue tracker only when the user asks.
- If the task, spec, or plan is wrong, stop and update it. Do not push through.
- Tests are the verification mechanism; review checks they are real.
- Density over length. Run `compress` when a skill or instruction starts to feel bloated.
- Generate a report in HTML format to capture the workflow in details including all the executed commands


## Code Disciplines
- Generate detailed descriptions to explain the motive of each functions
- Explain Inputs and Outputs, and expected behaviors for modules, classes, or functions.
- Any code change should reflect should reflect to all skills defined in the "skills" directory.

## Out of Scope

Blueprint is not an issue tracker, architecture review board, or release process. It turns external context into high-quality instructions for coding agents. That's the entire job.
