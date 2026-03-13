import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../App";

// Mock the page components to keep tests focused on routing
vi.mock("../pages/ProjectListPage", () => ({
  default: () => <div data-testid="project-list-page">ProjectListPage</div>,
}));
vi.mock("../pages/CreatePage", () => ({
  default: () => <div data-testid="create-page">CreatePage</div>,
}));
vi.mock("../pages/ProjectPage", () => ({
  default: () => <div data-testid="project-page">ProjectPage</div>,
}));
vi.mock("../pages/SettingsPage", () => ({
  default: () => <div data-testid="settings-page">SettingsPage</div>,
}));

describe("App routing", () => {
  it("renders ProjectListPage at /", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("project-list-page")).toBeInTheDocument();
  });

  it("renders CreatePage at /create", () => {
    render(
      <MemoryRouter initialEntries={["/create"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("create-page")).toBeInTheDocument();
  });

  it("renders ProjectPage at /project/:projectId", () => {
    render(
      <MemoryRouter initialEntries={["/project/test-123"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("project-page")).toBeInTheDocument();
  });

  it("renders SettingsPage at /settings", () => {
    render(
      <MemoryRouter initialEntries={["/settings"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("settings-page")).toBeInTheDocument();
  });
});
