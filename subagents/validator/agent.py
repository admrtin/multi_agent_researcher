from pathlib import Path
from google.adk.agents import Agent
from tools.agent_tools import (
    save_markdown_file,
    save_json_file,
    read_researcher_output,
    list_researcher_outputs,
    get_latest_run_dir,
    get_latest_planner_manifest,
    get_latest_shared_state,
    register_validation_result,
    stream_terminal_update,
    gemini_models,
)

prompt = Path("./subagents/validator/validator_agent_prompt.md").read_text()
agent_name = "VALIDATOR"
validator_agent = Agent(
    name=agent_name,
    model=gemini_models.VALIDATOR,
    instruction=prompt,
    tools=[
        stream_terminal_update,
        read_researcher_output,
        list_researcher_outputs,
        get_latest_run_dir,
        get_latest_planner_manifest,
        get_latest_shared_state,
        register_validation_result,
        save_markdown_file,
        save_json_file,
    ],
)