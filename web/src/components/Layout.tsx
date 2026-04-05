import { Outlet, Link } from "react-router-dom";
import { Home } from "lucide-react";

export default function Layout() {
  return (
    <div className="max-w-4xl mx-auto px-4">
      <header className="flex items-center justify-between py-4 border-b border-border mb-8">
        <div className="flex items-center gap-4">
          <span className="text-xl font-bold text-foreground">Story Video</span>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 rounded-md bg-muted px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          >
            <Home className="h-4 w-4" />
            Home
          </Link>
        </div>
        <Link to="/settings" className="text-sm text-muted-foreground hover:text-foreground">
          Settings
        </Link>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
