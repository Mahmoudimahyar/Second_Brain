/// <reference types="vitest" />
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { VerdictPicker } from "./VerdictPicker";

describe("VerdictPicker", () => {
  it("renders all four verdict buttons", () => {
    render(<VerdictPicker onCommit={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refine" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Defer" })).toBeInTheDocument();
  });

  it("calls onCommit with the chosen verdict + notes", () => {
    const fn = vi.fn();
    render(<VerdictPicker onCommit={fn} />);

    const notes = screen.getByLabelText("Reviewer notes");
    fireEvent.change(notes, { target: { value: "looks good" } });

    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(fn).toHaveBeenCalledWith("accept", "looks good");
  });

  it("disables buttons when disabled prop is set", () => {
    render(<VerdictPicker onCommit={vi.fn()} disabled />);
    expect(screen.getByRole("button", { name: "Accept" })).toBeDisabled();
    expect(screen.getByLabelText("Reviewer notes")).toBeDisabled();
  });
});
