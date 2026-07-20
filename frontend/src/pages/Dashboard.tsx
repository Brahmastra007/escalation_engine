import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getPending, approveTicket } from "../api/tickets";
import type { PendingTicket } from "../types";

export function Dashboard() {
  const queryClient = useQueryClient();

  const { data: tickets, isLoading, error } = useQuery({
    queryKey: ["pending"],
    queryFn: getPending,
    refetchInterval: 5000,
  });

  const mutation = useMutation({
    mutationFn: ({ ticketId, approved }: { ticketId: string; approved: boolean }) =>
      approveTicket(ticketId, approved),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pending"] });
    },
  });

  function handleDecision(ticketId: string, approved: boolean) {
    mutation.mutate({ ticketId, approved });
  }

  if (isLoading) {
    return <p className="text-gray-500">Loading pending tickets...</p>;
  }

  if (error) {
    return <p className="text-red-600">Failed to load tickets. Please try again.</p>;
  }

  if (!tickets || tickets.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 text-lg">No pending approvals</p>
        <p className="text-gray-400 text-sm mt-1">Tickets requiring review will appear here</p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-xl font-semibold text-slate-900 mb-4">
        Pending Approvals ({tickets.length})
      </h2>
      <div className="overflow-x-auto bg-white rounded-lg shadow">
        <table className="w-full text-sm text-left">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 font-medium text-gray-600">Ticket ID</th>
              <th className="px-4 py-3 font-medium text-gray-600">Customer</th>
              <th className="px-4 py-3 font-medium text-gray-600">Category</th>
              <th className="px-4 py-3 font-medium text-gray-600">Action</th>
              <th className="px-4 py-3 font-medium text-gray-600">Draft Email</th>
              <th className="px-4 py-3 font-medium text-gray-600">Decision</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {tickets.map((ticket: PendingTicket) => (
              <tr key={ticket.ticket_id} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <Link
                    to={`/tickets/${ticket.ticket_id}`}
                    className="text-blue-600 hover:underline font-mono"
                  >
                    {ticket.ticket_id.slice(0, 8)}
                  </Link>
                </td>
                <td className="px-4 py-3">{ticket.customer_email}</td>
                <td className="px-4 py-3 capitalize">{ticket.category}</td>
                <td className="px-4 py-3">
                  <span className="font-medium">{ticket.proposed_action.type}</span>
                  {ticket.proposed_action.amount && (
                    <span className="text-red-600 font-semibold ml-2">
                      ${ticket.proposed_action.amount}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="max-w-xs max-h-20 overflow-auto text-xs text-gray-600">
                    {ticket.proposed_action.draft_email}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleDecision(ticket.ticket_id, true)}
                      disabled={mutation.isPending}
                      className="px-3 py-1 bg-emerald-600 text-white text-xs rounded hover:bg-emerald-700 disabled:opacity-50"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => handleDecision(ticket.ticket_id, false)}
                      disabled={mutation.isPending}
                      className="px-3 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700 disabled:opacity-50"
                    >
                      Reject
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
