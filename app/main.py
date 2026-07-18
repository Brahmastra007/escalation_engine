import os
from contextlib import asynccontextmanager
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from langsmith import traceable
from langgraph.types import Command
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from sqlalchemy.orm import Session

from app.db import Ticket, get_db, get_session, init_db
from app.graph import build_graph
from app.state import TicketState


REQUIRED_ENV_VARS = ["OPENAI_API_KEY", "DATABASE_URL"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {missing}")
    database_url = os.environ["DATABASE_URL"]

    # Initialize SQLAlchemy — creates the tickets table if it doesn't exist.
    init_db(database_url)

    # Initialize the LangGraph checkpointer — creates its own internal tables.
    pool = ConnectionPool(
        conninfo=database_url,
        max_size=10,
        open=True,
        kwargs={
            "autocommit": True,      # Required for schema migration persistence
            "row_factory": dict_row  # Required for dictionary-style syntax matching
        }
    )

    checkpointer = PostgresSaver(pool)
    checkpointer.setup()

    app.state.graph = build_graph(checkpointer)
    yield
    pool.close()


app = FastAPI(title="Escalation Engine", lifespan=lifespan)


# --- Request / Response models ---

class TicketRequest(BaseModel):
    customer_email: str
    ticket_content: str

class ApprovalRequest(BaseModel):
    approved: bool


# --- Helpers ---

def _get_ticket_state(graph, ticket_id: str) -> dict | None:
    """Read the latest checkpoint state for a given ticket_id."""
    config = {"configurable": {"thread_id": ticket_id}}
    snapshot = graph.get_state(config)
    if not snapshot or not snapshot.values:
        return None
    return snapshot.values


@traceable(name="run-ticket-graph")
def _run_graph(graph, initial_state: TicketState, config: dict):
    """Run the graph synchronously (called from a background thread)."""
    try:
        graph.invoke(initial_state, config)
        # If the graph paused at human_review, mark the ticket as pending_approval.
        # snapshot.next is non-empty when execution is frozen at an interrupt.
        snapshot = graph.get_state(config)
        if snapshot.next:
            graph.update_state(config, {"status": "pending_approval"})
            status = "pending_approval"
            print(f"[Graph] Ticket {initial_state['ticket_id']} waiting for human approval")
        else:
            status = "resolved"

        state = snapshot.values
        with get_session() as session:
            ticket = session.get(Ticket, initial_state["ticket_id"])
            ticket.status = status
            ticket.category = state.get("category", "")
            ticket.proposed_action = state.get("proposed_action", {})
            session.commit()
    except Exception as e:
        print(f"[Graph] Error for ticket {initial_state['ticket_id']}: {e}")


@traceable(name="resume-ticket-graph")
def _resume_graph(graph, ticket_id: str, approved: bool):
    """Resume a paused graph after human approval/rejection."""
    config = {"configurable": {"thread_id": ticket_id}}
    try:
        # Command(resume=...) is the value returned by interrupt() inside human_review_node
        graph.invoke(Command(resume={"approved": approved}), config)
        with get_session() as session:
            ticket = session.get(Ticket, ticket_id)
            ticket.status = "resolved"
            session.commit()
    except Exception as e:
        print(f"[Graph] Resume error for ticket {ticket_id}: {e}")


# --- Endpoints ---

@app.post("/api/tickets", status_code=202)
async def submit_ticket(req: TicketRequest, background_tasks: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    graph = request.app.state.graph
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

    db.add(Ticket(
        ticket_id=ticket_id,
        customer_email=req.customer_email,
        ticket_content=req.ticket_content,
    ))
    db.commit()

    background_tasks.add_task(_run_graph, graph, initial_state, config)
    return {"ticket_id": ticket_id, "status": "processing"}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, request: Request):
    graph = request.app.state.graph
    state = _get_ticket_state(graph, ticket_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return state


@app.get("/api/pending")
async def get_pending(db: Session = Depends(get_db)):
    tickets = db.query(Ticket).filter(Ticket.status == "pending_approval").all()
    return [
        {
            "ticket_id":       t.ticket_id,
            "customer_email":  t.customer_email,
            "ticket_content":  t.ticket_content,
            "category":        t.category,
            "proposed_action": t.proposed_action,
        }
        for t in tickets
    ]


@app.post("/api/approve/{ticket_id}")
async def approve_ticket(ticket_id: str, body: ApprovalRequest, background_tasks: BackgroundTasks, request: Request):
    graph = request.app.state.graph
    state = _get_ticket_state(graph, ticket_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if state.get("status") != "pending_approval":
        raise HTTPException(status_code=400, detail="Ticket is not pending approval")

    background_tasks.add_task(_resume_graph, graph, ticket_id, body.approved)
    return {"ticket_id": ticket_id, "approved": body.approved}


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve the HTML dashboard at /
app.mount("/", StaticFiles(directory="static", html=True), name="static")
