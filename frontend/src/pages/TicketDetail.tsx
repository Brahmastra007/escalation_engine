import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getTicket, approveTicket } from "../api/tickets";

export function TicketDetail() {
  const { ticketId } = useParams<{ ticketId: string }>();
  const queryClient = useQueryClient();

  const { data: ticket, isLoading, error } = useQuery({
    queryKey: ["ticket", ticketId],
    queryFn: () => getTicket(ticketId!),
    enabled: !!ticketId,
  });

  const mutation = useMutation({
    mutationFn: (approved: boolean) => approveTicket(ticketId!, approved),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ticket", ticketId] });
      queryClient.invalidateQueries({ queryKey: ["pending"] });
    },
  });

  if (isLoading) {
    return <p className="text-gray-500">Loading ticket...</p>;
  }

  if (error || !ticket) {
    return <p className="text-red-600">Ticket not found.</p>;
  }

  const statusColors: Record<string, string> = {
    processing: "bg-yellow-100 text-yellow-800",
    pending_approval: "bg-orange-100 text-orange-800",
    resolved: "bg-emerald-100 text-emerald-800",
    rejected: "bg-red-100 text-red-800",
  };

  return (
    <div className="max-w-2xl">
      <Link to="/" className="text-sm text-blue-600 hover:underline mb-4 inline-block">
        &larr; Back to Dashboard
      </Link>

      <div className="bg-white rounded-lg shadow p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold text-slate-900 font-mono">
            {ticket.ticket_id.slice(0, 8)}...
          </h2>
          <span
            className={`px-3 py-1 rounded-full text-xs font-medium ${statusColors[ticket.status] || "bg-gray-100 text-gray-800"}`}
          >
            {ticket.status}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-gray-500">Customer</p>
            <p className="font-medium">{ticket.customer_email}</p>
          </div>
          <div>
            <p className="text-gray-500">Category</p>
            <p className="font-medium capitalize">{ticket.category || "—"}</p>
          </div>
        </div>

        <div className="text-sm">
          <p className="text-gray-500 mb-1">Ticket Content</p>
          <p className="bg-gray-50 rounded p-3">{ticket.ticket_content}</p>
        </div>

        {ticket.proposed_action?.type && (
          <div className="text-sm">
            <p className="text-gray-500 mb-1">Proposed Action</p>
            <div className="bg-gray-50 rounded p-3">
              <p>
                <span className="font-medium">{ticket.proposed_action.type}</span>
                {ticket.proposed_action.amount && (
                  <span className="text-red-600 font-semibold ml-2">
                    ${ticket.proposed_action.amount}
                  </span>
                )}
              </p>
              {ticket.proposed_action.draft_email && (
                <p className="mt-2 text-xs text-gray-600 whitespace-pre-wrap">
                  {ticket.proposed_action.draft_email}
                </p>
              )}
            </div>
          </div>
        )}

        {ticket.final_email && (
          <div className="text-sm">
            <p className="text-gray-500 mb-1">Final Email</p>
            <p className="bg-gray-50 rounded p-3 whitespace-pre-wrap">{ticket.final_email}</p>
          </div>
        )}

        {ticket.status === "pending_approval" && (
          <div className="flex gap-3 pt-2">
            <button
              onClick={() => mutation.mutate(true)}
              disabled={mutation.isPending}
              className="px-4 py-2 bg-emerald-600 text-white rounded-md hover:bg-emerald-700 disabled:opacity-50"
            >
              Approve
            </button>
            <button
              onClick={() => mutation.mutate(false)}
              disabled={mutation.isPending}
              className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50"
            >
              Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
