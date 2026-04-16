from pathlib import Path
from google.adk.agents import Agent
from google.adk.tools import agent_tool
from subagents.researcher.agent import researcher_agent
from tools.agent_tools import (
    save_markdown_file,
    save_json_file,
    read_researcher_output,
    list_researcher_outputs,
    get_latest_run_dir,
    get_latest_planner_manifest,
    gemini_models,
)

researcher_tool= agent_tool.AgentTool(agent=researcher_agent)

prompt = Path("./subagents/validator/validator_agent_prompt.md").read_text()
agent_name = "VALIDATOR"
validator_agent = Agent(
    name=agent_name,
    model=gemini_models.VALIDATOR,
    instruction=prompt,
    tools=[
        researcher_tool,
        read_researcher_output,
        list_researcher_outputs,
        get_latest_run_dir,
        get_latest_planner_manifest,
        save_markdown_file,
        save_json_file,
    ],
)