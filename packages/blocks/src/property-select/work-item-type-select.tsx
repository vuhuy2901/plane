/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Select } from "../select/select";
import type { SelectVariant } from "../select/types";

export type WorkItemTypeOption = { id: string; name: string; color: string; is_active: boolean };

export function workTypeColors(value: string | null | undefined) {
  const backgroundColor = value && /^#[0-9a-f]{6}$/i.test(value) ? value : "#64748B";
  const rgb = [1, 3, 5].map((index) => {
    const channel = Number.parseInt(backgroundColor.slice(index, index + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  const luminance = rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  return { backgroundColor, color: luminance > 0.179 ? "#000000" : "#FFFFFF" };
}

type Props = {
  options: WorkItemTypeOption[];
  value: WorkItemTypeOption | null;
  onChange: (id: string) => void;
  disabled?: boolean;
  variant: SelectVariant;
  className?: string;
};

/** Keep menu chrome neutral; type colors belong to swatches and the selected badge only. */
export function WorkItemTypeSelect({ options, value, onChange, disabled, variant, className }: Props) {
  return (
    <Select<WorkItemTypeOption>
      getValues={() => options}
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder="Unassigned type"
      searchPlaceholder="Search work types..."
      pinSelected={false}
      getOptionValue={(type) => type.id}
      getOptionLabel={(type) => `${type.name}${type.is_active ? "" : " (inactive)"}`}
      getOptionDisabled={(type) => !type.is_active && type.id !== value?.id}
      getOptionIcon={(type) => (
        <span
          aria-hidden="true"
          className="size-3 shrink-0 rounded-sm border border-subtle"
          style={{ backgroundColor: workTypeColors(type.color).backgroundColor }}
          data-work-type-color={type.id}
        />
      )}
    >
      <Select.Trigger<WorkItemTypeOption> variant={variant} className={className} data-testid="work-item-type-select">
        {(selected) =>
          selected[0] ? (
            <span
              className="max-w-36 truncate rounded px-1.5 py-0.5 text-[11px] font-medium"
              style={workTypeColors(selected[0].color)}
            >
              {selected[0].name}
            </span>
          ) : (
            <span className="truncate text-placeholder">Unassigned type</span>
          )
        }
      </Select.Trigger>
    </Select>
  );
}
