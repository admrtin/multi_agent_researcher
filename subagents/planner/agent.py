import json
from pathlib import Path
from google.adk.agents import Agent
from google.adk.tools import agent_tool
from subagents.researcher.agent import researcher_agent
from subagents.synthesizer.agent import synthesizer_agent
from tools.agent_tools import (
    save_markdown_file,
    create_run_output_dir,
    scrape_research_articles,
    execute_planner_pipeline,
    planner_synthesis_fallback,
    save_json_file,
    initialize_shared_run,
    register_planner_assignment,
    build_planner_output_identity,
    stream_terminal_update,
    reset_output_workspace,
    gemini_models,
)



def _serialize_agent_request(request: object) -> str:
    if isinstance(request, str):
        return request
    try:
        return json.dumps(request, indent=2, sort_keys=True, default=str)
    except TypeError:
        return str(request)


class StructuredAgentTool(agent_tool.AgentTool):
    async def run_async(self, *, args: dict, tool_context):
        request = args.get("request", "")
        if not isinstance(request, str):
            request = _serialize_agent_request(request)
        return await super().run_async(args={"request": request}, tool_context=tool_context)


researcher_tool = StructuredAgentTool(agent=researcher_agent)
synthesizer_tool = StructuredAgentTool(agent=synthesizer_agent)

prompt = Path("./subagents/planner/planner_agent_prompt.md").read_text()
agent_name = "PLANNER"

planner_agent = Agent(
    name=agent_name,
    model=gemini_models.PLANNER,
    instruction=prompt,
    tools=[
        researcher_tool,
        synthesizer_tool,
        stream_terminal_update,
        reset_output_workspace,
        build_planner_output_identity,
        save_markdown_file,
        save_json_file,
        create_run_output_dir,
        scrape_research_articles,
        execute_planner_pipeline,
        planner_synthesis_fallback,
        initialize_shared_run,
        register_planner_assignment,
    ],
)

# TODO: (DONE) We need to implement the research article abstract/reference scraper as a tool for the planner
# TODO: (DONE) Once above TODO is done we need to update the planner prompt to reflect

# available tools and their usage

# semantic search_agent : to discover relevant research articles based on the research question
# arxiv / openalex : to scrape the pdf and content of the research articles 
# firecrawl:
# langchain/llamaindex: