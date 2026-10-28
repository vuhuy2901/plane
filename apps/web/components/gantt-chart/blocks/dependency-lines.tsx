import { observer } from "mobx-react";
import type { TIssue } from "@plane/types";
import { useTimeLineChartStore } from "@/hooks/use-timeline-chart";
import { BLOCK_HEIGHT } from "../constants";

type Props = {
  blockIds: string[];
};

export const GanttDependencyLines = observer(function GanttDependencyLines({ blockIds }: Props) {
  const { getBlockById } = useTimeLineChartStore();
  const visibleIds = new Set(blockIds);
  const lines = blockIds.flatMap((blockedId, blockedIndex) => {
    const blocked = getBlockById(blockedId);
    const blockedIssue = blocked?.data as TIssue | undefined;
    if (!blocked?.position || !blockedIssue) return [];
    const blockedPosition = blocked.position;

    return (blockedIssue.issue_relation ?? []).flatMap((relation) => {
      if (relation.relation_type !== "blocked_by" || !visibleIds.has(relation.id)) return [];
      const blocker = getBlockById(relation.id);
      const blockerIndex = blockIds.indexOf(relation.id);
      if (!blocker?.position || blockerIndex < 0) return [];
      const blockerIssue = blocker.data as TIssue | undefined;
      const startX = blocker.position.marginLeft + blocker.position.width;
      const endX = blockedPosition.marginLeft;
      const startY = blockerIndex * BLOCK_HEIGHT + BLOCK_HEIGHT / 2;
      const endY = blockedIndex * BLOCK_HEIGHT + BLOCK_HEIGHT / 2;
      const bendX = startX + Math.max(18, (endX - startX) / 2);
      const completed = (blockerIssue?.state__group ?? relation.state_group) === "completed";
      return [
        {
          id: `${relation.id}-${blockedId}`,
          path: `M ${startX} ${startY} H ${bendX} V ${endY} H ${endX}`,
          completed,
          label: `${relation.name} blocks ${blockedIssue.name}. ${completed ? "Blocker completed" : "Actively blocked"}.`,
        },
      ];
    });
  });

  if (!lines.length) return null;

  return (
    <svg
      aria-label="Work item dependencies"
      className="pointer-events-none absolute top-0 left-0 z-[4] overflow-visible"
      width="100%"
      height={blockIds.length * BLOCK_HEIGHT}
    >
      <defs>
        <marker id="dependency-arrow-active" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
          <path d="M0,0 L7,3.5 L0,7 z" className="fill-danger-primary" />
        </marker>
        <marker id="dependency-arrow-complete" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
          <path d="M0,0 L7,3.5 L0,7 z" className="fill-secondary" />
        </marker>
      </defs>
      {lines.map((line) => (
        <path
          key={line.id}
          d={line.path}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeDasharray={line.completed ? "4 4" : undefined}
          markerEnd={`url(#dependency-arrow-${line.completed ? "complete" : "active"})`}
          className={line.completed ? "text-secondary" : "text-danger-primary"}
          style={{ pointerEvents: "stroke" }}
        >
          <title>{line.label}</title>
        </path>
      ))}
    </svg>
  );
});
