# Multi Agent Researcher Project Documentation

## 1. Project Objective

The project builds an end-to-end multi-agent research assistant that can:

- intake broad research questions,
- decompose them into structured planning aspects,
- analyze selected papers deeply,
- validate analysis quality,
- synthesize validated outputs into a final related-work style report.

The primary goal is to replace ad-hoc manual literature triage with a reproducible, artifact-driven workflow that preserves traceability between planning decisions, paper-level reviews, validation decisions, and final synthesis.

## 2. Problem Statement

Academic and technical research exploration has four recurring bottlenecks:

1. Broad topics are difficult to scope into actionable sub-questions.
2. Paper selection and comparison are inconsistent across sessions.
3. Summaries often mix grounded facts with unsupported claims.
4. Final synthesis is hard to reproduce without explicit intermediate artifacts.

This project addresses those bottlenecks by introducing specialized agents and strict JSON/markdown contracts between stages.

## 3. High-Level System Scope

The system supports:

- Topic scoping and planning.
- Seed paper discovery from multiple sources.
- Per-paper deep analysis.
- Validation at researcher stage and synthesis stage.
- Cross-agent communication using shared state.
- Continuation from previous planner runs.

The system intentionally stores artifacts to disk so each stage can be audited independently.

## 4. Architecture Overview

### 4.1 Agent Roles

- ROOT:
  - Intake coordinator.
  - Confirms scope for broad requests.
  - Requests explicit Green Light before planning.
  - Routes to Planner, Researcher, or Synthesizer based on intent.

- PLANNER:
  - Searches seed literature.
  - Produces aspect plans and planner manifests.
  - Initializes shared run state.
  - Assigns papers to researcher workers.
  - Triggers synthesizer after researcher stage.

- RESEARCHER:
  - Analyzes one assigned paper.
  - Prefers arXiv PDF retrieval and text extraction when available.
  - Produces review markdown and review JSON.
  - Triggers validator for quality check.

- VALIDATOR:
  - Evaluates researcher outputs or synthesizer outputs.
  - Produces pass/fail validation records and rationale.
  - Registers decisions into shared state.

- SYNTHESIZER:
  - Reads registered researcher outputs.
  - Produces final integrated literature synthesis.
  - Triggers final validator pass.

### 4.2 Orchestration Pattern

The project uses artifact-driven orchestration:

- planner and shared-state files are written first,
- researcher assignments are explicitly registered,
- researcher outputs and validations are registered,
- synthesizer reads shared state and completes final integration.

This pattern reduces hidden state and improves debuggability.

## 5. Methodologies and Frameworks Used

### 5.1 Core Framework

- Google ADK for agent/sub-agent orchestration.
- Google Gemini models via Vertex AI with dynamic model resolution.

### 5.2 Retrieval and Data Sources

Paper retrieval order in planner:

1. arXiv (primary)
2. Semantic Scholar (fallback)
3. OpenAlex (fallback)

Researcher retrieval strategy:

1. arXiv first, attempt PDF download,
2. web fallback for PDF/landing page,
3. metadata enrichment from Semantic Scholar.

### 5.3 Document Processing

- PDF text extraction uses pypdf.
- Markdown artifacts for human-readable reviews.
- JSON artifacts for machine-readable handoff.

### 5.4 Validation Methodology

Validator checks:

- scientific grounding,
- factual consistency,
- relevance correlation to planner question.

Output decision:

- pass or fail,
- structured reasons and confidence labels.

### 5.5 Reliability and Recovery Strategies

- Stable output identity generation for planner/researcher artifacts.
- Run-folder retention and cleanup controls.
- Shared state registration for each stage transition.
- Robust JSON payload parsing for model-produced data.
- Vertex model probing to avoid selecting inaccessible model IDs.

## 6. Repository Structure Summary

Top-level key components:

- agent.py:
  - root agent composition.

- subagents/planner:
  - planner agent config and instructions.

- subagents/researcher:
  - researcher agent config and instructions.

- subagents/validator:
  - validator agent config and instructions.

- subagents/synthesizer:
  - synthesizer agent config and instructions.

- tools/agent_tools.py:
  - shared utility and orchestration tools.
  - search, save, registration, model selection, and run-state helpers.

- outputs/:
  - runtime artifacts written by all stages.

- json_file_architecture.md:
  - JSON contract for cross-agent communication.

## 7. Output Contracts

### 7.1 Planner Artifacts

Expected planner outputs:

- planner run directory under outputs/planner_outputs,
- aspect markdown files,
- planner_manifest.json,
- optionally prefixed manifest with output identity.

### 7.2 Shared Run Artifacts

Expected shared output:

- shared_state.json under outputs/shared_runs,
- assignment registry,
- research output registry,
- validation registry,
- synthesis output registry.

### 7.3 Researcher and Validator Artifacts

Expected researcher outputs:

- one review markdown file per paper,
- one paper review JSON per paper,
- validator report for each reviewed paper.

### 7.4 Synthesizer Artifacts

Expected synthesis outputs:

- final literature review markdown,
- synthesis summary JSON,
- final validator report.

## 8. Current Development Status (As of 2026-04-22)

Implemented:

- Multi-agent wiring: ROOT, PLANNER, RESEARCHER, VALIDATOR, SYNTHESIZER.
- Shared-state based cross-agent communication tools.
- Planner arXiv-first retrieval and fallback strategy.
- Researcher PDF-first enrichment workflow.
- Validator registration and synthesis-stage validation flow.
- Dynamic Vertex Gemini model selection with probe checks.
- Deterministic planner pipeline helper added to reduce prompt-only failures.

Observed runtime gap:

- The latest planner run directory exists but is empty in the current workspace snapshot.
- No planner manifest, shared state, researcher outputs, or validator artifacts were present at snapshot time.

Interpretation:

- Core architecture and tools are implemented.
- End-to-end execution still requires runtime validation in the configured environment to confirm planner pipeline completion and downstream spawning.

## 9. Known Risks and Constraints

- External API dependency risk:
  - paper sources can rate-limit or change behavior.

- Environment dependency risk:
  - missing local package installs can prevent direct tool execution.

- LLM instruction fragility:
  - prompt-only workflows can stall without deterministic tool-level enforcement.

- Artifact consistency risk:
  - naming changes require backward-compatible manifest lookup.

## 10. Recommended Operational Flow

1. Configure environment and credentials.
2. Launch ADK CLI from project root.
3. Submit broad topic to ROOT.
4. Confirm scoped summary and provide Green Light.
5. Validate that planner writes manifest/shared-state artifacts.
6. Validate that researchers are spawned per selected paper.
7. Validate per-paper validator reports.
8. Validate synthesizer output and final validator report.

## 11. Success Criteria

A run is considered successful when all conditions are met:

1. Planner writes manifest plus aspect files.
2. Shared state file exists and includes assignments.
3. Multiple researcher outputs are generated for selected papers.
4. Validator reports exist for researcher outputs.
5. Synthesizer output and final validation report are generated.
6. Final output is traceable from planner decision to synthesis conclusion.

## 12. Next Technical Priorities

1. Add automated integration test for planner-to-researcher-to-validator path.
2. Add runtime guardrails to detect and report empty planner output immediately.
3. Add explicit telemetry/logging per agent stage transition.
4. Add deterministic retry strategy for transient retrieval/model failures.
5. Expand tests for manifest and shared-state schema validation.
