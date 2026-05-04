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

## Authentication and Model Access

Copy the example environment file:

```bash
cp .env.example .env
```

Then edit `.env`.

### Option A: Vertex AI (recommended)

Use this mode when you want usage billed through your Google Cloud project credits.

Required `.env` values:

- `GOOGLE_GENAI_USE_VERTEXAI=true`
- `GOOGLE_CLOUD_PROJECT=<your-project-id>`
- `GOOGLE_CLOUD_LOCATION=us-central1` (or another supported region)

Authenticate with Application Default Credentials (ADC):

```bash
gcloud auth application-default login
gcloud config set project <your-project-id>
```

Enable required API:

```bash
gcloud services enable aiplatform.googleapis.com
```

### Option B: API key mode (fallback)

Use only if you are not using Vertex AI.

Required `.env` value:

- `GOOGLE_API_KEY=<your-api-key>`

### Optional key

- `SEMANTIC_SCHOLAR_API_KEY`

### Notes

- Vertex mode is selected when `GOOGLE_GENAI_USE_VERTEXAI=true` and ADC is configured.
- API-key mode is selected when `GOOGLE_API_KEY` is set and Vertex mode is not enabled.
- `SEMANTIC_SCHOLAR_API_KEY` is optional but recommended to reduce throttling for paper metadata retrieval.

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
- queries arXiv first for seed literature
- automatically falls back to Semantic Scholar and OpenAlex if arXiv returns no usable results
- generates **10 aspect markdown files**
- generates a machine-readable **`planner_manifest.json`**
- names its outputs with a stable planner/topic identity prefix so the run folder and files clearly match the topic
- uses a shared top-level `output_id` field in the manifest JSON

Planner outputs are saved under:

```text
outputs/planner_outputs/run_.../
```

Each planner run typically contains:
- plan files whose names include the stable planner/topic identity and topic slug
- ...
- `planner_manifest.json` whose name includes the stable planner/topic identity and topic slug
- the manifest JSON includes `output_id`

### 3. Researcher Agent

The Researcher agent:
- analyzes a selected paper
- first tries arXiv and downloads the PDF when available
- falls back to a web search for a direct PDF or reliable landing page if arXiv has nothing usable
- generates a structured markdown review
- generates a machine-readable **`paper_review.json`**
- names its outputs with a stable researcher/paper identity prefix so the file path clearly shows which paper was analyzed
- uses a shared top-level `output_id` field in the paper review JSON

Researcher outputs are saved under:

```text
outputs/researcher_outputs/run_.../
```

Each researcher run typically contains:
- one markdown review file whose name includes the stable paper identity and paper title
- `paper_review.json` whose name includes the stable paper identity and paper title
- the paper review JSON includes `output_id`

### 4. Synthesizer Agent

The Synthesizer agent is implemented and now:
- reads researcher outputs from shared state
- synthesizes a final related-work style report
- writes synthesis markdown + JSON artifacts
- spawns a validator pass for final quality checks

Synthesizer outputs are saved under:

```text
outputs/synthesizer_outputs/run_.../
```

Typical files:
- `final_literature_review.md`
- `synthesis_summary.json`
- `validation_report.json`

### 5. Shared State (Cross-Agent Communication)

Agents exchange essential information through:

```text
outputs/shared_runs/run_.../shared_state.json
```

This file tracks:
- planner assignments
- researcher output registrations
- validator decisions
- synthesizer output registrations

---

## Running the Web UI

The web UI provides a browser-based way to submit prompts, view live logs, and inspect Markdown outputs.

### 1. Create the web UI virtual environment

From the repository root:

```bash
cd multi_agent_researcher
python3 -m venv web_ui/venv
```

### 2. Install dependencies into the web UI environment

```bash
web_ui/venv/bin/python -m pip install --upgrade pip
web_ui/venv/bin/python -m pip install -r requirements.txt
```

If you use Vertex AI, make sure the environment variables from the setup section are configured before starting the app.

### 3. Start the web UI

```bash
PORT=8080 web_ui/run.sh
```

Then open:

```text
http://127.0.0.1:8080
```

### 4. How the web UI is organized

- Prompt input is saved in `web_ui/inputs/`
- Live log output is streamed from the agent log file and shown in the browser
- Output browsing is read from `web_ui/outputs/`, which points at the shared generated outputs location
- The web UI virtual environment lives in `web_ui/venv/`

### 5. Typical run flow

1. Start the web UI
2. Submit a research prompt
3. Watch the live logs for planner, researcher, validator, and synthesizer activity
4. Open Markdown artifacts from the output tree
5. Click `Refresh outputs` if you want to reload the Markdown catalog without clearing the log stream

### 6. Notes

- The UI is designed to keep runtime artifacts out of version control.
- If you need a clean run, clear generated output folders before starting a new prompt.
- To reproduce the current implementation exactly, use the repository's `requirements.txt` and the scripts under `web_ui/`.



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
  shared_runs/
    run_...
    run_...
    run_...
  planner_outputs/
    run_...
    run_...
    run_...
  researcher_outputs/
    run_...
    run_...
    run_...
  synthesizer_outputs/
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

### Researcher → Synthesizer

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

### Shared State Across All Agents

Shared communication registry:
- `shared_state.json`

Tracks:
- planner assignments
- researcher completions
- validator decisions
- synthesizer outputs

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
- Planner, Researcher, Validator, and Synthesizer are wired for artifact-driven orchestration.
- arXiv is the primary paper search source; Semantic Scholar and OpenAlex are fallback sources.
- Google Scholar is not used because it does not provide a stable official API for this workflow.

---

## Team Handoff Notes

Current completed milestones:
- Root → Planner routing
- Root → Researcher routing
- Root → Synthesizer routing
- Planner output generation
- Researcher output generation
- Researcher-level validation routing
- Synthesizer-level validation routing
- Planner manifest continuation
- Latest-run and explicit-manifest continuation flows
- Structured JSON handoff across Planner, Researcher, Validator, and Synthesizer
- Optional Semantic Scholar API key support
- Per-agent output folder retention