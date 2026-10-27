/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import type { IUserLite, TFilterProperty, TSupportedOperators } from "@plane/types";
import { EQUALITY_OPERATOR, COLLECTION_OPERATOR } from "@plane/types";
// local imports
import type { TCreateFilterConfig, TCreateUserFilterParams } from "../../../rich-filters";
import {
  createFilterConfig,
  createOperatorConfigEntry,
  getMemberMultiSelectConfig,
  getMultiSelectConfig,
} from "../../../rich-filters";

/** Stable non-UUID values used by the API for the assignee quick options. */
export const ALL_ASSIGNEES_FILTER_VALUE = "__all_assignees__";
export const UNASSIGNED_ASSIGNEE_FILTER_VALUE = "__unassigned__";

type TAssigneeFilterOption = {
  id: string;
  label: string;
  value: string;
  member?: IUserLite;
  description?: string;
};

// ------------ Assignee filter ------------

/**
 * Assignee filter specific params
 */
export type TCreateAssigneeFilterParams = TCreateUserFilterParams & {
  currentUserId?: string;
  includeUnassigned?: boolean;
};

const getAssigneeMultiSelectConfig = (
  params: TCreateAssigneeFilterParams,
  singleValueOperator: TSupportedOperators
) => {
  const currentMember = params.members.find((member) => member.id === params.currentUserId);
  const options: TAssigneeFilterOption[] = [
    {
      id: ALL_ASSIGNEES_FILTER_VALUE,
      label: "All assignees",
      value: ALL_ASSIGNEES_FILTER_VALUE,
    },
    ...(params.currentUserId
      ? [
          {
            id: params.currentUserId,
            label: "Assigned to me",
            value: params.currentUserId,
            member: currentMember,
            description: currentMember?.display_name,
          },
        ]
      : []),
    ...params.members
      .filter((member) => member.id !== params.currentUserId)
      .map((member) => ({
        id: member.id,
        label: member.display_name,
        value: member.id,
        member,
      })),
    ...(params.includeUnassigned
      ? [
          {
            id: UNASSIGNED_ASSIGNEE_FILTER_VALUE,
            label: "Unassigned",
            value: UNASSIGNED_ASSIGNEE_FILTER_VALUE,
          },
        ]
      : []),
  ];

  return getMultiSelectConfig<TAssigneeFilterOption, string, TAssigneeFilterOption>(
    {
      items: options,
      getId: (option) => option.id,
      getLabel: (option) => option.label,
      getValue: (option) => option.value,
      getIconData: (option) => option,
      getDescription: (option) => option.description,
    },
    {
      singleValueOperator,
      ...params,
    },
    {
      getOptionIcon: (option) => (option.member ? params.getOptionIcon?.(option.member) : undefined),
    }
  );
};

/**
 * Get the assignee filter config
 * @template K - The filter key
 * @param key - The filter key to use
 * @returns A function that takes parameters and returns the assignee filter config
 */
export const getAssigneeFilterConfig =
  <P extends TFilterProperty>(key: P): TCreateFilterConfig<P, TCreateAssigneeFilterParams> =>
  (params: TCreateAssigneeFilterParams) =>
    createFilterConfig<P>({
      id: key,
      label: "Assignees",
      ...params,
      icon: params.filterIcon,
      supportedOperatorConfigsMap: new Map([
        createOperatorConfigEntry(COLLECTION_OPERATOR.IN, params, (updatedParams) =>
          getAssigneeMultiSelectConfig(updatedParams, EQUALITY_OPERATOR.EXACT)
        ),
      ]),
    });

// ------------ Mention filter ------------

/**
 * Mention filter specific params
 */
export type TCreateMentionFilterParams = TCreateUserFilterParams;

/**
 * Get the mention filter config
 * @template K - The filter key
 * @param key - The filter key to use
 * @returns A function that takes parameters and returns the mention filter config
 */
export const getMentionFilterConfig =
  <P extends TFilterProperty>(key: P): TCreateFilterConfig<P, TCreateMentionFilterParams> =>
  (params: TCreateMentionFilterParams) =>
    createFilterConfig<P>({
      id: key,
      label: "Mentions",
      ...params,
      icon: params.filterIcon,
      supportedOperatorConfigsMap: new Map([
        createOperatorConfigEntry(COLLECTION_OPERATOR.IN, params, (updatedParams) =>
          getMemberMultiSelectConfig(updatedParams, EQUALITY_OPERATOR.EXACT)
        ),
      ]),
    });

// ------------ Created by filter ------------

/**
 * Created by filter specific params
 */
export type TCreateCreatedByFilterParams = TCreateUserFilterParams;

/**
 * Get the created by filter config
 * @template K - The filter key
 * @param key - The filter key to use
 * @returns A function that takes parameters and returns the created by filter config
 */
export const getCreatedByFilterConfig =
  <P extends TFilterProperty>(key: P): TCreateFilterConfig<P, TCreateCreatedByFilterParams> =>
  (params: TCreateCreatedByFilterParams) =>
    createFilterConfig<P>({
      id: key,
      label: "Created by",
      ...params,
      icon: params.filterIcon,
      supportedOperatorConfigsMap: new Map([
        createOperatorConfigEntry(COLLECTION_OPERATOR.IN, params, (updatedParams) =>
          getMemberMultiSelectConfig(updatedParams, EQUALITY_OPERATOR.EXACT)
        ),
      ]),
    });

// ------------ Subscriber filter ------------

/**
 * Subscriber filter specific params
 */
export type TCreateSubscriberFilterParams = TCreateUserFilterParams;

/**
 * Get the subscriber filter config
 * @template K - The filter key
 * @param key - The filter key to use
 * @returns A function that takes parameters and returns the subscriber filter config
 */
export const getSubscriberFilterConfig =
  <P extends TFilterProperty>(key: P): TCreateFilterConfig<P, TCreateSubscriberFilterParams> =>
  (params: TCreateSubscriberFilterParams) =>
    createFilterConfig<P>({
      id: key,
      label: "Subscriber",
      ...params,
      icon: params.filterIcon,
      supportedOperatorConfigsMap: new Map([
        createOperatorConfigEntry(COLLECTION_OPERATOR.IN, params, (updatedParams) =>
          getMemberMultiSelectConfig(updatedParams, EQUALITY_OPERATOR.EXACT)
        ),
      ]),
    });
