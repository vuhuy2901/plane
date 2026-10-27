import { StateOutline } from "@makeplane/propel/icons";
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
import { WorkItemTypeSelect } from "./work-item-type-select";
import type { WorkItemTypeSelectProps } from "./work-item-type-select";

/** The same basic entity property in full-page, peek and mobile detail views. */
export function WorkItemTypeProperty(props: Omit<WorkItemTypeSelectProps, "variant">) {
  return (
    <SidebarPropertyListItem icon={StateOutline} label="Work type">
      <WorkItemTypeSelect {...props} variant="sidebar" />
    </SidebarPropertyListItem>
  );
}
