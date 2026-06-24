# ruff: noqa
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
import logging
import re
from typing import Any, AsyncGenerator

from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.workflow import Workflow, node, START
from google.genai import types
from pydantic import BaseModel, Field

import os
import google.auth

from .config import THRESHOLD, MODEL_NAME

# Setup default cloud project env for Vertex/Gemini Enterprise
try:
    _, project_id = google.auth.default()
    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
except Exception:
    pass

os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

logger = logging.getLogger(__name__)


# 1. Pydantic models for inputs and outputs
class RiskAssessment(BaseModel):
    risk_score: int = Field(description="Risk score from 1 (low) to 10 (high)")
    risk_factors: list[str] = Field(description="List of identified risk factors or anomalies")
    alert_raised: bool = Field(description="True if an alert should be raised for high risk")
    summary: str = Field(description="Short summary of the risk assessment")


# 2. Workflow Node definitions

def parse_payload(node_input: Any) -> dict:
    """Parses incoming JSON event (handles base64 Pub/Sub or raw JSON)."""
    raw_text = ""
    # Extract the payload string from types.Content or raw inputs
    if hasattr(node_input, "parts") and node_input.parts:
        raw_text = "".join(part.text for part in node_input.parts if part.text)
    elif isinstance(node_input, str):
        raw_text = node_input
    elif isinstance(node_input, dict):
        raw_text = json.dumps(node_input)
    else:
        raw_text = str(node_input)

    try:
        payload = json.loads(raw_text)
    except Exception:
        # Fallback if raw text isn't JSON
        payload = {"data": raw_text}

    # Extract base64 details if we have Pub/Sub 'data' structure
    data_content = payload.get("data")
    if isinstance(data_content, str):
        try:
            # Check if it is base64-encoded
            decoded_bytes = base64.b64decode(data_content)
            decoded_str = decoded_bytes.decode("utf-8")
            expense_data = json.loads(decoded_str)
        except Exception:
            # Fallback to plain JSON string or fallback to dictionary parsing
            try:
                expense_data = json.loads(data_content)
            except Exception:
                expense_data = {"raw": data_content}
    elif isinstance(data_content, dict):
        expense_data = data_content
    else:
        # Fallback if data is not present or formatting is flat
        expense_data = payload

    # Extract required fields: amount, submitter, category, description, date
    amount = float(expense_data.get("amount", 0.0))
    submitter = expense_data.get("submitter", "Unknown")
    category = expense_data.get("category", "General")
    description = expense_data.get("description", "No description")
    date = expense_data.get("date", "")

    result = {
        "amount": amount,
        "submitter": submitter,
        "category": category,
        "description": description,
        "date": date,
    }
    logger.info(f"Parsed expense data: {result}")
    return result


def route_expense(ctx: Context, node_input: dict):
    """Routes the expense report based on threshold rules."""
    amount = node_input.get("amount", 0.0)
    
    # Store expense dict in workflow state to be accessed by LlmAgent and downstream nodes
    state_update = {"expense": node_input}
    
    if amount < THRESHOLD:
        logger.info(f"Amount ${amount} is under ${THRESHOLD}. Routing to auto_approve.")
        return Event(output=node_input, route="auto", state=state_update)
    else:
        logger.info(f"Amount ${amount} is ${THRESHOLD} or more. Routing to review_risk.")
        return Event(output=node_input, route="review", state=state_update)


def auto_approve(node_input: dict):
    """Instantly auto-approves expenses under threshold."""
    return {
        "approved": True,
        "reviewer_notes": f"Auto-approved (under ${THRESHOLD})",
    }


def scrub_pii(text: str) -> tuple[str, list[str]]:
    """Redacts SSNs and Credit Card numbers from the text."""
    redacted_categories = []
    
    # Redact SSNs (XXX-XX-XXXX or 9 consecutive digits)
    ssn_pattern = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
    if ssn_pattern.search(text):
        text = ssn_pattern.sub("[REDACTED SSN]", text)
        redacted_categories.append("SSN")
        
    # Redact Credit Cards (standard 16 digit format or 15 digit Amex format)
    cc_pattern = re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b|\b\d{4}[- ]?\d{6}[- ]?\d{5}\b')
    if cc_pattern.search(text):
        text = cc_pattern.sub("[REDACTED CREDIT CARD]", text)
        redacted_categories.append("Credit Card")
        
    return text, redacted_categories


def detect_injection(text: str) -> bool:
    """Detects prompt injection attempts trying to override rules."""
    injection_keywords = [
        "ignore previous", "ignore instruction", "ignore rules", "override",
        "auto-approve", "auto approve", "bypass", "force approval", "force approve",
        "system message", "system prompt", "you are now", "instead of review",
        "under $100", "pretend to be", "acting as", "do not flag", "do not review"
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in injection_keywords)


