/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane web components
import { observer } from "mobx-react";
// hooks
import { useAnalytics } from "@/hooks/store/use-analytics";
import { useProject } from "@/hooks/store/use-project";
// components
import { ProjectSelect } from "./select/project";
import { CountModeSelect } from "./select/count-mode";
import DurationDropdown from "./select/duration";

const AnalyticsFilterActions = observer(function AnalyticsFilterActions() {
  const {
    countMode,
    selectedDuration,
    selectedProjects,
    updateCountMode,
    updateSelectedDuration,
    updateSelectedProjects,
  } = useAnalytics();
  const { joinedProjectIds } = useProject();
  return (
    <div className="flex items-center justify-end gap-2">
      <ProjectSelect
        value={selectedProjects}
        onChange={(val) => {
          updateSelectedProjects(val ?? []);
        }}
        projectIds={joinedProjectIds}
      />
      <DurationDropdown
        value={selectedDuration}
        onChange={(val) => {
          updateSelectedDuration(val);
        }}
      />
      <CountModeSelect value={countMode} onChange={updateCountMode} />
    </div>
  );
});

export default AnalyticsFilterActions;
