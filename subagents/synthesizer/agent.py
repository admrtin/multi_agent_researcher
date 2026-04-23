from pathlib import Path
from google.adk.agents import Agent
from tools.agent_tools import (
	save_markdown_file,
	save_json_file,
	get_latest_shared_state,
	list_registered_research_outputs,
	register_synthesis_output,
	register_validation_result,
	validate_synthesis_artifacts,
	stream_terminal_update,
	load_json_file,
	gemini_models,
)

prompt = Path("./subagents/synthesizer/synthesizer_agent_prompt.md").read_text()
agent_name = "SYNTHESIZER"

synthesizer_agent = Agent(
	name=agent_name,
	model=gemini_models.SYNTHESIZER,
	instruction=prompt,
	tools=[
		stream_terminal_update,
		get_latest_shared_state,
		list_registered_research_outputs,
		load_json_file,
		save_markdown_file,
		save_json_file,
		validate_synthesis_artifacts,
		register_synthesis_output,
		register_validation_result,
	],
)
