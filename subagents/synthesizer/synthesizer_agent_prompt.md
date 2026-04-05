# TODO: Synthesizer Agent Prompt Guidance

Current pipeline:
- ROOT scopes topics and routes requests
- PLANNER generates aspect plans + planner_manifest.json
- RESEARCHER generates paper reviews + paper_review.json

Synthesizer goal:
- Read multiple researcher outputs
- Produce a combined literature synthesis

Recommended v1 behavior:
1. Accept multiple researcher review files as input
2. Prefer paper_review.json as the primary machine-readable source
3. Identify:
   - shared themes
   - key differences
   - repeated limitations
   - future directions
   - relevance to the scoped topic
4. Save:
   - synthesis markdown
   - optionally synthesis JSON

Recommended output folder:
- outputs/synthesizer_outputs/run_.../

Recommended output file types:
- synthesis_report.md
- synthesis_summary.json