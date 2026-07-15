from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel
from typing import Literal

from app.state import TicketState


class CategoryOutput(BaseModel):
    category: Literal["billing", "technical", "refund"]


llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
structured_llm = llm.with_structured_output(CategoryOutput)


def triage_node(state: TicketState) -> dict:
    messages = [
        SystemMessage(content=(
            "You are a customer support triage agent. "
            "Classify the incoming ticket into exactly one of these categories: "
            "billing (payment, invoice, subscription charges), "
            "technical (bugs, errors, service outages), "
            "refund (customer wants money back). "
            "Reply with the category only."
        )),
        HumanMessage(content=state["ticket_content"]),
    ]

    result: CategoryOutput = structured_llm.invoke(messages)

    print(f"[Triage] Ticket {state['ticket_id']} classified as: {result.category}")

    return {"category": result.category, "status": "processing"}
