from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel
from typing import Literal, Optional

from app.state import TicketState
from app.tools.mock_db import lookup_customer, calculate_refund, draft_support_response


class ProposedAction(BaseModel):
    type: Literal["refund", "support_response"]
    amount: Optional[float] = None
    reason: Optional[str] = None
    draft_email: str


tools = [lookup_customer, calculate_refund, draft_support_response]
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

agent_executor = create_react_agent(llm, tools)
extractor_llm = llm.with_structured_output(ProposedAction)


def resolution_node(state: TicketState) -> dict:
    task_prompt = (
        f"Customer email: {state['customer_email']}\n"
        f"Category: {state['category']}\n"
        f"Ticket: {state['ticket_content']}\n\n"
        "Use the available tools to:\n"
        "1. Look up the customer account\n"
        "2. If category is 'refund': calculate the refund amount\n"
        "3. If category is 'billing' or 'technical': draft a support response\n"
        "Then summarize what action you propose to take and write a short draft email to the customer."
    )

    agent_result = agent_executor.invoke({
        "messages": [HumanMessage(content=task_prompt)]
    })

    final_message = agent_result["messages"][-1].content

    extraction_prompt = (
        f"Based on this agent output, extract the proposed action as structured data:\n\n{final_message}"
    )
    proposed: ProposedAction = extractor_llm.invoke([HumanMessage(content=extraction_prompt)])
    proposed_dict = proposed.model_dump()

    print(f"[Resolution] Ticket {state['ticket_id']} proposed action: {proposed_dict}")

    return {"proposed_action": proposed_dict, "status": "processing"}
