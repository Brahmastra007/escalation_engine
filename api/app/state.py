from typing import TypedDict, Optional


class TicketState(TypedDict):
    ticket_id: str
    customer_email: str
    ticket_content: str
    category: str               # "billing" | "technical" | "refund"
    proposed_action: dict       # {"type": ..., "amount": ..., "draft_email": ...}
    approved: Optional[bool]    # None until human acts; True=approve, False=reject
    final_email: str
    status: str                 # "processing" | "pending_approval" | "complete" | "rejected"
