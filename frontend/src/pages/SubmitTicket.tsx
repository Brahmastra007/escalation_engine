import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { submitTicket } from "../api/tickets";

export function SubmitTicket() {
  const [customerEmail, setCustomerEmail] = useState("");
  const [ticketContent, setTicketContent] = useState("");

  const mutation = useMutation({
    mutationFn: () => submitTicket(customerEmail, ticketContent),
    onSuccess: () => {
      setCustomerEmail("");
      setTicketContent("");
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    mutation.mutate();
  }

  return (
    <div className="max-w-lg">
      <h2 className="text-xl font-semibold text-slate-900 mb-4">Submit a Ticket</h2>

      {mutation.isSuccess && (
        <div className="mb-4 bg-emerald-50 border border-emerald-200 rounded-md px-4 py-3">
          <p className="text-emerald-800 text-sm">
            Ticket submitted successfully!{" "}
            <Link
              to={`/tickets/${mutation.data.ticket_id}`}
              className="font-medium underline"
            >
              {mutation.data.ticket_id.slice(0, 8)}...
            </Link>
          </p>
        </div>
      )}

      {mutation.isError && (
        <div className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
          Failed to submit ticket. Please try again.
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4 bg-white rounded-lg shadow p-6">
        <div>
          <label htmlFor="customer-email" className="block text-sm font-medium text-gray-700 mb-1">
            Customer Email
          </label>
          <input
            id="customer-email"
            type="email"
            value={customerEmail}
            onChange={(e) => setCustomerEmail(e.target.value)}
            required
            placeholder="customer@example.com"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-slate-500"
          />
        </div>
        <div>
          <label htmlFor="ticket-content" className="block text-sm font-medium text-gray-700 mb-1">
            Ticket Content
          </label>
          <textarea
            id="ticket-content"
            value={ticketContent}
            onChange={(e) => setTicketContent(e.target.value)}
            required
            rows={5}
            placeholder="Describe the customer's issue..."
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-slate-500 resize-y"
          />
        </div>
        <button
          type="submit"
          disabled={mutation.isPending}
          className="px-4 py-2 bg-slate-900 text-white rounded-md hover:bg-slate-800 disabled:opacity-50"
        >
          {mutation.isPending ? "Submitting..." : "Submit Ticket"}
        </button>
      </form>
    </div>
  );
}
