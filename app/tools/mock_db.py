from langchain_core.tools import tool


@tool
def lookup_customer(email: str) -> dict:
    """Look up customer account details by email address."""
    mock_customers = {
        "alice@example.com": {"tier": "premium", "refund_eligible": True, "account_age_days": 365},
        "bob@example.com":   {"tier": "standard", "refund_eligible": True, "account_age_days": 90},
        "carol@example.com": {"tier": "premium", "refund_eligible": False, "account_age_days": 730},
    }
    return mock_customers.get(email, {"tier": "standard", "refund_eligible": True, "account_age_days": 30})


@tool
def calculate_refund(ticket_content: str) -> dict:
    """Calculate the appropriate refund amount based on the ticket content."""
    content_lower = ticket_content.lower()

    if "entire month" in content_lower or "full month" in content_lower:
        return {"amount": 99.0, "reason": "Full monthly charge refund"}
    elif "week" in content_lower or "partial" in content_lower:
        return {"amount": 29.0, "reason": "Partial service disruption refund"}
    elif "charge" in content_lower or "billed" in content_lower:
        return {"amount": 75.0, "reason": "Incorrect billing correction"}
    else:
        return {"amount": 15.0, "reason": "Goodwill credit"}


@tool
def draft_support_response(category: str, issue_summary: str) -> str:
    """Draft a support response for non-refund tickets."""
    templates = {
        "billing": (
            f"Thank you for reaching out about your billing concern. "
            f"We have reviewed your account regarding: {issue_summary}. "
            f"Our billing team will adjust your invoice within 2 business days."
        ),
        "technical": (
            f"Thank you for reporting this technical issue: {issue_summary}. "
            f"Our engineering team has been notified and is investigating. "
            f"Expected resolution time is 4-8 hours."
        ),
    }
    return templates.get(category, f"Thank you for contacting support. We will review your issue: {issue_summary}.")


__all__ = ["lookup_customer", "calculate_refund", "draft_support_response"]
