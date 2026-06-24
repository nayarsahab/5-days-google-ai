# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
# Set Cloud Telemetry to False as requested
os.environ["GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY"] = "false"
os.environ["ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"] = "false"

import logging
import base64
import json
import uuid
from typing import Optional, Any
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

# Setup standard Python logging for console logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("expense_agent.web_service")

# Load dotenv if running locally
from dotenv import load_dotenv
load_dotenv()

# Initialize vertexai
try:
    import vertexai
    vertexai.init()
except Exception as e:
    logger.warning("Could not initialize vertexai, proceeding: %s", e)

from google.adk.runners import Runner
from google.adk.events.event import Event
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from google.adk.artifacts.file_artifact_service import FileArtifactService
from google.genai import types
from expense_agent.agent import app as adk_app

# Set up SQLite session database and file artifact services matching the Dev UI
db_path = os.path.join("expense_agent", ".adk", "session.db")
artifacts_path = os.path.join("expense_agent", ".adk", "artifacts")

session_service = SqliteSessionService(db_path=db_path)
artifact_service = FileArtifactService(root_dir=artifacts_path)

runner = Runner(
    app=adk_app,
    session_service=session_service,
    artifact_service=artifact_service,
    auto_create_session=True
)

app = FastAPI(title="Ambient Expense Approval Agent Web Service")


class PubSubMessage(BaseModel):
    data: Optional[str] = Field(default=None, description="Base64-encoded message data.")
    attributes: Optional[dict[str, str]] = Field(default=None, description="Message attributes.")
    messageId: Optional[str] = Field(default=None, description="Pub/Sub message ID.")
    publishTime: Optional[str] = Field(default=None, description="Publish timestamp.")


class PubSubTriggerRequest(BaseModel):
    message: PubSubMessage
    subscription: Optional[str] = Field(
        default=None,
        description="Full subscription name (e.g. projects/p/subscriptions/s).",
    )


class ResumeRequest(BaseModel):
    session_id: str
    decision: str  # e.g., "approve" or "reject"


@app.post("/")
@app.post("/pubsub")
async def trigger_pubsub(req: PubSubTriggerRequest):
    """
    Accepts Pub/Sub push messages, normalizes subscription path, and feeds to the workflow.
    """
    subscription = req.subscription or "pubsub-caller"
    
    # Gotcha: Normalize fully-qualified subscription path down to a short name
    # e.g. 'projects/my-project/subscriptions/my-subscription' -> 'my-subscription'
    sub_short_name = subscription.split("/")[-1] if subscription else "default-subscription"
    
    message_id = req.message.messageId or str(uuid.uuid4())
    
    # session_id combined with normalized short name for readability
    session_id = f"{sub_short_name}-{message_id}"
    user_id = "pubsub-trigger"

    logger.info("Normalized subscription to: %s", sub_short_name)
    logger.info("Processing message ID: %s", message_id)
    logger.info("Running workflow with session ID: %s", session_id)

    # Feed the message dictionary containing 'data' to the runner
    message_text = json.dumps(req.message.model_dump())
    new_message = types.Content(
        role="user",
        parts=[types.Part(text=message_text)]
    )

    try:
        events = []
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message
        ):
            events.append(event)
            # Standard python log output for each node execution
            if isinstance(event, Event) and event.node_info and event.node_info.path:
                logger.info("[%s] Node executed: %s", 
                            session_id, event.node_info.name)

        # Retrieve the final result or status if completed
        final_result = None
        for event in events:
            if isinstance(event, Event) and event.output and "status" in event.output:
                final_result = event.output
                break

        # If we yielded RequestInput, it paused the workflow
        # Let's inspect events to see if RequestInput is yielded
        # (In ADK, RequestInput is emitted as part of runner.run_async generator output)
        from google.adk.events.request_input import RequestInput
        has_request_input = False
        for e in events:
            if isinstance(e, RequestInput):
                has_request_input = True
                break
            elif isinstance(e, Event):
                # Real ADK runner wraps RequestInput as an Event containing adk_request_input function call
                for fc in e.get_function_calls():
                    if fc.name == "adk_request_input":
                        has_request_input = True
                        break
                if has_request_input:
                    break

        if has_request_input:
            logger.info("[%s] Workflow paused at security/review checkpoint waiting for human approval.", session_id)
            return {
                "status": "paused",
                "session_id": session_id,
                "message": "Workflow is paused waiting for human approval."
            }

        logger.info("[%s] Workflow execution completed. Result: %s", session_id, final_result)
        return {
            "status": "completed",
            "session_id": session_id,
            "result": final_result
        }

    except Exception as e:
        logger.exception("[%s] Error running workflow: %s", session_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/resume")
async def resume_session(req: ResumeRequest):
    """
    Exposes an endpoint to resume a paused human_approval step.
    """
    session_id = req.session_id
    user_id = "pubsub-trigger"
    decision = req.decision

    logger.info("Resuming session %s with decision: %s", session_id, decision)

    # Resume the workflow by constructing a function response matching the 'decision' interrupt_id
    new_message = types.Content(
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

    try:
        events = []
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message
        ):
            events.append(event)
            if isinstance(event, Event) and event.node_info and event.node_info.path:
                logger.info("[%s] Node executed: %s", 
                            session_id, event.node_info.name)

        final_result = None
        for event in events:
            if isinstance(event, Event) and event.output and "status" in event.output:
                final_result = event.output
                break

        logger.info("[%s] Workflow completed after resume. Result: %s", session_id, final_result)
        return {
            "status": "completed",
            "session_id": session_id,
            "result": final_result
        }

    except Exception as e:
        logger.exception("[%s] Error resuming workflow: %s", session_id, e)
        raise HTTPException(status_code=500, detail=str(e))
