import { Outlet, Link } from "react-router-dom";

export default function Layout() {
  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "1rem" }}>
      <header
        style={{
          borderBottom: "1px solid #eee",
          marginBottom: "1rem",
          paddingBottom: "0.5rem",
        }}
      >
        <Link to="/" style={{ textDecoration: "none", color: "inherit" }}>
          <h1 style={{ margin: 0 }}>Story Video</h1>
        </Link>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
