import asyncio
import json
from expense_agent.agent import app as adk_app
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.adk.artifacts.file_artifact_service import FileArtifactService
from google.genai import types

async def main():
    runner = Runner(
        app=adk_app,
        session_service=SqliteSessionService(db_path="expense_agent/.adk/session.db"),
        artifact_service=FileArtifactService(root_dir="expense_agent/.adk/artifacts"),
        auto_create_session=True
    )
    
    expense = {
        "amount": 50.0,
        "submitter": "alice@company.com",
        "category": "software",
        "description": "IDE License",
        "date": "2026-06-06"
    }
    
    new_message = types.Content(
        role="user",
        parts=[types.Part(text=json.dumps(expense))]
    )
    
    events = []
    async for event in runner.run_async(
        user_id="test-eval",
        session_id="test-eval-session-1",
        new_message=new_message
    ):
        events.append(event)
        
    print(f"Number of events: {len(events)}")
    for e in events:
        print(type(e))
        if hasattr(e, 'model_dump'):
            print(e.model_dump())
        elif hasattr(e, 'to_dict'):
            print(e.to_dict())
        else:
            print(str(e))

asyncio.run(main())
