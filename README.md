# DSCI 576 Multi Agent Researcher Project - Group 6

## Clone the repository: 
`git clone <repo-url>`

`cd multi_agent_researcher`

## Setup Python Environment
`python -m venv .venv`

## Install Dependencies
Linux/MacOS: `source .venv/bin/activate`          

In Windows: `.venv\Scripts\activate`

`pip install -r requirements.txt`

## API Keys
`cp .env.example .env`

* After executing above, edit .env and fill in your API keys


## Repository Scaffolding
```
multi_agent_researcher/
│
├── agent.py                       # ROOT AGENT (Agent-to-Agent Pipeline Orchestration)
├── __init__.py                    # ROOT AGENT's init file
|                          
├── subagents/                     # One sub-package per agent
│   |   __init__.py
|   |
|   ├── planner/
│   |       agent.py               # Planner's agent file
|   |       __init__.py            # Planner's init file
|   |       prompt.md              # Planner's input prompt
│   ├── researcher/
│   │       agent.py               # ...
|   |       __init__.py
|   |       prompt.md
│   ├── synthesizer/
│   │       agent.py
|   |       __init__.py
|   |       prompt.md
│   └── validator/
│           agent.py
|           __init__.py
|           prompt.md
│
├── tools/                         # Reusable Utilities
|           __init__.py
│
├── tests/
│           .gitkeep               # Can remove when testing files are added
|
├── outputs/                       # Generated literature reviews (git-ignored)
│           .gitkeep               # Don't remove. Ensures the folder is instantiated on local.
├── requirements.txt               # Runtime dependencies
├── .env.example                   # Example env for API Keys
├── .gitignore                     # Ensures we don't commit bloat.
├── README.md                      # This file
```