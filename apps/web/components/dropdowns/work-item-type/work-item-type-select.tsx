/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useWorkItemTypes } from "@/hooks/use-work-item-types";
import { useState } from "react";
import { setToast } from "@plane/blocks/toast";
import { WorkItemTypeSelect as WorkItemTypeSelectBlock } from "@plane/blocks/property-select";
import { getWorkflowErrorMessage } from "@/components/workflows/workflow-error";

export type WorkItemTypeSelectProps = {
  workspaceSlug: string;
  projectId: string | null | undefined;
  value: string | null | undefined;
  onChange: (typeId: string | null) => unknown;
  disabled?: boolean;
  variant?: "form" | "sidebar";
};

export function WorkItemTypeSelect({
  workspaceSlug,
  projectId,
  value,
  onChange,
  disabled,
  variant = "form",
}: WorkItemTypeSelectProps) {
  const { data: types = [] } = useWorkItemTypes(workspaceSlug, projectId);
  const selectedType = types.find((type) => type.id === value);
  const [isUpdating, setIsUpdating] = useState(false);
  const changeType = async (typeId: string | null) => {
    if (isUpdating) return;
    setIsUpdating(true);
    try {
      await onChange(typeId);
    } catch (error) {
      setToast({ type: "error", title: "Unable to change work type", message: getWorkflowErrorMessage(error) });
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <WorkItemTypeSelectBlock
      options={types}
      value={selectedType ?? null}
      onChange={(typeId) => void changeType(typeId)}
      variant={variant === "form" ? "pill-sm" : "select-ghost-md"}
      className={variant === "sidebar" ? "w-full" : "max-w-36"}
      disabled={disabled || isUpdating || types.length === 0}
    />
  );
}
