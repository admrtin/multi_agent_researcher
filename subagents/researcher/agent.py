from pathlib import Path
from google.adk.agents import Agent
from tools.agent_tools import (
    save_markdown_file,
    create_run_output_dir,
    load_pdf_file,
    research_single_paper,
    save_json_file,
    register_research_output,
    register_validation_result,
    get_latest_shared_state,
    build_researcher_output_identity,
    validate_researcher_artifacts,
    stream_terminal_update,
    gemini_models,
)

prompt = Path("./subagents/researcher/researcher_agent_prompt.md").read_text()
agent_name = "RESEARCHER"

researcher_agent = Agent(
    name=agent_name,
    model=gemini_models.RESEARCHER,
    instruction=prompt,
    tools=[
        stream_terminal_update,
        build_researcher_output_identity,
        create_run_output_dir,
        load_pdf_file,
        research_single_paper,
        save_markdown_file,
        save_json_file,
        validate_researcher_artifacts,
        register_research_output,
        register_validation_result,
        get_latest_shared_state,
    ],
)