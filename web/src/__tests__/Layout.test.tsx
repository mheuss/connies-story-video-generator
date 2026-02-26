import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../App";

describe("Layout", () => {
  it("renders the app title", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText("Story Video")).toBeInTheDocument();
  });

  it("shows create page at root route", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText(/create/i)).toBeInTheDocument();
  });
});
