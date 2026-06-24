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

import base64
import json
from unittest.mock import patch
from fastapi.testclient import TestClient
from expense_agent.web_service import app

client = TestClient(app)


@patch("expense_agent.web_service.runner")
def test_trigger_pubsub_completed(mock_runner):
    """Test that a completed workflow (like auto-approval) returns 'completed' status."""
    async def mock_run_async(*args, **kwargs):
        from google.adk.events.event import Event, NodeInfo
        yield Event(
            node_info=NodeInfo(path="route_expense"),
        )
        yield Event(
            node_info=NodeInfo(path="auto_approve"),
        )
        yield Event(
            node_info=NodeInfo(path="record_outcome"),
            output={"status": "APPROVED", "reviewer_notes": "Auto-approved (under $100.0)"}
        )

    mock_runner.run_async = mock_run_async

    expense = {
        "amount": 50.0,
        "submitter": "alice@company.com",
        "category": "software",
        "description": "IDE License",
        "date": "2026-06-06"
    }
    b64_data = base64.b64encode(json.dumps(expense).encode("utf-8")).decode("utf-8")
    payload = {
        "message": {
            "data": b64_data,
            "messageId": "msg-12345"
        },
        "subscription": "projects/my-project/subscriptions/expense-sub"
    }

    response = client.post("/pubsub", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["session_id"] == "expense-sub-msg-12345"
    assert data["result"]["status"] == "APPROVED"


@patch("expense_agent.web_service.runner")
def test_trigger_pubsub_paused(mock_runner):
    """Test that a workflow pausing for human review returns 'paused' status."""
    async def mock_run_async(*args, **kwargs):
        from google.adk.events.event import Event, NodeInfo
        from google.adk.events.request_input import RequestInput
        yield Event(
            node_info=NodeInfo(path="route_expense"),
        )
        yield Event(
            node_info=NodeInfo(path="security_checkpoint"),
        )
        # Yield RequestInput to simulate the graph pause
        yield RequestInput(
            interrupt_id="decision",
            message="Do you approve or reject?"
        )

    mock_runner.run_async = mock_run_async

    expense = {
        "amount": 150.0,
        "submitter": "alice@company.com",
        "category": "software",
        "description": "IDE License",
        "date": "2026-06-06"
    }
    b64_data = base64.b64encode(json.dumps(expense).encode("utf-8")).decode("utf-8")
    payload = {
        "message": {
            "data": b64_data,
            "messageId": "msg-67890"
        },
        "subscription": "projects/my-project/subscriptions/expense-sub"
    }

    response = client.post("/pubsub", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "paused"
    assert data["session_id"] == "expense-sub-msg-67890"


@patch("expense_agent.web_service.runner")
def test_resume_session_completed(mock_runner):
    """Test that resuming a paused session returns completed status."""
    async def mock_run_async(*args, **kwargs):
        from google.adk.events.event import Event, NodeInfo
        yield Event(
            node_info=NodeInfo(path="human_approval"),
        )
        yield Event(
            node_info=NodeInfo(path="record_outcome"),
            output={"status": "APPROVED", "reviewer_notes": "Human reviewer decision: approve"}
        )

    mock_runner.run_async = mock_run_async

    payload = {
        "session_id": "expense-sub-msg-67890",
        "decision": "approve"
    }

    response = client.post("/resume", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["session_id"] == "expense-sub-msg-67890"
    assert data["result"]["status"] == "APPROVED"
