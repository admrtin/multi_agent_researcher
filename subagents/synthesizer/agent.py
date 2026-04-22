from pathlib import Path
from google.adk.agents import Agent
from google.adk.tools import agent_tool
from subagents.validator.agent import validator_agent
from tools.agent_tools import (
	save_markdown_file,
	save_json_file,
	get_latest_shared_state,
	list_registered_research_outputs,
	register_synthesis_output,
	register_validation_result,
	stream_terminal_update,
	load_json_file,
	gemini_models,
)

validator_tool = agent_tool.AgentTool(agent=validator_agent)

prompt = Path("./subagents/synthesizer/synthesizer_agent_prompt.md").read_text()
agent_name = "SYNTHESIZER"

synthesizer_agent = Agent(
	name=agent_name,
	model=gemini_models.SYNTHESIZER,
	instruction=prompt,
	tools=[
		validator_tool,
		stream_terminal_update,
		get_latest_shared_state,
		list_registered_research_outputs,
		load_json_file,
		save_markdown_file,
		save_json_file,
		register_synthesis_output,
		register_validation_result,
	],
)
