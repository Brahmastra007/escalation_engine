// Response from POST /api/auth/login
export interface LoginResponse {
  access_token: string;
  token_type: string;
}

// Response from GET /api/auth/me
export interface User {
  user_id: string;
  email: string;
}

// Response from POST /api/tickets
export interface SubmitTicketResponse {
  ticket_id: string;
  status: string;
}

// Each item in the array from GET /api/pending
export interface PendingTicket {
  ticket_id: string;
  customer_email: string;
  ticket_content: string;
  category: string;
  proposed_action: {
    type?: string;
    amount?: number;
    draft_email?: string;
  };
}

// Response from GET /api/tickets/:id
export interface TicketDetail {
  ticket_id: string;
  customer_email: string;
  ticket_content: string;
  category: string;
  proposed_action: {
    type?: string;
    amount?: number;
    draft_email?: string;
  };
  approved: boolean | null;
  final_email: string;
  status: string;
}

// Response from POST /api/approve/:id
export interface ApproveResponse {
  ticket_id: string;
  approved: boolean;
}