def security_checkpoint(ctx: Context, node_input: dict):
    """Scrubs personal data and checks for prompt injections."""
    expense = dict(node_input)
    description = expense.get("description", "")
    
    # 1. Scrub personal data
    clean_desc, redacted = scrub_pii(description)
    expense["description"] = clean_desc
    
    # 2. Check prompt injection
    is_injection = detect_injection(clean_desc)
    
    state_update = {
        "expense": expense,
        "redacted_categories": redacted,
        "security_event": is_injection
    }
    
    if is_injection:
        logger.warning("Prompt injection detected in description! Bypassing LLM review.")
        risk_assessment = {
            "risk_score": 10,
            "risk_factors": ["PROMPT INJECTION DETECTED", "Security Policy Violation"],
            "alert_raised": True,
            "summary": "Security Warning: Possible prompt injection attempt detected in description. Bypassed LLM review."
        }
        state_update["risk_assessment"] = risk_assessment
        return Event(output=expense, route="injection", state=state_update)
    else:
        return Event(output=expense, route="clean", state=state_update)


# Risk assessment using the LLM
review_risk_agent = LlmAgent(
    name="review_risk",
    model=MODEL_NAME,
    instruction=(
        "You are an AI financial auditor. Review the expense report details provided in the input "
        "for risk factors and potential anomalies. Assign a risk score from 1 to 10, list the risk "
        "factors, decide if an alert should be raised, and summarize your findings."
    ),
    output_schema=RiskAssessment,
    output_key="risk_assessment",
)


@node(rerun_on_resume=True)
async def human_approval(ctx: Context, node_input: dict) -> AsyncGenerator[Any, None]:
    """Pauses the workflow to wait for human approval/rejection."""
    expense = ctx.state.get("expense", {})
    risk_assessment = ctx.state.get("risk_assessment", {})
    
    # Extract risk info
    risk_score = risk_assessment.get("risk_score", 5)
    summary = risk_assessment.get("summary", "No summary provided.")
    
    redacted = ctx.state.get("redacted_categories", [])
    redacted_str = f" (Redacted: {', '.join(redacted)})" if redacted else ""
    
    # Build prompt message for the human reviewer
    prompt_message = (
        f"\n[ALERT] Expense Review Required (Amount: ${expense.get('amount')})\n"
        f"- Submitter: {expense.get('submitter')}\n"
        f"- Category: {expense.get('category')}\n"
        f"- Description: {expense.get('description')}{redacted_str}\n"
        f"- Date: {expense.get('date')}\n"
        f"- Risk Score: {risk_score}/10\n"
        f"- Risk Summary: {summary}\n"
        f"Do you approve or reject this expense? (Type 'approve' or 'reject'): "
    )
    
    # If the response hasn't been received yet, yield RequestInput and pause
    if not ctx.resume_inputs or "decision" not in ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="decision",
            message=prompt_message
        )
        return

    # Once resumed, process the decision
    decision_val = ctx.resume_inputs["decision"]
    if isinstance(decision_val, dict):
        decision_text = decision_val.get("decision", "")
    else:
        decision_text = str(decision_val)
    decision_text = decision_text.strip().lower()
    approved = "approve" in decision_text
    
    result = {
        "approved": approved,
        "reviewer_notes": f"Human reviewer decision: {decision_text}",
    }
    
    # Output the result and update the workflow state
    yield Event(output=result, state={"approved": approved, "reviewer_notes": result["reviewer_notes"]})


def record_outcome(ctx: Context, node_input: dict):
    """Records final outcome of the approval process."""
    expense = ctx.state.get("expense", {})
    approved = node_input.get("approved", False)
    notes = node_input.get("reviewer_notes", "")
    
    status = "APPROVED" if approved else "REJECTED"
    
    result = {
        "status": status,
        "expense": expense,
        "reviewer_notes": notes,
    }
    
    message = (
        f"Expense Processing Completed.\n"
        f"Status: {status}\n"
        f"Details: Submitter: {expense.get('submitter')}, Amount: ${expense.get('amount')}\n"
        f"Notes: {notes}"
    )
    
    # Emit UI content and final output
    yield Event(
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=message)]
        ),
        state={"final_result": result}
    )
    yield Event(output=result)


# 3. Wire the Workflow Graph
root_workflow = Workflow(
    name="ambient_expense_approval",
    edges=[
        (START, parse_payload),
        (parse_payload, route_expense),
        (route_expense, {"auto": auto_approve, "review": security_checkpoint}),
        (security_checkpoint, {"clean": review_risk_agent, "injection": human_approval}),
        (review_risk_agent, human_approval),
        (human_approval, record_outcome),
        (auto_approve, record_outcome),
    ]
)

# 4. Initialize the App
app = App(
    root_agent=root_workflow,
    name="expense_agent",
    resumability_config=ResumabilityConfig(is_resumable=True)
)

root_agent = root_workflow

