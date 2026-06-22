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

import os
from pathlib import Path
import dotenv

# Load .env file explicitly
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    dotenv.load_dotenv(dotenv_path=env_path)
else:
    parent_env_path = Path(__file__).resolve().parent.parent / ".env"
    if parent_env_path.exists():
        dotenv.load_dotenv(dotenv_path=parent_env_path)

from pydantic import BaseModel, Field

from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.models import Gemini
from google.adk.workflow import Workflow, START
from google.genai import types


# Define Pydantic schemas for LLM Agent I/O
class ClassificationResult(BaseModel):
    is_shipping_related: bool = Field(
        description="True if the user query is related to shipping (rates, tracking, delivery, returns, etc.), False if it is unrelated."
    )
    reason: str = Field(
        description="Brief explanation of why the query was classified this way."
    )


class FAQResponse(BaseModel):
    answer: str = Field(
        description="The polite, helpful, and accurate response to the user's shipping question."
    )


# Shared Gemini Model Configuration
model = Gemini(
    model="gemini-flash-latest",
    retry_options=types.HttpRetryOptions(attempts=3),
)

# 1. Classifier Agent Node
classifier = Agent(
    name="classifier",
    model=model,
    instruction=(
        "You are a classification assistant for a shipping company. "
        "Your task is to classify whether the user's query is related to shipping (such as shipping rates, shipment tracking, package delivery, product returns/refunds, etc.) or unrelated to shipping. "
        "Provide your output strictly according to the ClassificationResult schema."
    ),
    output_schema=ClassificationResult,
    output_key="classification",
    mode="single_turn",
)


# 2. Routing Function Node
def route_query(node_input: dict | None) -> Event:
    if not node_input:
        return Event(output={}, route="unrelated")
    is_shipping = node_input.get("is_shipping_related", False)
    if is_shipping:
        return Event(output=node_input, route="shipping")
    else:
        return Event(output=node_input, route="unrelated")


# 3. Shipping FAQ Agent Node
shipping_faq_agent = Agent(
    name="shipping_faq_agent",
    model=model,
    instruction=(
        "You are a customer support FAQ agent for a shipping company. "
        "Answer the customer's query about shipping (rates, tracking, delivery, returns, etc.) politely, clearly, and accurately. "
        "Make your responses about shipping rates extremely playful, enthusiastic, and loaded with helpful emojis! 🎉🚀 "
        "Be sure to enthusiastically highlight our awesome Free Shipping threshold: FREE standard shipping on all orders over $50! 🎁✨ "
        "If you do not have specific data for a tracking number, answer using general helpful policies of a standard shipping company (e.g., standard delivery takes 3-5 days, returns are accepted within 30 days, etc.). "
        "Respond strictly according to the FAQResponse schema."
    ),
    output_schema=FAQResponse,
    output_key="faq_response",
    mode="single_turn",
)


# 4. Output Formatting Function Node (for FAQ agent output)
def format_faq_response(node_input: dict | None) -> Event:
    if not node_input:
        answer = "I'm sorry, I couldn't generate an answer."
    else:
        answer = node_input.get("answer", "")
    return Event(
        output=answer,
        content=types.Content(role="model", parts=[types.Part.from_text(text=answer)]),
    )


# 5. Polite Decline Function Node
def politely_decline(ctx: Context, node_input: dict | None = None) -> Event:
    message = (
        "I'm sorry, but I can only answer questions related to shipping "
        "(such as rates, tracking, delivery, or returns). How can I help "
        "you with your shipping needs today?"
    )
    return Event(
        output=message,
        content=types.Content(role="model", parts=[types.Part.from_text(text=message)]),
    )


# Assemble the Workflow Graph
root_agent = Workflow(
    name="customer_support_workflow",
    edges=[
        (START, classifier),
        (classifier, route_query),
        (
            route_query,
            {
                "shipping": shipping_faq_agent,
                "unrelated": politely_decline,
            },
        ),
        (shipping_faq_agent, format_faq_response),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
