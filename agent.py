# The root agent.
# Acts as the interface to planner and researcher agents.
from pathlib import Path
from google.adk.agents import Agent
from subagents.planner.agent import planner_agent
from subagents.researcher.agent import researcher_agent
from subagents.synthesizer.agent import synthesizer_agent
from tools.agent_tools import (
    gemini_models,
    load_json_file,
    get_latest_planner_manifest,
    stream_terminal_update,
)

prompt = Path("root_agent_prompt.md").read_text()
agent_name = "ROOT"

root_agent = Agent(
    name=agent_name,
    model=gemini_models.ROOT,
    instruction=prompt,
    tools=[load_json_file, get_latest_planner_manifest, stream_terminal_update],
    sub_agents=[planner_agent, researcher_agent, synthesizer_agent],
)