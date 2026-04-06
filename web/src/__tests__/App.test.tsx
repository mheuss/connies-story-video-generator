import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import App from "../App";

/** Renders the current pathname so tests can assert on redirect targets. */
function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-path">{location.pathname}</div>;
}

// Mock the page components to keep tests focused on routing
vi.mock("../pages/ProjectListPage", () => ({
  default: () => <div data-testid="project-list-page">ProjectListPage</div>,
}));
vi.mock("../pages/UnifiedProjectPage", () => ({
  UnifiedProjectPage: () => (
    <div data-testid="project-page">UnifiedProjectPage</div>
  ),
}));
vi.mock("../pages/SettingsPage", () => ({
  default: () => <div data-testid="settings-page">SettingsPage</div>,
}));

describe("App routing", () => {
  it("renders ProjectListPage at /", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("project-list-page")).toBeInTheDocument();
  });

  it("redirects /create to /project/new", async () => {
    render(
      <MemoryRouter initialEntries={["/create"]}>
        <App />
        <LocationProbe />
      </MemoryRouter>,
    );
    // /create redirects to /project/new, which renders UnifiedProjectPage
    expect(await screen.findByTestId("project-page")).toBeInTheDocument();
    expect(screen.getByTestId("location-path")).toHaveTextContent("/project/new");
  });

  it("renders UnifiedProjectPage at /project/:projectId", async () => {
    render(
      <MemoryRouter initialEntries={["/project/test-123"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("project-page")).toBeInTheDocument();
  });

  it("renders SettingsPage at /settings", async () => {
    render(
      <MemoryRouter initialEntries={["/settings"]}>
        <App />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
  });

  it("redirects unknown routes to the project list page", async () => {
    render(
      <MemoryRouter initialEntries={["/does-not-exist"]}>
        <App />
        <LocationProbe />
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("project-list-page")).toBeInTheDocument();
    expect(screen.getByTestId("location-path")).toHaveTextContent("/");
  });
});
