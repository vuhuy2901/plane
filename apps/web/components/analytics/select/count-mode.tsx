/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import type { TAnalyticsCountMode } from "@plane/types";
import { Select } from "@plane/blocks/select";

type CountModeOption = {
  value: TAnalyticsCountMode;
  label: string;
};

const COUNT_MODE_OPTIONS: CountModeOption[] = [
  { value: "all", label: "All work items" },
  { value: "top_level", label: "Top-level only" },
];

type Props = {
  value: TAnalyticsCountMode;
  onChange: (value: TAnalyticsCountMode) => void;
};

export function CountModeSelect({ value, onChange }: Props) {
  const selectedOption = COUNT_MODE_OPTIONS.find((option) => option.value === value) ?? COUNT_MODE_OPTIONS[0];

  return (
    <Select<CountModeOption>
      getValues={() => COUNT_MODE_OPTIONS}
      value={selectedOption}
      onChange={(nextValue) => {
        const option = COUNT_MODE_OPTIONS.find((item) => item.value === nextValue);
        if (option) onChange(option.value);
      }}
      getOptionValue={(option) => option.value}
      getOptionLabel={(option) => option.label}
      pinSelected={false}
    >
      <Select.Trigger<CountModeOption> variant="select-md">
        {(selected) => <span className="truncate">{selected[0]?.label ?? "All work items"}</span>}
      </Select.Trigger>
    </Select>
  );
}
