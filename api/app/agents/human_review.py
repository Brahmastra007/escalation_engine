from langgraph.types import interrupt

from app.state import TicketState


def human_review_node(state: TicketState) -> dict:
    proposed = state["proposed_action"]

    print(f"[HumanReview] Ticket {state['ticket_id']} waiting for approval — refund ${proposed.get('amount')}")

    # Freeze the graph here. Returns only when POST /api/approve is called.
    # The dict passed to interrupt() is what appears in snapshot.tasks[0].interrupts[0].value
    # and is what gets passed back as resume_data when the human approves/rejects.
    resume_data = interrupt(proposed)

    approved = resume_data.get("approved", False)
    print(f"[HumanReview] Ticket {state['ticket_id']} decision: {'approved' if approved else 'rejected'}")

    return {
        "approved": approved,
        "status": "processing",
    }
