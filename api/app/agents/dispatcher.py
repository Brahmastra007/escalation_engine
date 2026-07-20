from app.state import TicketState


def dispatcher_node(state: TicketState) -> dict:
    # If a human explicitly rejected this ticket, close it without sending.
    if state.get("approved") is False:
        print(f"[Dispatcher] Ticket {state['ticket_id']} was rejected by human. No email sent.")
        return {"status": "rejected", "final_email": ""}

    proposed = state["proposed_action"]
    draft = proposed.get("draft_email", "")

    # Compose the final outbound email
    final_email = (
        f"To: {state['customer_email']}\n"
        f"Subject: Re: Your Support Ticket #{state['ticket_id']}\n"
        f"\n"
        f"{draft}"
    )

    # In production: call an email API here (SendGrid, SES, etc.)
    print(f"[Dispatcher] Sending email for ticket {state['ticket_id']}:\n{final_email}")

    return {"final_email": final_email, "status": "complete"}
