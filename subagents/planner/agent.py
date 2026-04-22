from pathlib import Path
from google.adk.agents import Agent
from tools.agent_tools import (
    save_markdown_file,
    create_run_output_dir,
    scrape_research_articles,
    save_json_file,
    gemini_models,
    load_pdf_file,
)

prompt = Path("./subagents/planner/planner_agent_prompt.md").read_text()
agent_name = "PLANNER"

planner_agent = Agent(
    name=agent_name,
    model=gemini_models.PLANNER,
    instruction=prompt,
    tools=[
        save_markdown_file,
        save_json_file,
        create_run_output_dir,
        scrape_research_articles,
        load_pdf_file,
    ],
)