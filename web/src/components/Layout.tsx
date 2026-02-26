import { Outlet, Link } from "react-router-dom";

export default function Layout() {
  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "1rem" }}>
      <header
        style={{
          borderBottom: "1px solid #eee",
          marginBottom: "1rem",
          paddingBottom: "0.5rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <Link to="/" style={{ textDecoration: "none", color: "inherit" }}>
          <h1 style={{ margin: 0 }}>Story Video</h1>
        </Link>
        <nav>
          <Link to="/settings" style={{ fontSize: "0.9rem" }}>
            Settings
          </Link>
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
