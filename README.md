# DSCI 576 Multi Agent Researcher Project - Group 6

A multi-agent research assistant built with Google ADK for scoped literature planning, single-paper analysis, and structured handoff between agents using markdown and JSON artifacts.

---

## Clone the repository

```bash
git clone <repo-url>
cd multi_agent_researcher
```

---

## Setup Python Environment

Create and activate a virtual environment:

```bash
python -m venv .venv
```

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Activate the environment:

**Linux / macOS**
```bash
source .venv/bin/activate
```

**Windows**
```powershell
.\.venv\Scripts\activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

---

## API Keys

Copy the example environment file:

```bash
cp .env.example .env
```

Then edit `.env` and provide your keys.

### Supported keys

- `GOOGLE_API_KEY`
- `SEMANTIC_SCHOLAR_API_KEY`

### Notes

- `GOOGLE_API_KEY` is required for Gemini / Google ADK agent execution.
- `SEMANTIC_SCHOLAR_API_KEY` is optional but recommended to reduce throttling when retrieving paper metadata from Semantic Scholar.

---

## Running Google ADK

To start the app, make sure your current working directory is `multi_agent_researcher`, then run:

```bash
adk run .
```

This launches the CLI for the **Root agent**, which routes requests to the project subagents.

---

## Current Agent Workflow

The application currently supports a multi-stage research workflow.

### 1. Root Agent

The Root agent acts as the intake coordinator.

It can:
- refine broad literature-review topics before sending them to the Planner
- route a specific paper-analysis request directly to the Researcher
- continue from:
  - the latest planner run, or
  - a user-specified `planner_manifest.json`

When continuing from a planner run, Root loads the planner manifest and presents a numbered menu of seed papers for user selection.

### 2. Planner Agent

The Planner agent:
- receives a refined research topic
- queries Semantic Scholar for seed literature
- generates **10 aspect markdown files**
- generates a machine-readable **`planner_manifest.json`**

Planner outputs are saved under:

```text
outputs/planner_outputs/run_.../
```

Each planner run typically contains:
- `plan_01_...md`
- `plan_02_...md`
- ...
- `plan_10_...md`
- `planner_manifest.json`

### 3. Researcher Agent

The Researcher agent:
- analyzes a selected paper
- generates a structured markdown review
- generates a machine-readable **`paper_review.json`**

Researcher outputs are saved under:

```text
outputs/researcher_outputs/run_.../
```

Each researcher run typically contains:
- one markdown review file
- `paper_review.json`

### 4. Synthesizer Agent

The Synthesizer agent is not yet fully implemented.

The intended next step is for Synthesizer to consume multiple `paper_review.json` files and produce a higher-level literature synthesis.

---

## Continuation Workflows

### Continue from the latest planner run

Example user prompt:

```text
Continue from the latest planner run
```

Root will:
1. load the newest `planner_manifest.json`
2. present a numbered menu of seed papers
3. wait for the user to choose a paper
4. hand the selected paper to the Researcher

### Continue from a specific planner manifest

Example user prompt:

```text
Continue from this planner manifest: outputs/planner_outputs/run_2026_04_05_101835/planner_manifest.json
```

This allows the user to revisit an older planner run instead of the newest one.

---

## Output Retention

Each agent uses timestamped run folders and keeps only the most recent **3** runs.

Example structure:

```text
outputs/
  planner_outputs/
    run_...
    run_...
    run_...
  researcher_outputs/
    run_...
    run_...
    run_...
```

### Note for Windows / OneDrive users

If the project is stored inside OneDrive or files are open in an editor, old output folders may occasionally be locked. In that case, retention cleanup may print warnings, but the app can still continue running.

---

## Current Structured Handoff Artifacts

The app now supports structured communication between agents through JSON files.

### Planner → Researcher

Planner creates:
- `planner_manifest.json`

This file contains:
- overall topic
- planner run directory
- aspect metadata
- seed paper titles for each aspect

### Researcher → Future Synthesizer / Expansion

Researcher creates:
- `paper_review.json`

This file contains:
- paper metadata
- abstract summary
- methodology
- advantages / limitations
- results
- references for expansion
- citations for expansion

These artifacts allow the system to move beyond plain chat-only coordination.

---

## Example Usage

### Broad planning request

```text
I want to do a literature review on agentic AI systems for scientific research automation.
```

### Scoped follow-up

```text
Focus on automated hypothesis generation in biomedical research workflows, specifically using Large Language Models.
```

### Planning confirmation

```text
Green Light.
```

### Continue from latest planner run

```text
Continue from the latest planner run
```

### Select a paper from the menu

```text
1
```

### Analyze a specific paper directly

```text
Analyze this paper: LLaVA-Med: Training a Large Language-and-Vision Assistant for Biomedicine in One Day
```

---

## Development Notes

- The project currently works best as a CLI-driven ADK application.
- Semantic Scholar retrieval is metadata-based and currently does not require PDF parsing.
- Planner and Researcher are functioning for v1.
- The next major feature is the Synthesizer agent.

---

## Team Handoff Notes

Current completed milestones:
- Root → Planner routing
- Root → Researcher routing
- Planner output generation
- Researcher output generation
- Planner manifest continuation
- Latest-run and explicit-manifest continuation flows
- Structured JSON handoff between Planner and Researcher
- Optional Semantic Scholar API key support
- Per-agent output folder retention

Recommended next development target: