import { useState } from "react";
import { Link } from "react-router";
import { Avatar } from "@makeplane/propel/components/avatar";
import type { IWorkspaceReport } from "@plane/types";
import { getFileURL } from "@plane/utils";

type Group = IWorkspaceReport["estimates"]["leaderboard"][number];
type Member = Group["members"][number];

const displayName = (member: Member) =>
  member.assignee__display_name ||
  [member.assignee__first_name, member.assignee__last_name].filter(Boolean).join(" ") ||
  "Unassigned";

export function MemberAvatar({ member }: { member: Member }) {
  return (
    <Avatar
      alt={displayName(member)}
      fallback={displayName(member)[0]?.toUpperCase()}
      src={member.assignee__avatar ? getFileURL(member.assignee__avatar) : undefined}
      size="sm"
    />
  );
}

export function StoryPointsLeaderboard({ data, slug }: { data: IWorkspaceReport; slug: string }) {
  const groups = data.estimates.leaderboard ?? [];
  const [selectedKey, setSelectedKey] = useState("");
  const [selectedMember, setSelectedMember] = useState<string | null>(null);
  const group = groups.find((item) => item.key === selectedKey) ?? groups[0];
  if (!group)
    return (
      <p className="text-sm text-secondary">
        Leaderboard data is unavailable. Reload the Analytics API and refresh this report.
      </p>
    );

  const members = group.members;
  const leaders = members.filter((member) => member.rank !== null && member.rank <= 3);
  const maximum = Math.max(0, ...members.map((member) => member.completed_points));
  const active = members.find((member) => (member.assignee_id ?? "unassigned") === selectedMember);

  return (
    <div className="space-y-5">
      {groups.length > 1 && (
        <label className="text-sm text-secondary">
          Estimate scale:{" "}
          <select
            className="ml-2 rounded border border-subtle bg-surface-1 px-2 py-1 text-primary"
            value={group.key}
            onChange={(event) => {
              setSelectedKey(event.target.value);
              setSelectedMember(null);
            }}
          >
            {groups.map((item) => (
              <option key={item.key} value={item.key}>
                {item.projects.join(", ")} ({item.scale.join(", ")} SP)
              </option>
            ))}
          </select>
        </label>
      )}
      <p className="text-xs text-secondary">
        Completed from {data.meta.date_from} to {data.meta.date_to}. Assigned SP covers current work in this estimate
        scale. Points are split equally across current assignees; this is workload, not employee performance.
      </p>
      {leaders.length ? (
        <div className="grid gap-3 md:grid-cols-3">
          {leaders.map((member) => (
            <button
              key={member.assignee_id}
              type="button"
              onClick={() => setSelectedMember(member.assignee_id)}
              className="rounded-md border border-subtle bg-surface-1 p-4 text-left hover:bg-layer-1"
            >
              <div className="flex items-center gap-2 text-primary">
                <span aria-label={`Rank ${member.rank}`}>{["🥇", "🥈", "🥉"][(member.rank ?? 1) - 1]}</span>
                <MemberAvatar member={member} />
                <span className="truncate font-medium">{displayName(member)}</span>
              </div>
              <p className="text-xl mt-3 font-semibold text-primary tabular-nums">{member.completed_points} SP</p>
              <p className="text-xs text-secondary">
                {member.completed_items} completed items ·{" "}
                {member.completion_rate === null ? "—" : `${member.completion_rate}%`} completion
              </p>
            </button>
          ))}
        </div>
      ) : (
        <p className="text-sm rounded-md border border-subtle p-4 text-secondary">
          No member has completed estimated work in this period.
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="text-sm w-full min-w-[850px] text-left">
          <thead className="text-xs border-b border-subtle text-secondary">
            <tr>
              <th className="pb-3 font-medium">Rank</th>
              <th className="pb-3 font-medium">Member</th>
              <th className="pb-3 text-right font-medium">Assigned SP</th>
              <th className="pb-3 text-right font-medium">Completed SP</th>
              <th className="pb-3 text-right font-medium">Remaining SP</th>
              <th className="pb-3 text-right font-medium">Completion Rate</th>
              <th className="pb-3 text-right font-medium">Completed Items</th>
            </tr>
          </thead>
          <tbody>
            {members.map((member) => (
              <tr key={member.assignee_id ?? "unassigned"} className="border-b border-subtle last:border-0">
                <td className="py-3 text-secondary">{member.rank ?? "—"}</td>
                <td className="py-3">
                  <button
                    type="button"
                    className="flex items-center gap-2 font-medium text-primary hover:underline"
                    onClick={() => setSelectedMember(member.assignee_id ?? "unassigned")}
                  >
                    <MemberAvatar member={member} /> {displayName(member)}
                  </button>
                </td>
                <td className="py-3 text-right tabular-nums">{member.assigned_points}</td>
                <td className="py-3 text-right tabular-nums">{member.completed_points}</td>
                <td className="py-3 text-right tabular-nums">{member.remaining_points}</td>
                <td className="py-3 text-right tabular-nums">
                  {member.completion_rate === null ? "—" : `${member.completion_rate}%`}
                </td>
                <td className="py-3 text-right tabular-nums">{member.completed_items}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>
        <h4 className="text-sm mb-3 font-medium text-primary">Completed SP by Member</h4>
        {members
          .filter((member) => member.completed_points > 0)
          .map((member) => (
            <div key={member.assignee_id} className="text-xs mb-2 flex items-center gap-3 text-secondary">
              <span className="w-32 truncate">{displayName(member)}</span>
              <span className="h-2 flex-1 rounded-full bg-layer-1">
                <span
                  className="bg-green-500 block h-full rounded-full"
                  style={{ width: `${(member.completed_points / maximum) * 100}%` }}
                />
              </span>
              <span className="w-16 text-right tabular-nums">{member.completed_points} SP</span>
            </div>
          ))}
      </div>
      {active && (
        <div className="rounded-md border border-subtle p-4">
          <div className="mb-3 flex items-center justify-between">
            <h4 className="text-sm font-medium text-primary">Completed work items · {displayName(active)}</h4>
            <button
              type="button"
              className="text-xs text-secondary hover:underline"
              onClick={() => setSelectedMember(null)}
            >
              Close
            </button>
          </div>
          {active.work_items.length ? (
            <ul className="text-sm space-y-2">
              {active.work_items.map((item) => (
                <li key={item.id}>
                  <Link
                    className="text-primary hover:underline"
                    to={`/${slug}/projects/${item.project_id}/issues/${item.id}`}
                  >
                    {item.identifier} · {item.name}
                  </Link>
                  <span className="ml-2 text-secondary">{item.allocated_points} SP</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-secondary">No completed estimated work items in this period.</p>
          )}
        </div>
      )}
    </div>
  );
}
