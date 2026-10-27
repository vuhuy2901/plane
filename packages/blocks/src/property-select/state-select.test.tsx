import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { useSelectContext } from "../select/context";
import { StateSelect } from "./state-select";
import type { StateOption } from "./state-select";

const state: StateOption = { id: "todo", name: "To Do", color: "#3E63DD", group: "unstarted" };

function ViewWorkflow({ onView }: { onView: () => void }) {
  const { close } = useSelectContext();
  return (
    <button
      type="button"
      onClick={() => {
        close();
        onView();
      }}
    >
      View workflow
    </button>
  );
}

describe("StateSelect workflow footer", () => {
  it("keeps View workflow below the options even when the search has no matches", async () => {
    const user = userEvent.setup();
    render(
      <StateSelect
        value={state}
        getValues={() => Promise.resolve({ results: [state], next_page_results: false })}
        onChange={vi.fn()}
        variant="pill-sm"
        footer={<ViewWorkflow onView={vi.fn()} />}
      />
    );
    await user.click(screen.getByRole("button", { name: "To Do" }));
    const search = await screen.findByRole("combobox", { name: /search states/i });
    const action = await screen.findByRole("button", { name: "View workflow" });
    expect(within(screen.getByRole("listbox")).queryByRole("button", { name: "View workflow" })).toBeNull();
    await user.type(search, "missing state");
    expect(screen.getByRole("button", { name: "View workflow" })).toBe(action);
  });

  it("opens the viewer and closes the dropdown without changing the selected state", async () => {
    const user = userEvent.setup();
    const onView = vi.fn();
    const onChange = vi.fn();
    const onClose = vi.fn();
    render(
      <StateSelect
        value={state}
        getValues={() => Promise.resolve({ results: [state], next_page_results: false })}
        onChange={onChange}
        onClose={onClose}
        variant="pill-sm"
        footer={<ViewWorkflow onView={onView} />}
      />
    );
    await user.click(screen.getByRole("button", { name: "To Do" }));
    await user.click(await screen.findByRole("button", { name: "View workflow" }));
    expect(onView).toHaveBeenCalledOnce();
    expect(onClose).toHaveBeenCalledOnce();
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("StateSelect workflow transition navigation", () => {
  const currentState: StateOption = {
    id: "state-ready",
    name: "Ready for Review",
    color: "#F59E0B",
    group: "unstarted",
    order: 1,
  };

  const transitions: StateOption[] = [
    {
      id: "trans-start-review",
      targetStateId: "state-in-review",
      name: "In Review",
      transitionName: "Start Review",
      color: "#3B82F6",
      group: "started",
      direction: "forward",
      transitionId: "t-1",
      order: 2,
    },
    {
      id: "trans-request-changes",
      targetStateId: "state-needs-changes",
      name: "Needs Changes",
      transitionName: "Request Changes",
      color: "#EF4444",
      group: "unstarted",
      direction: "backward",
      transitionId: "t-2",
      order: 3,
    },
  ];

  it("displays Current State in a dedicated header and excludes it from transition options", async () => {
    const user = userEvent.setup();
    render(
      <StateSelect
        value={currentState}
        isWorkflowMode
        variant="pill-sm"
        getValues={() => Promise.resolve({ results: transitions, next_page_results: false })}
        onChange={vi.fn()}
      />
    );

    await user.click(screen.getByRole("button", { name: "Ready for Review" }));

    // Verify dedicated header exists
    const header = await screen.findByTestId("workflow-current-state-header");
    expect(within(header).getByText("Current State")).toBeDefined();
    expect(within(header).getByText("Ready for Review")).toBeDefined();

    // Verify options list contains only available transitions, not current state
    const listbox = screen.getByRole("listbox");
    expect(within(listbox).getByText("AVAILABLE TRANSITIONS")).toBeDefined();
    expect(within(listbox).getByText("In Review")).toBeDefined();
    expect(within(listbox).getByText("Start Review")).toBeDefined();
    expect(within(listbox).getByText("Needs Changes")).toBeDefined();
    expect(within(listbox).getByText("Request Changes")).toBeDefined();

    // Current state must not be an option in the listbox
    expect(within(listbox).queryByRole("option", { name: /Ready for Review/i })).toBeNull();
  });

  it("calls onChange with targetStateId and transitionId when transition is selected", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <StateSelect
        value={currentState}
        isWorkflowMode
        variant="pill-sm"
        getValues={() => Promise.resolve({ results: transitions, next_page_results: false })}
        onChange={onChange}
      />
    );

    await user.click(screen.getByRole("button", { name: "Ready for Review" }));
    const option = await screen.findByRole("option", { name: /Start Review/i });
    await user.click(option);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("state-in-review", "t-1");
  });

  it("filters transitions by target state name and transition name during search", async () => {
    const user = userEvent.setup();
    render(
      <StateSelect
        value={currentState}
        isWorkflowMode
        variant="pill-sm"
        getValues={(params) => {
          const q = params?.search?.toLowerCase().trim();
          const results = q
            ? transitions.filter(
                (t) =>
                  t.name.toLowerCase().includes(q) ||
                  (t.transitionName && t.transitionName.toLowerCase().includes(q))
              )
            : transitions;
          return Promise.resolve({ results, next_page_results: false });
        }}
        onChange={vi.fn()}
      />
    );

    await user.click(screen.getByRole("button", { name: "Ready for Review" }));
    const search = await screen.findByRole("combobox", { name: /search states/i });

    // Search by transition name
    await user.type(search, "Request Changes");
    await waitFor(() => {
      expect(screen.getByText("Needs Changes")).toBeDefined();
      expect(screen.queryByText("In Review")).toBeNull();
    });

    // Clear and search by target state name
    await user.clear(search);
    await user.type(search, "In Review");
    await waitFor(() => {
      expect(screen.getByText("In Review")).toBeDefined();
      expect(screen.queryByText("Needs Changes")).toBeNull();
    });
  });

  it("handles empty outgoing transitions gracefully with Current State header preserved", async () => {
    const user = userEvent.setup();
    render(
      <StateSelect
        value={currentState}
        isWorkflowMode
        variant="pill-sm"
        getValues={() => Promise.resolve({ results: [], next_page_results: false })}
        onChange={vi.fn()}
      />
    );

    await user.click(screen.getByRole("button", { name: "Ready for Review" }));
    const header = await screen.findByTestId("workflow-current-state-header");
    expect(within(header).getByText("Ready for Review")).toBeDefined();

    const listbox = screen.getByRole("listbox");
    expect(within(listbox).queryAllByRole("option")).toHaveLength(0);
  });
});
