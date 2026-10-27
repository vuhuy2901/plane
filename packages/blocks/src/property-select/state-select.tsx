/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useCallback } from "react";
import type { ReactNode } from "react";
import { ArrowNarrowRightOutline, ChevronRightOutline } from "@makeplane/propel/icons";
import { Workflow as WorkflowIcon } from "lucide-react";
import { cn } from "@plane/utils";
import { StateGroupIcon } from "../icons/state/state-group-icon";
import type { TPaginatedResponse, TStateGroups } from "@plane/types";
import { Select } from "../select/select";
import type { SelectPaginationParams, SelectTooltip, SelectVariant } from "../select/types";
import { ProjectIdentifierElement } from "./shared/project-identifier-element";

/** Minimal state shape the dropdown needs — the client maps its richer record down to this. */
export type StateOption = {
  id: string;
  name: string;
  color: string;
  group: TStateGroups;
  order?: number;
  /** Owning project's short code, shown as a pill when `showIdentifier` is set. */
  identifier?: string;
  /** Unique transition identifier if representing an outgoing workflow transition */
  transitionId?: string;
  /** Target state id when representing an outgoing workflow transition */
  targetStateId?: string;
  /** Human-readable transition name (e.g. "Start Review") */
  transitionName?: string;
  /** Flow direction in the workflow graph ("forward" | "backward") */
  direction?: "forward" | "backward";
};

export type StateSelectProps = {
  /** Paginated fetcher, bound by the client to the state lite service (cursor + optional server search). */
  getValues: (params: SelectPaginationParams) => Promise<TPaginatedResponse<StateOption[]>>;
  /** Selected state as a full object (resolved by the client from `state_id`), or `null` when none. */
  value: StateOption | null;
  /** Emits the next selected state id and optional transition id. */
  onChange: (id: string, transitionId?: string) => void;
  /** Controls trigger chrome, button sizing, and arrow visibility. */
  variant: SelectVariant;
  disabled?: boolean;
  placeholder?: string;
  searchPlaceholder?: string;
  onClose?: () => void;
  className?: string;
  /**
   * When provided, only states whose id is in this set are shown. Pass `null` (or omit) to show all
   * states — used when workflows are disabled or unavailable.
   */
  allowedStateIds?: Set<string> | null;
  /** Shows each option's `identifier` as a pill, for a picker scoped across several projects. */
  showIdentifier?: boolean;
  tooltip?: SelectTooltip;
  appendElement?: ReactNode;
  /** Persistent content displayed below the state options, outside the listbox. */
  footer?: ReactNode;
  /** Forwarded to `Select.Trigger`'s `testId` — see its doc comment (value-agnostic e2e selector). */
  testId?: string;
  /** Tab order of the trigger, for forms that sequence focus explicitly (e.g. the work item create modal). */
  tabIndex?: number;
  /** Custom header to display above options (e.g. Current State header). */
  header?: ReactNode;
  /** When true, renders in workflow transition navigation mode */
  isWorkflowMode?: boolean;
};

/**
 * Presentational, data-source-agnostic state picker built on the generic single-select `Select`.
 * The client supplies `getValues` (bound to the state lite list or workflow transitions), the
 * selected `value` object, and an `onChange` that persists the chosen id — this block owns the
 * state-specific and transition-specific markup.
 */
