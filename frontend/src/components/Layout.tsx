import { Link, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-slate-900 text-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-lg font-semibold">Escalation Engine</h1>
            <nav className="flex gap-4 text-sm">
              <Link to="/" className="hover:text-gray-300">
                Dashboard
              </Link>
              <Link to="/submit" className="hover:text-gray-300">
                Submit Ticket
              </Link>
            </nav>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-gray-300">{user?.email}</span>
            <button
              onClick={logout}
              className="px-3 py-1 bg-slate-700 rounded hover:bg-slate-600"
            >
              Logout
            </button>
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
