import { observer } from "mobx-react";
import { Breadcrumbs } from "@plane/blocks/breadcrumb";
import { PROJECT_SETTINGS } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
import { SettingsPageHeader } from "@/components/settings/page-header";
import { PROJECT_SETTINGS_ICONS } from "@/components/settings/project/sidebar/item-icon";

export const WorkflowsProjectSettingsHeader = observer(function WorkflowsProjectSettingsHeader() {
  const { t } = useTranslation();
  const settings = PROJECT_SETTINGS.workflows;
  const Icon = PROJECT_SETTINGS_ICONS.workflows;
  return (
    <SettingsPageHeader
      leftItem={
        <Breadcrumbs>
          <Breadcrumbs.Item
            component={
              <BreadcrumbLink label={t(settings.i18n_label)} icon={<Icon className="size-4 text-tertiary" />} />
            }
          />
        </Breadcrumbs>
      }
    />
  );
});
