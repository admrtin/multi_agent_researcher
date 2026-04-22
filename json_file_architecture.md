# JSON Architecture

This project uses a shared JSON contract so agents can communicate by artifacts,
not only by chat context.

## Agent Flow

1. Planner receives the research question and identifies relevant papers.
2. Planner spawns multiple researcher agents, one per selected paper.
3. Each researcher writes a paper review and spawns a validator for that review.
4. Synthesizer reads all validated researcher outputs and creates a final related-work style synthesis.
5. Synthesizer spawns its own validator for final quality and correlation checks.

## Required JSON Artifacts

- `outputs/planner_outputs/run_.../planner_manifest.json`
- `outputs/shared_runs/run_.../shared_state.json`
- `outputs/researcher_outputs/run_.../paper_review.json`
- `outputs/researcher_outputs/run_.../validation_report.json`
- `outputs/synthesizer_outputs/run_.../synthesis_summary.json`
- `outputs/synthesizer_outputs/run_.../validation_report.json`

## planner_manifest.json

```json
{
    "topic": "<planner topic>",
    "planner_run_dir": "outputs/planner_outputs/run_...",
    "shared_state_file": "outputs/shared_runs/run_.../shared_state.json",
    "aspects": [
        {
            "aspect_id": "aspect_01",
            "title": "<aspect title>",
            "plan_markdown_file": "outputs/planner_outputs/run_.../plan_01_...md",
            "seed_papers": [
                {
                    "title": "<paper title>",
                    "year": 2024,
                    "url": "<optional url>"
                }
            ]
        }
    ],
    "research_assignments": [
        {
            "researcher_id": "researcher_01",
            "aspect_id": "aspect_01",
            "paper_title": "<paper title>",
            "paper_url": "<optional url>"
        }
    ]
}
```

## shared_state.json

This is the central communication file used by all agents.

```json
{
    "planner_topic": "<planner topic>",
    "planner_manifest_path": "outputs/planner_outputs/run_.../planner_manifest.json",
    "run_dir": "outputs/shared_runs/run_...",
    "created_at": "<iso timestamp>",
    "assignments": [
        {
            "researcher_id": "researcher_01",
            "aspect_id": "aspect_01",
            "aspect_title": "<aspect>",
            "paper_title": "<paper>",
            "paper_url": "<url or null>",
            "status": "assigned | completed",
            "timestamp": "<iso timestamp>"
        }
    ],
    "research_outputs": [
        {
            "researcher_id": "researcher_01",
            "paper_title": "<paper>",
            "review_markdown_file": "outputs/researcher_outputs/run_.../paper_review.md",
            "review_json_file": "outputs/researcher_outputs/run_.../paper_review.json",
            "validation_report_file": "outputs/researcher_outputs/run_.../validation_report.json",
            "validation_status": "pass | fail | pending",
            "timestamp": "<iso timestamp>"
        }
    ],
    "validations": [
        {
            "validator_scope": "researcher | synthesizer",
            "target_id": "researcher_01 | final_synthesis",
            "status": "pass | fail",
            "notes": "<summary>",
            "report_file": "<path or null>",
            "timestamp": "<iso timestamp>"
        }
    ],
    "synthesis_outputs": [
        {
            "synthesis_markdown_file": "outputs/synthesizer_outputs/run_.../final_literature_review.md",
            "synthesis_json_file": "outputs/synthesizer_outputs/run_.../synthesis_summary.json",
            "validation_report_file": "outputs/synthesizer_outputs/run_.../validation_report.json",
            "validation_status": "pass | fail | pending",
            "timestamp": "<iso timestamp>"
        }
    ]
}
```

## Validator report format

Both researcher-level and synthesizer-level validator runs use:

```json
{
    "validator_scope": "researcher | synthesizer",
    "target_id": "<id>",
    "status": "pass | fail",
    "reasons": ["<reason>"],
    "correlation_to_planner_question": "high | medium | low",
    "scientific_grounding": "high | medium | low"
}
```

## Why this contract works

- Planner-to-researcher communication: explicit assignments.
- Researcher-to-validator communication: local review artifact paths.
- Researcher-to-synthesizer communication: shared `research_outputs` registry.
- Synthesizer-to-validator communication: final synthesis artifact paths.
- Full traceability: every stage writes status and validation outcome.