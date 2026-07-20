import client from "./client";
import type {
  ApproveResponse,
  PendingTicket,
  SubmitTicketResponse,
  TicketDetail,
} from "../types";

export async function submitTicket(
  customerEmail: string,
  ticketContent: string
): Promise<SubmitTicketResponse> {
  const response = await client.post<SubmitTicketResponse>("/tickets", {
    customer_email: customerEmail,
    ticket_content: ticketContent,
  });
  return response.data;
}

export async function getPending(): Promise<PendingTicket[]> {
  const response = await client.get<PendingTicket[]>("/pending");
  return response.data;
}

export async function getTicket(ticketId: string): Promise<TicketDetail> {
  const response = await client.get<TicketDetail>(`/tickets/${ticketId}`);
  return response.data;
}

export async function approveTicket(
  ticketId: string,
  approved: boolean
): Promise<ApproveResponse> {
  const response = await client.post<ApproveResponse>(
    `/approve/${ticketId}`,
    { approved }
  );
  return response.data;
}
