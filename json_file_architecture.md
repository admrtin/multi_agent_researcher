# JSON Architecture

The run folder, defined in `run_folder.md`, should be instantiated at the start of the program.

The JSON files that need to be created are:
- In the validator of each researcher: `validation_criteria.json`
- In the main folder: `planner_manifest.json`

## JSON Format
### `validation_criteria.json`
```json
{
    "summary_exists": false,
    "summary_relevant_to_planner_topic": false,
    "summary_scientifically_grounded": false,
    "summary_grammatically_correct": false,
    "citations_exist": false,
    "citations_valid": false,
    "citations_relevant_to_summary": false
}
```

The researcher agent:
1. deep dives into the paper assigned to it
2. generates a markdown summary of the paper
3. uses the validator sub-agent as an `agent_tool` to update the `validation_criteria.json` file

If any of the values in the `validation_criteria.json` file are false, the researcher needs to fix their summary by looping back to step 2, adding or removing content from the summary. If the validator returns all true, the researcher's summary is complete and ready to be used by the synthesizer agent.

### `planner_manifest.json`
```json
{
    "timestamp": "<timestamp>",
    "planner_topic": "<planner_topic>",
    "researchers": [
        {
            "id": "researcher_1",
            "paper": "<paper_name_1>.pdf",
            "summary": "<paper_name_1>_summary.md",
        },
        {
            "id": "researcher_2",
            "paper": "<paper_name_2>.pdf",
            "summary": "<paper_name_2>_summary.md",
        },
        /* ... */,
        {
            "id": "researcher_n",
            "paper": "<paper_name_n>.pdf",
            "summary": "<paper_name_n>_summary.md",
        }
    ]
}
```
The planner manifest contains the "global" information about the run, including the planner topic, the timestamp, and what papers/summaries each researcher is responsible for.

The synthesizer agent needs to be aware of the entire contents of the `planner_manifest.json` file so that it can use the summaries to generate a comprehensive literature review.