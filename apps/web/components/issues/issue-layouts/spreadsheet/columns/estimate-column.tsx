/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// types
import type { TIssue } from "@plane/types";
// components
import { EstimateSelect } from "@/components/dropdowns/estimate/estimate-select";
import { displayedEstimate, usesHierarchicalEstimate } from "@/store/issue/helpers/hierarchical-estimate";

type Props = {
  issue: TIssue;
  onClose: () => void;
  onChange: (issue: TIssue, data: Partial<TIssue>, updates: any) => void;
  disabled: boolean;
};

export const SpreadsheetEstimateColumn = observer(function SpreadsheetEstimateColumn(props: Props) {
  const { issue, onChange, disabled, onClose } = props;

  return (
    <div className="h-11 border-b-[0.5px] border-subtle">
      {usesHierarchicalEstimate(issue) ? (
        <div className="flex h-full items-center px-3 text-13 font-medium text-secondary">
          {displayedEstimate(issue)} pts
        </div>
      ) : (
        <EstimateSelect
          value={issue.estimate_point || undefined}
          onChange={(data) =>
            onChange(issue, { estimate_point: data }, { changed_property: "estimate_point", change_details: data })
          }
          placeholder="Estimate"
          projectId={issue.project_id ?? undefined}
          disabled={disabled}
          onClose={onClose}
          // `.clickable` is what the table's keyboard navigation clicks on Enter / Space in a focused cell.
          className="clickable"
          variant="table-cell"
        />
      )}
    </div>
  );
});
