import { Outlet, Link } from "react-router-dom";

export default function Layout() {
  return (
    <div className="max-w-4xl mx-auto px-4">
      <header className="flex items-center justify-between py-4 border-b border-border mb-8">
        <Link to="/" className="text-xl font-bold text-foreground hover:text-foreground/80">
          Story Video
        </Link>
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
