import os
import json
import asyncio
from pathlib import Path
from typing import Any

# Ensure standard import paths
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from expense_agent.agent import app as adk_app
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.adk.artifacts.file_artifact_service import FileArtifactService
from google.adk.events.request_input import RequestInput
from google.adk.events.event import Event
from google.genai import types

def serialize_event(e: Any) -> dict:
    if hasattr(e, 'model_dump'):
        return e.model_dump(mode='json', exclude_none=True)
    elif hasattr(e, 'to_dict'):
        return e.to_dict()
    else:
        return {"event_str": str(e)}

async def run_scenario(runner: Runner, case_id: str, prompt_text: str) -> list[Any]:
    session_id = f"eval-{case_id}"
    user_id = "eval-user"
    
    # Parse payload
    try:
        expense = json.loads(prompt_text)
    except Exception:
        expense = {"description": prompt_text}
        
    new_message = types.Content(
        role="user",
        parts=[types.Part(text=prompt_text)]
    )
    
    events = []
    paused = False
    
    # First execution pass
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message
    ):
        events.append(event)
        is_paused = False
        if isinstance(event, RequestInput):
            is_paused = True
        elif isinstance(event, Event):
            if hasattr(event, "get_function_calls"):
                for fc in event.get_function_calls():
                    if fc.name == "adk_request_input":
                        is_paused = True
                        break
            if not is_paused and event.content:
                parts = getattr(event.content, "parts", []) or []
                for p in parts:
                    fc = getattr(p, "function_call", None) if not isinstance(p, dict) else p.get("function_call", None)
                    if fc:
                        fc_name = getattr(fc, "name", "") if not isinstance(fc, dict) else fc.get("name", "")
                        if fc_name == "adk_request_input":
                            is_paused = True
                            break
        
        if is_paused:
            paused = True
            break
            
    if paused:
        # We hit human_approval. Automate the decision.
        description = expense.get("description", "").lower()
        # Reject if we see prompt injection attempt or if it's the specific injection case
        is_injection = "bypass" in description or "override" in description or "force" in description or case_id == "prompt_injection"
        decision = "reject" if is_injection else "approve"
        
        print(f"  [HITL] Intercepted human approval for case '{case_id}'. Decision: {decision}")
        
        # Resume the runner
        resume_message = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                         name="decision",
                         id="decision",
                         response={"decision": decision}
                    )
                )
            ]
        )
        
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=resume_message
        ):
            events.append(event)
            
    return events

async def main():
    dataset_path = Path("tests/eval/datasets/basic-dataset.json")
    output_path = Path("artifacts/traces/generated_traces.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Setup fresh runner files
    db_path = "tests/eval/eval_session.db"
    artifacts_dir = "tests/eval/eval_artifacts"
    # Clean up previous db if any
    if os.path.exists(db_path):
        os.remove(db_path)
        
    runner = Runner(
        app=adk_app,
        session_service=SqliteSessionService(db_path=db_path),
        artifact_service=FileArtifactService(root_dir=artifacts_dir),
        auto_create_session=True
    )
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    cases = dataset.get("eval_cases", [])
    populated_cases = []
    
    print(f"Generating traces for {len(cases)} cases...")
    
    for case in cases:
        case_id = case["eval_case_id"]
        prompt_content = case["prompt"]
        prompt_text = prompt_content["parts"][0]["text"]
        
        print(f"Running scenario: {case_id}...")
        events = await run_scenario(runner, case_id, prompt_text)
        
        # Extract the final response text
        final_text = ""
        for e in events:
            if hasattr(e, 'content') and e.content:
                # content can be a pydantic model or a dictionary
                role = getattr(e.content, 'role', '') if not isinstance(e.content, dict) else e.content.get('role', '')
                if role == 'model':
                    parts = getattr(e.content, 'parts', []) if not isinstance(e.content, dict) else e.content.get('parts', [])
                    parts = parts or []
                    texts = []
                    for part in parts:
                        text_val = getattr(part, 'text', '') if not isinstance(part, dict) else part.get('text', '')
                        if text_val:
                            texts.append(text_val)
                    if texts:
                        final_text = "".join(texts)
                    
        response_candidate = {
            "response": {
                "role": "model",
                "parts": [{"text": final_text}]
            }
        }
        
        populated_case = {
            "eval_case_id": case_id,
            "prompt": prompt_content,
            "responses": [response_candidate],
            "agent_data": {
                "turns": [
                    {
                        "turn_index": 0,
                        "turn_id": "turn_0",
                        "events": [serialize_event(e) for e in events]
                    }
                ]
            }
        }
        populated_cases.append(populated_case)
        print(f"Scenario: {case_id} completed.")
        
    # Write to artifacts
    output_dataset = {
        "eval_cases": populated_cases
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_dataset, f, indent=2)
        
    print(f"Traces successfully written to {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
