/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { observer } from "mobx-react";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
import { ProjectFeaturesList } from "@/components/project/settings/features-list";
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
import type { Route } from "./+types/page";
import { FeaturesBlockingProjectSettingsHeader } from "./header";

function FeaturesBlockingSettingsPage({ params }: Route.ComponentProps) {
  const { workspaceSlug, projectId } = params;
  const { currentProjectDetails } = useProject();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const canAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);

  if (workspaceUserInfo && !canAdmin) {
    return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;
  }

  return (
    <SettingsContentWrapper header={<FeaturesBlockingProjectSettingsHeader />}>
      <PageHead
        title={
          currentProjectDetails?.name
            ? `${currentProjectDetails.name} settings - Prevent blocked completion`
            : undefined
        }
      />
      <section className="w-full">
        <SettingsHeading
          title="Prevent blocked completion"
          description="Prevent work items with active blockers from moving to a completed state."
        />
        <div className="mt-7">
          <ProjectFeaturesList
            workspaceSlug={workspaceSlug}
            projectId={projectId}
            isAdmin={canAdmin}
            featureKeys={["blocked_completion"]}
          />
        </div>
      </section>
    </SettingsContentWrapper>
  );
}

export default observer(FeaturesBlockingSettingsPage);
