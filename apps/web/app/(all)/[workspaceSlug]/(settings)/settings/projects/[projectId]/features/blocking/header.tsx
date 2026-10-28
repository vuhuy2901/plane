/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { observer } from "mobx-react";
import { Breadcrumbs } from "@plane/blocks/breadcrumb";
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
import { SettingsPageHeader } from "@/components/settings/page-header";
import { PROJECT_SETTINGS } from "@plane/constants";
import { PROJECT_SETTINGS_ICONS } from "@/components/settings/project/sidebar/item-icon";

export const FeaturesBlockingProjectSettingsHeader = observer(function FeaturesBlockingProjectSettingsHeader() {
  const settingsDetails = PROJECT_SETTINGS.features_blocking;
  const Icon = PROJECT_SETTINGS_ICONS.features_blocking;

  return (
    <SettingsPageHeader
      leftItem={
        <Breadcrumbs>
          <Breadcrumbs.Item
            component={
              <BreadcrumbLink label={settingsDetails.i18n_label} icon={<Icon className="size-4 text-tertiary" />} />
            }
          />
        </Breadcrumbs>
      }
    />
  );
});
