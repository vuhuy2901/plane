import { observer } from "mobx-react";
import { useSearchParams } from "react-router";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { ProjectAutomationRules } from "@/components/automation/project-rules";
import { automationRulePaths } from "@/components/automation/rule-routing";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
import { AutomationsProjectSettingsHeader } from "./header";

export const AutomationRuleEditorPage = observer(function AutomationRuleEditorPage({
  workspaceSlug,
  projectId,
  ruleId,
}: {
  workspaceSlug: string;
  projectId: string;
  ruleId?: string;
}) {
  const [search] = useSearchParams();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const { currentProjectDetails } = useProject();
  const canEdit = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);
  const title = ruleId ? "Edit automation rule" : "Create automation rule";

  if (workspaceUserInfo && !canEdit) return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;

  return (
    <SettingsContentWrapper
      header={
        <AutomationsProjectSettingsHeader
          listHref={automationRulePaths(workspaceSlug, projectId).list}
          editorLabel={ruleId ? "Edit rule" : "Create rule"}
        />
      }
    >
      <PageHead title={`${currentProjectDetails?.name ? `${currentProjectDetails.name} - ` : ""}${title}`} />
      <SettingsHeading
        title={title}
        description="Configure the source event, conditions, and actions for this project."
      />
      {canEdit && (
        <div className="mt-6">
          <ProjectAutomationRules
            workspaceSlug={workspaceSlug}
            projectId={projectId}
            editor={{
              ruleId,
              preset: search.get("preset") ?? undefined,
              templateId: search.get("template") ?? undefined,
            }}
          />
        </div>
      )}
    </SettingsContentWrapper>
  );
});
