import os
from contextlib import asynccontextmanager
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from langsmith import traceable
from langgraph.types import Command
from pydantic import BaseModel

from app.graph import graph
from app.state import TicketState

# All submitted ticket IDs — needed to iterate over tickets for /api/pending,
# since LangGraph has no "list all threads" API.
_all_ticket_ids: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    yield


app = FastAPI(title="Escalation Engine", lifespan=lifespan)


# --- Request / Response models ---

class TicketRequest(BaseModel):
    customer_email: str
    ticket_content: str

class ApprovalRequest(BaseModel):
    approved: bool


# --- Helpers ---

def _get_ticket_state(ticket_id: str) -> dict | None:
    """Read the latest checkpoint state for a given ticket_id."""
    config = {"configurable": {"thread_id": ticket_id}}
    snapshot = graph.get_state(config)
    if not snapshot or not snapshot.values:
        return None
    return snapshot.values


@traceable(name="run-ticket-graph")
def _run_graph(initial_state: TicketState, config: dict):
    """Run the graph synchronously (called from a background thread)."""
    try:
        graph.invoke(initial_state, config)
        # If the graph paused at human_review, mark the ticket as pending_approval.
        # snapshot.next is non-empty when execution is frozen at an interrupt.
        snapshot = graph.get_state(config)
        if snapshot.next:
            graph.update_state(config, {"status": "pending_approval"})
            print(f"[Graph] Ticket {initial_state['ticket_id']} waiting for human approval")
    except Exception as e:
        print(f"[Graph] Error for ticket {initial_state['ticket_id']}: {e}")


@traceable(name="resume-ticket-graph")
def _resume_graph(ticket_id: str, approved: bool):
    """Resume a paused graph after human approval/rejection."""
    config = {"configurable": {"thread_id": ticket_id}}
    try:
        # Command(resume=...) is the value returned by interrupt() inside human_review_node
        graph.invoke(Command(resume={"approved": approved}), config)
    except Exception as e:
        print(f"[Graph] Resume error for ticket {ticket_id}: {e}")


# --- Endpoints ---

@app.post("/api/tickets", status_code=202)
async def submit_ticket(req: TicketRequest, background_tasks: BackgroundTasks):
    ticket_id = str(uuid4())
    config = {
        "configurable": {"thread_id": ticket_id},
        "run_name": f"ticket-{ticket_id[:8]}",
        "metadata": {
            "ticket_id": ticket_id,
            "customer_email": req.customer_email,
        },
    }

    initial_state: TicketState = {
        "ticket_id":      ticket_id,
        "customer_email": req.customer_email,
        "ticket_content": req.ticket_content,
        "category":       "",
        "proposed_action": {},
        "approved":       None,
        "final_email":    "",
        "status":         "processing",
    }

    _all_ticket_ids.add(ticket_id)
    background_tasks.add_task(_run_graph, initial_state, config)
    return {"ticket_id": ticket_id, "status": "processing"}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: str):
    state = _get_ticket_state(ticket_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return state


@app.get("/api/pending")
async def get_pending():
    pending = []
    for ticket_id in _all_ticket_ids:
        config = {"configurable": {"thread_id": ticket_id}}
        snapshot = graph.get_state(config)
        if not snapshot or not snapshot.values:
            continue
        state = snapshot.values
        if state.get("status") == "pending_approval":
            pending.append({
                "ticket_id":       state.get("ticket_id"),
                "customer_email":  state.get("customer_email"),
                "ticket_content":  state.get("ticket_content"),
                "category":        state.get("category"),
                "proposed_action": state.get("proposed_action"),
            })
    return pending


@app.post("/api/approve/{ticket_id}")
async def approve_ticket(ticket_id: str, body: ApprovalRequest, background_tasks: BackgroundTasks):
    state = _get_ticket_state(ticket_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if state.get("status") != "pending_approval":
        raise HTTPException(status_code=400, detail="Ticket is not pending approval")

    # Mark approved in the checkpoint state so dispatcher_node can read it
    config = {"configurable": {"thread_id": ticket_id}}
    graph.update_state(config, {"approved": body.approved, "status": "processing"})

    background_tasks.add_task(_resume_graph, ticket_id, body.approved)
    return {"ticket_id": ticket_id, "approved": body.approved}


# Serve the HTML dashboard at /
app.mount("/", StaticFiles(directory="static", html=True), name="static")
