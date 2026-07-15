from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.state import TicketState
from app.agents.triage import triage_node
from app.agents.resolution import resolution_node
from app.agents.human_review import human_review_node
from app.agents.dispatcher import dispatcher_node

# Module-level singleton — shared across all FastAPI requests.
# MemorySaver holds all checkpoint state in a plain Python dict in memory.
checkpointer = MemorySaver()


def _needs_human_review(state: TicketState) -> str:
    """Routing function: send to human_review only for refunds over $50."""
    proposed = state.get("proposed_action", {})
    if proposed.get("type") == "refund" and (proposed.get("amount") or 0) > 50:
        return "human_review"
    return "dispatcher"


def build_graph():
    builder = StateGraph(TicketState)

    builder.add_node("triage",       triage_node)
    builder.add_node("resolution",   resolution_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("dispatcher",   dispatcher_node)

    builder.add_edge(START,          "triage")
    builder.add_edge("triage",       "resolution")

    # After resolution, route based on whether human approval is needed
    builder.add_conditional_edges("resolution", _needs_human_review)

    builder.add_edge("human_review", "dispatcher")
    builder.add_edge("dispatcher",   END)

    return builder.compile(checkpointer=checkpointer)


# Compile once at import time — reused for every ticket
graph = build_graph()
