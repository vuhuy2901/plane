import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { WorkItemTypeSelect } from "./work-item-type-select";
import type { WorkItemTypeOption } from "./work-item-type-select";

const options: WorkItemTypeOption[] = [
  { id: "task", name: "Task", color: "#3E63DD", is_active: true },
  { id: "bug", name: "Bug", color: "#FF0000", is_active: true },
  { id: "epic", name: "EPIC", color: "#D97706", is_active: true },
  { id: "subtask", name: "Sub-task", color: "#0736F2", is_active: true },
];

describe("WorkItemTypeSelect", () => {
  it("keeps the menu neutral and gives each type its own color when Bug is selected", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <WorkItemTypeSelect options={options} value={options[1]} onChange={vi.fn()} variant="select-ghost-md" />
    );
    const trigger = screen.getByTestId("work-item-type-select");
    expect(container.querySelector("select")).toBeNull();
    expect(trigger.style.backgroundColor).toBe("");
    expect(within(trigger).getByText("Bug").style.backgroundColor).toBe("rgb(255, 0, 0)");
    await user.click(trigger);
    await screen.findByRole("combobox", { name: /search work types/i });
    const menu = screen.getByRole("listbox");
    expect(menu.style.backgroundColor).toBe("");
    for (const type of options) {
      const row = within(menu).getByRole("option", { name: type.name });
      expect(row.style.backgroundColor).toBe("");
      const swatch = row.querySelector<HTMLElement>(`[data-work-type-color="${type.id}"]`);
      const expected = document.createElement("span");
      expected.style.backgroundColor = type.color;
      expect(swatch?.style.backgroundColor).toBe(expected.style.backgroundColor);
    }
    expect(within(menu).getByRole("option", { name: "Bug" }).getAttribute("aria-selected")).toBe("true");
  });

  it("searches and changes the type by ID while updating the selected badge", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    function Picker() {
      const [value, setValue] = useState(options[1]);
      return (
        <WorkItemTypeSelect
          options={options}
          value={value}
          onChange={(id) => {
            onChange(id);
            setValue(options.find((type) => type.id === id)!);
          }}
          variant="select-ghost-md"
        />
      );
    }
    render(<Picker />);
    await user.click(screen.getByTestId("work-item-type-select"));
    await user.type(await screen.findByRole("combobox", { name: /search work types/i }), "EPIC");
    const menu = screen.getByRole("listbox");
    expect(within(menu).queryByRole("option", { name: "Bug" })).toBeNull();
    await user.click(within(menu).getByRole("option", { name: "EPIC" }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith("epic");
    const badge = within(screen.getByTestId("work-item-type-select")).getByText("EPIC");
    expect(badge.style.backgroundColor).toBe("rgb(217, 119, 6)");
  });

  it("prevents edits while disabled", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <WorkItemTypeSelect options={options} value={options[1]} onChange={onChange} variant="select-ghost-md" disabled />
    );
    await user.click(screen.getByTestId("work-item-type-select"));
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });
});