export function StateSelect(props: StateSelectProps) {
  const {
    getValues,
    value,
    onChange,
    disabled = false,
    placeholder = "",
    searchPlaceholder = "Search states...",
    onClose,
    className,
    allowedStateIds = null,
    showIdentifier = false,
    tooltip,
    appendElement,
    footer,
    testId,
    tabIndex,
    header,
    isWorkflowMode = false,
    variant = "pill-sm",
  } = props;

  const shouldFilterStates = allowedStateIds !== null;
  const optionMap = useRef<Map<string, StateOption>>(new Map());

  const fetchValues = useCallback(
    async (params: SelectPaginationParams): Promise<TPaginatedResponse<StateOption[]>> => {
      const response = await getValues(params);
      for (const opt of response.results) {
        optionMap.current.set(opt.id, opt);
        if (opt.targetStateId) {
          optionMap.current.set(opt.targetStateId, opt);
        }
      }
      return response;
    },
    [getValues]
  );

  const handleSelectChange = useCallback(
    (selectedId: string) => {
      const selectedOption = optionMap.current.get(selectedId);
      const targetId = selectedOption?.targetStateId ?? selectedId;
      const transitionId = selectedOption?.transitionId;
      onChange(targetId, transitionId);
    },
    [onChange]
  );

  const defaultWorkflowHeader = (
    <div className="border-b border-subtle px-3 py-2" data-testid="workflow-current-state-header">
      <div className="flex items-center justify-between text-caption-xs-medium uppercase tracking-wider text-tertiary">
        <span>Current State</span>
        <WorkflowIcon className="size-3.5 text-tertiary" />
      </div>
      {value ? (
        <div className="mt-1.5 flex items-center gap-2">
          <StateGroupIcon
            stateGroup={value.group}
            color={value.color}
            percentage={value.order}
            className="size-4 shrink-0"
          />
          <span className="text-body-xs-medium text-primary truncate font-medium">{value.name}</span>
        </div>
      ) : (
        <div className="mt-1.5 text-body-xs-regular text-tertiary">None</div>
      )}
    </div>
  );

  const resolvedHeader = header !== undefined ? header : isWorkflowMode ? defaultWorkflowHeader : undefined;

  return (
    <Select<StateOption>
      infinite
      getValues={fetchValues}
      value={value}
      onChange={handleSelectChange}
      disabled={disabled}
      placeholder={placeholder}
      searchPlaceholder={searchPlaceholder}
      onClose={onClose}
      header={resolvedHeader}
      footer={footer}
      pinSelected={false}
      getOptionValue={(state) => state.id}
      getOptionLabel={(state) => state.name}
      getOptionDescription={(state) => state.transitionName}
      getOptionSearchText={(state) => `${state.name} ${state.transitionName ?? ""}`}
      filterOption={
        shouldFilterStates
          ? (state) => allowedStateIds.has(state.targetStateId ?? state.id)
          : undefined
      }
      getOptionIcon={(state) => {
        if (isWorkflowMode || state.transitionName !== undefined || state.direction !== undefined) {
          const isForward = state.direction !== "backward";
          return (
            <ArrowNarrowRightOutline
              className={cn(
                "size-4 shrink-0 transition-colors",
                isForward ? "text-emerald-600 dark:text-emerald-500" : "text-tertiary"
              )}
            />
          );
        }
        return (
          <StateGroupIcon
            stateGroup={state.group}
            color={state.color}
            className="size-4 shrink-0"
            percentage={state.order}
          />
        );
      }}
      getOptionTrailing={(state) => {
        if (isWorkflowMode || state.transitionName !== undefined || state.direction !== undefined) {
          return <ChevronRightOutline className="size-4 text-tertiary shrink-0" />;
        }
        return showIdentifier && state.identifier ? (
          <ProjectIdentifierElement show identifier={state.identifier} />
        ) : undefined;
      }}
      getOptionGroup={(state) => {
        if (isWorkflowMode || state.transitionName !== undefined || state.direction !== undefined) {
          return "AVAILABLE TRANSITIONS";
        }
        return undefined;
      }}
    >
      <Select.Trigger<StateOption>
        disabled={disabled}
        variant={variant}
        tabIndex={tabIndex}
        className={className}
        data-testid={testId}
        prependIcon={(states) => (
          <StateGroupIcon
            stateGroup={states[0]?.group ?? "backlog"}
            color={states[0]?.color ?? "currentColor"}
            percentage={states[0]?.order}
            size="md"
          />
        )}
        label={(states) => states[0]?.name ?? placeholder}
        tooltip={tooltip}
      >
        {(states) => {
          const selected = states[0];
          const label = selected?.name ?? placeholder;
          return (
            (!!selected || !!placeholder) && (
              <span className="flex min-w-0 grow items-center gap-2 truncate text-left">
                <span className="truncate">{label}</span>
                {selected?.name && appendElement ? appendElement : undefined}
              </span>
            )
          );
        }}
      </Select.Trigger>
    </Select>
  );
}
