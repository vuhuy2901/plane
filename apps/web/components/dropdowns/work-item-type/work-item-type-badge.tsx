import { useParams } from "next/navigation";
import { useWorkItemTypes } from "@/hooks/use-work-item-types";
import { workTypeColors } from "./work-item-type-color";

export function WorkItemTypeBadge({
  projectId,
  typeId,
}: {
  projectId: string | null | undefined;
  typeId: string | null | undefined;
}) {
  const { workspaceSlug } = useParams();
  const { data: types, error } = useWorkItemTypes(typeId ? workspaceSlug?.toString() : undefined, projectId);
  const type = types?.find((item) => item.id === typeId);
  const name = !typeId
    ? "Unassigned type"
    : (type?.name ?? (error ? "Type unavailable" : types ? "Unknown type" : "Loading type…"));
  return (
    <span
      className="max-w-32 shrink-0 truncate rounded px-1.5 py-0.5 text-[11px] font-medium"
      style={workTypeColors(type?.color)}
      title={`Work type: ${name}`}
    >
      {name}
    </span>
  );
}
