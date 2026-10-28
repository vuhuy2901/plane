/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
import { observer } from "mobx-react";
// plane package imports
import { useTranslation } from "@plane/i18n";
import { Loader } from "@plane/blocks/skeleton";
// plane web hooks
import { useAnalytics } from "@/hooks/store/use-analytics";
import { useWorkspaceReport } from "@/components/analytics/report";
// plane web components
import AnalyticsSectionWrapper from "../analytics-section-wrapper";
import ActiveProjectItem from "./active-project-item";

const ActiveProjects = observer(function ActiveProjects() {
  const { t } = useTranslation();
  const { selectedDurationLabel } = useAnalytics();
  const { data: report, isLoading } = useWorkspaceReport();
  return (
    <AnalyticsSectionWrapper
      title={`${t("workspace_analytics.active_projects")}`}
      subtitle={selectedDurationLabel}
      className="md:col-span-2"
    >
      <div className="flex h-[350px] flex-col gap-4 overflow-auto">
        {isLoading &&
          ["one", "two", "three", "four", "five"].map((loaderId) => (
            <Loader.Item key={`active-project-loader-${loaderId}`} height="40px" width="100%" />
          ))}
        {!isLoading &&
          report?.projects.map((project) => (
            <ActiveProjectItem
              key={project.id}
              project={{ id: project.id, completed_issues: project.completed, total_issues: project.total }}
            />
          ))}
      </div>
    </AnalyticsSectionWrapper>
  );
});

export default ActiveProjects;
