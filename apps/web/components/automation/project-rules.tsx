import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { Button } from "@makeplane/propel/components/button";
import { useTranslation } from "@plane/i18n";
import { AutomationService } from "@/services/automation.service";
import type {
  AutomationAction,
  AutomationCondition,
  AutomationDefinition,
  AutomationHistory,
  AutomationResource,
  AutomationResources,
  AutomationRule,
  AutomationTemplate,
  TriggerOptions,
} from "@/services/automation.service";
import { changeConditionField, changeConditionOperator, persistRuleDraft } from "./rule-form";
import { EvaluationDetails, RuleDryRun, RuleSummary } from "./rule-feedback";
import { automationRulePaths, loadAutomationEditor } from "./rule-routing";
import type { AutomationEditorOptions } from "./rule-routing";
import {
  automationError,
  historyCreatedWorkItemIds,
  historyTriggerMismatch,
  sourceTransitionHint,
} from "./rule-presentation";

const triggers: Record<string, string> = {
  created: "Work Item Created",
  updated: "Work Item Updated",
  state_changed: "State Changed",
  assignee_changed: "Assignee Changed",
  priority_changed: "Priority Changed",
  comment_added: "Comment Added",
  work_item_linked: "Work Item Linked",
  scheduled: "Scheduled",
};
const actions: Record<string, string> = {
  assign_user: "Assign User",
  change_state: "Change State",
  change_priority: "Change Priority",
  manage_labels: "Manage Labels",
  add_comment: "Add Comment",
  set_due_date: "Set Due Date",
  create_work_item: "Create Work Item",
};
const fields: Record<string, string> = {
  work_item_type: "Work Item Type",
  state: "State",
  priority: "Priority",
  assignee: "Assignee",
  label: "Label",
  due_date: "Due Date",
  ALL_SUBTASKS_COMPLETED: "All Subtasks Completed",
};
const operatorNames: Record<string, string> = {
  equals: "Is",
  not_equals: "Is Not",
  contains: "Contains",
  does_not_contain: "Does Not Contain",
  is_empty: "Is Empty",
  is_not_empty: "Is Not Empty",
  overdue: "Overdue",
  within_next_days: "Within Next N Days",
  is_true: "Is True",
};
const defaults: Record<string, string[]> = {
  work_item_type: ["equals", "not_equals", "is_empty", "is_not_empty"],
  state: ["equals", "not_equals", "is_empty", "is_not_empty"],
  priority: ["equals", "not_equals"],
  assignee: ["equals", "not_equals", "contains", "does_not_contain", "is_empty", "is_not_empty"],
  label: ["contains", "does_not_contain", "is_empty", "is_not_empty"],
  due_date: ["overdue", "within_next_days", "equals", "not_equals", "is_empty", "is_not_empty"],
  ALL_SUBTASKS_COMPLETED: ["is_true"],
};
const priorityOptions = ["none", "low", "medium", "high", "urgent"].map((id) => ({
  id,
  name: id[0].toUpperCase() + id.slice(1),
}));
const mapOptions = (items: Record<string, string>) => Object.entries(items).map(([id, name]) => ({ id, name }));
const resourceField = (field: string) => ["work_item_type", "state", "assignee", "label"].includes(field);
const input = "w-full rounded border border-subtle bg-surface-1 px-3 py-2 text-sm";

function Select({
  label,
  value,
  options,
  onChange,
  optional = false,
  availability,
}: {
  label: string;
  value?: string;
  options: AutomationResource[];
  onChange: (value: string) => void;
  optional?: boolean;
  availability?: "loading" | "error" | "ready";
}) {
  const missing = Boolean(value && !options.some((option) => option.id === value));
  return (
    <label className="text-sm block space-y-1">
      <span>{label}</span>
      <select
        className={input}
        aria-label={label}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
        disabled={availability === "loading" || availability === "error"}
      >
        <option value="">
          {availability === "loading"
            ? "Loading values..."
            : availability === "error"
              ? "Failed to load values"
              : options.length === 0
                ? "No available values"
                : optional
                  ? "Any"
                  : `Select ${label}`}
        </option>
        {missing && <option value={value}>Unavailable selection ({value})</option>}
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
    </label>
  );
}
function Text({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value?: string | number;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label className="text-sm block space-y-1">
      <span>{label}</span>
      <input
        className={input}
        aria-label={label}
        type={type}
        min={0}
        max={3650}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

export function ProjectAutomationRules({
  workspaceSlug: w,
  projectId: p,
  editor,
}: {
  workspaceSlug: string;
  projectId: string;
  editor?: AutomationEditorOptions;
}) {
  return (
    <ProjectAutomationRulesForProject
      key={`${w}:${p}:${editor?.ruleId ?? (editor ? "new" : "list")}:${editor?.preset ?? ""}:${editor?.templateId ?? ""}`}
      workspaceSlug={w}
      projectId={p}
      editor={editor}
    />
  );
}

function ProjectAutomationRulesForProject({
  workspaceSlug: w,
  projectId: p,
  editor,
}: {
  workspaceSlug: string;
  projectId: string;
  editor?: AutomationEditorOptions;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const paths = automationRulePaths(w, p);
  const isEditor = editor !== undefined;
  const { ruleId, preset, templateId } = editor ?? {};
  const draftInitialized = useRef(false);
  const [editorStatus, setEditorStatus] = useState<"loading" | "error" | "ready">("loading");
  const [editorAttempt, setEditorAttempt] = useState(0);
  const navigationNotice = location.state as { automationNotice?: string; automationNoticeIsError?: boolean } | null;
  const { t } = useTranslation();
  // This module intentionally uses English, independently of the rest of Plane.
  const tr = (key: string, fallback: string) =>
    t(`automations.project_rules.${key}`, { lng: "en", defaultValue: fallback });
  const service = useMemo(() => new AutomationService(), []);
  const [tab, setTab] = useState("rules");
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [templates, setTemplates] = useState<AutomationTemplate[]>([]);
  const [resources, setResources] = useState<AutomationResources>({
    members: [],
    types: [],
    states: [],
    labels: [],
    work_items: [],
  });
  const [resourcesStatus, setResourcesStatus] = useState<"loading" | "error" | "ready">("loading");
  const [resourcesError, setResourcesError] = useState("");
  const [history, setHistory] = useState<AutomationHistory[]>([]);
  const [page, setPage] = useState(0);
  const [status, setStatus] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [draft, setDraft] = useState<AutomationDefinition | null>(null);
  const [editing, setEditing] = useState<AutomationRule>();
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [message, setMessage] = useState(
    typeof navigationNotice?.automationNotice === "string" ? navigationNotice.automationNotice : ""
  );
  const [messageIsError, setMessageIsError] = useState(navigationNotice?.automationNoticeIsError === true);
  const [rulesStatus, setRulesStatus] = useState<"loading" | "error" | "ready">("loading");
  const [historyStatus, setHistoryStatus] = useState<"loading" | "error" | "ready">("loading");
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [preview, setPreview] = useState<string | null>(null);
  const failure = useCallback((error: unknown) => {
    setMessageIsError(true);
    setMessage(automationError(error));
  }, []);
  const refresh = async () => {
    try {
      setRules(await service.rules(w, p));
      setRulesStatus("ready");
    } catch (error) {
      setRulesStatus("error");
      throw error;
    }
  };
  const upsertRule = (saved: AutomationRule) =>
    setRules((current) =>
      current.some((rule) => rule.id === saved.id)
        ? current.map((rule) => (rule.id === saved.id ? saved : rule))
        : [saved, ...current]
    );
  const loadResources = useCallback(async () => {
    setResourcesStatus("loading");
    setResourcesError("");
    try {
      const result = await service.resources(w, p);
      if (
        !result ||
        !["types", "states", "members", "labels", "work_items"].every((key) =>
          Array.isArray(result[key as keyof AutomationResources])
        )
      ) {
        throw new Error("The project resources response is invalid.");
      }
      setResources(result);
      setResourcesStatus("ready");
    } catch (error) {
      setResourcesStatus("error");
      setResourcesError(error instanceof Error ? error.message : "Failed to load project resources.");
    }
  }, [service, w, p]);
  useEffect(() => {
    if (isEditor) return;
    let cancelled = false;
    void service
      .rules(w, p)
      .then((result) => {
        if (!cancelled) {
          setRules(result);
          setRulesStatus("ready");
        }
        return undefined;
      })
      .catch((error) => {
        if (!cancelled) {
          setRulesStatus("error");
          failure(error);
        }
      });
    void service
      .templates(w, p)
      .then((result) => {
        if (!cancelled) setTemplates(result);
        return undefined;
      })
      .catch((error) => {
        if (!cancelled) failure(error);
      });
    return () => {
      cancelled = true;
    };
  }, [service, w, p, failure, isEditor]);
  useEffect(() => {
    void loadResources();
  }, [loadResources]);
  useEffect(() => {
    if (!isEditor || draftInitialized.current || resourcesStatus !== "ready") return;
    let cancelled = false;
    const initialize = async () => {
      setEditorStatus("loading");
      setMessage("");
      setMessageIsError(false);
      try {
        const { draft: definition, rule: saved } = await loadAutomationEditor(
          { ruleId, preset, templateId },
          resources,
          service,
          w,
          p
        );
        if (!cancelled) {
          draftInitialized.current = true;
          setDraft(definition);
          setEditing(saved);
          setEditorStatus("ready");
        }
      } catch (error) {
        if (!cancelled) {
          setEditorStatus("error");
          failure(error);
        }
      }
    };
    void initialize();
    return () => {
      cancelled = true;
    };
  }, [isEditor, ruleId, preset, templateId, resourcesStatus, resources, service, w, p, failure, editorAttempt]);
  useEffect(() => {
    if (isEditor || tab !== "history") return;
    let cancelled = false;
    setHistoryStatus("loading");
    setHistory([]);
    setHasMore(false);
    void service
      .history(w, p, page, status)
      .then((result) => {
        if (!cancelled) {
          setHistory(result.results);
          setHasMore(result.has_more);
          setHistoryStatus("ready");
        }
        return undefined;
      })
      .catch((error) => {
        if (!cancelled) {
          setHistoryStatus("error");
          failure(error);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tab, page, status, service, w, p, failure, historyRefresh, isEditor]);
  const run = async (fn: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setMessage("");
    setMessageIsError(false);
    try {
      await fn();
    } catch (error) {
      failure(error);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };
  const saveDraft = (enable: boolean) =>
    void run(async () => {
      if (!draft || resourcesStatus !== "ready") return;
      const result = await persistRuleDraft({
        draft,
        resources,
        service,
        workspace: w,
        project: p,
        rule: editing,
        enable,
      });
      const enableFailed = "enableError" in result;
      navigate(paths.list, {
        replace: true,
        state: {
          automationNotice: enableFailed
            ? `Rule saved, but it remains disabled. Enable failed: ${automationError(result.enableError)} Retry Enable on the saved rule below.`
            : enable
              ? "Rule saved and enabled. It will run on future matching source events."
              : "Rule saved and disabled. Run a dry-run, then Enable when ready.",
          automationNoticeIsError: enableFailed,
        },
      });
    });
  const button = (label: string, onClick: () => void, disabled = false, primary = false) => (
    <Button
      stretch="auto"
      size="sm"
      variant={primary ? "primary" : "secondary"}
      label={label}
      onClick={onClick}
      disabled={busy || disabled}
    />
  );
  const choices = (field: string) =>
    field === "work_item_type"
      ? resources.types
      : field === "state"
        ? [
            ...resources.states,
            ...["backlog", "unstarted", "started", "completed", "cancelled"].map((group) => ({
              id: `group:${group}`,
              name: `${group[0].toUpperCase()}${group.slice(1)} State Group`,
            })),
          ]
        : field === "priority"
          ? priorityOptions
          : field === "label"
            ? resources.labels
            : resources.members;
  const operators = resources.catalog?.operators ?? defaults;
  const setOptions = (patch: Partial<TriggerOptions>) => {
    if (!draft) return;
    const options = { ...draft.trigger_options, ...patch };
    Object.keys(options).forEach((key) => {
      if (options[key as keyof TriggerOptions] === "") delete options[key as keyof TriggerOptions];
    });
    setDraft({ ...draft, trigger_options: options });
  };
  const patchAction = (index: number, action: AutomationAction) => {
    if (draft) setDraft({ ...draft, actions: draft.actions.map((item, i) => (i === index ? action : item)) });
  };
  const conditionEditor = (
    conditions: AutomationCondition[],
    onChange: (value: AutomationCondition[]) => void,
    scheduled = false
  ) => (
    <div className="space-y-3">
      {conditions.map((condition, index) => {
        const patch = (value: AutomationCondition) =>
          onChange(conditions.map((item, i) => (i === index ? value : item)));
        return (
          <div key={index} className="grid gap-3 rounded border border-subtle p-3 md:grid-cols-3">
            <Select
              label="Condition"
              value={condition.field}
              options={mapOptions(fields).filter((item) => !scheduled || item.id !== "ALL_SUBTASKS_COMPLETED")}
              onChange={(field) => patch(changeConditionField(field, { ...defaults, ...operators }))}
            />
            <Select
              label="Operator"
              value={condition.operator}
              options={(operators[condition.field] ?? defaults[condition.field] ?? []).map((id) => ({
                id,
                name: operatorNames[id] ?? id,
              }))}
              onChange={(operator) => patch(changeConditionOperator(condition, operator))}
            />
            {!["is_empty", "is_not_empty", "overdue", "is_true"].includes(condition.operator) &&
              (condition.field === "due_date" ? (
                <Text
                  label={condition.operator === "within_next_days" ? "Number of Days" : "Due Date"}
                  type={condition.operator === "within_next_days" ? "number" : "date"}
                  value={condition.value}
                  onChange={(value) => patch({ ...condition, value })}
                />
              ) : (
                <Select
                  label="Value"
                  value={condition.value}
                  options={choices(condition.field)}
                  availability={resourceField(condition.field) ? resourcesStatus : "ready"}
                  onChange={(value) => patch({ ...condition, value })}
                />
              ))}
            {button("Remove Condition", () => onChange(conditions.filter((_, i) => i !== index)))}
          </div>
        );
      })}
      {button(
        "Add Condition",
        () => onChange([...conditions, { field: "priority", operator: "equals" }]),
        conditions.length >= (resources.limits?.conditions ?? 3)
      )}
    </div>
  );
  const filteredTemplates = templates.filter(
    (item) =>
      `${item.name} ${item.description ?? ""}`.toLowerCase().includes(query.toLowerCase()) &&
      (!category || item.category === category)
  );
  const options = draft?.trigger_options ?? {};
  return (
    <section className={isEditor ? "space-y-4" : "mt-8 border-t border-subtle pt-6"} lang="en">
      {isEditor ? (
        <Link to={paths.list} className="text-sm text-accent underline-offset-4 hover:underline">
          Back to Automations
        </Link>
      ) : (
        <h2 className="text-lg font-semibold">{tr("title", "Automations")}</h2>
      )}
      <p className="text-sm my-2 text-secondary">
        Choose the source event in When, filter source work items in If, and choose what happens in Then.
      </p>
      {resourcesStatus === "loading" && <p role="status">Loading project resources...</p>}
      {resourcesStatus === "error" && (
        <div role="alert" className="my-3 rounded border border-subtle p-3">
          <p>Failed to load project resources. {resourcesError}</p>
          {button("Retry loading values", () => void loadResources())}
        </div>
      )}
      {resourcesStatus === "ready" &&
        ["types", "states", "members", "labels"].map((key) =>
          resources[key as "types" | "states" | "members" | "labels"].length === 0 ? (
            <p key={key} role="status">
              No available {key} in this project.
            </p>
          ) : null
        )}
      {!isEditor && (
        <nav className="my-4 flex gap-2" aria-label="Automation tabs">
          {[
            ["templates", "Templates"],
            ["rules", "My Rules"],
            ["history", "History"],
          ].map(([id, name]) => (
            <Button
              key={id}
              stretch="auto"
              size="sm"
              variant={tab === id ? "primary" : "secondary"}
              label={name}
              disabled={busy}
              onClick={() => setTab(id)}
            />
          ))}
        </nav>
      )}
      {message && (!draft || !messageIsError) && (
        <div
          role={messageIsError ? "alert" : "status"}
          className={`text-sm my-3 rounded border border-subtle p-3 break-words ${messageIsError ? "text-danger-primary" : ""}`}
        >
          {message}
        </div>
      )}
      {isEditor && editorStatus === "loading" && resourcesStatus !== "error" && (
        <p role="status">Loading rule editor...</p>
      )}
      {isEditor &&
        editorStatus === "error" &&
        button("Retry loading rule", () => setEditorAttempt((attempt) => attempt + 1))}
      {!isEditor && tab === "templates" && (
        <>
          <div className="mb-4 grid gap-3 md:grid-cols-2">
            <Text label="Search Templates" value={query} onChange={setQuery} />
            <Select
              label="Category"
              optional
              value={category}
              onChange={setCategory}
              options={Array.from(new Set(templates.map((item) => item.category))).map((id) => ({ id, name: id }))}
            />
          </div>
          {!filteredTemplates.length && <p>{tr("no_templates", "No templates match your search.")}</p>}
          <div className="grid gap-4 md:grid-cols-2">
            {filteredTemplates.map((template) => (
              <article key={template.id} className="rounded border border-subtle p-4">
                <h3 className="font-medium">{template.name}</h3>
                <p className="text-sm my-2 text-secondary">{template.description}</p>
                {preview === template.id && (
                  <div className="text-sm my-3 space-y-2">
                    <RuleSummary definition={template} resources={resources} />
                    <p>Select the project&apos;s actual resources before saving.</p>
                  </div>
                )}
                <div className="flex gap-2">
                  {button("Preview Template", () => setPreview(preview === template.id ? null : template.id))}
                  {button("Use Template", () => navigate(paths.template(template.id)), Boolean(draft))}
                </div>
              </article>
            ))}
          </div>
        </>
      )}
      {(isEditor || tab === "rules") && (
        <>
          {!isEditor && (
            <div className="flex flex-wrap gap-2">
              {button("Create rule", () => navigate(paths.create), false, true)}
              {button("Create Bug starter", () => navigate(paths.bug), Boolean(draft) || resourcesStatus !== "ready")}
            </div>
          )}
          {draft && (
            <fieldset disabled={busy} className="my-4 space-y-6 border-0 p-0">
              <legend className="sr-only">{editing ? "Edit Rule" : "Create Rule"}</legend>
              <p className="text-sm text-warning-primary">
                Unsaved draft.{" "}
                {editing?.enabled
                  ? "The saved rule is still enabled with its previous configuration until you save."
                  : "This draft will not run until saved and enabled."}
              </p>
              <Text label="Rule Name" value={draft.name} onChange={(name) => setDraft({ ...draft, name })} />
              <details className="rounded border border-subtle bg-surface-1 p-3" open>
                <summary className="text-sm cursor-pointer font-medium">Draft preview</summary>
                <RuleSummary definition={draft} resources={resources} />
              </details>
              <div className="space-y-3 border-l-2 border-subtle pl-4">
                <h3 className="font-semibold">When · Source event</h3>
                <p className="text-sm text-secondary">
                  This event happens to the source work item. To create a Bug when a Task moves back from testing,
                  choose State Changed here, select From and To states, and add Task as the source type in If.
                </p>
                <Select
                  label="Source event"
                  value={draft.trigger}
                  options={mapOptions(triggers)}
                  onChange={(trigger) =>
                    setDraft({
                      ...draft,
                      trigger,
                      trigger_options:
                        trigger === "scheduled"
                          ? { frequency: "daily", time: "09:00", timezone: resources.timezone ?? "UTC", filters: [] }
                          : {},
                    })
                  }
                />
                {draft.trigger === "created" && (
                  <Select
                    label="Source work item type"
                    optional
                    options={resources.types}
                    availability={resourcesStatus}
                    value={options.type_id}
                    onChange={(type_id) => setOptions({ type_id })}
                  />
                )}
                {draft.trigger === "updated" && (
                  <Select
                    label="Updated Field"
                    optional
                    options={(resources.catalog?.update_fields ?? []).map((id) => ({
                      id,
                      name:
                        (
                          {
                            target_date: "Due Date",
                            name: "Title",
                            description_html: "Description",
                            work_item_type: "Work Item Type",
                            parent_id: "Parent Work Item",
                          } as Record<string, string>
                        )[id] ?? id.replaceAll("_", " "),
                    }))}
                    value={options.field}
                    onChange={(field) => setOptions({ field })}
                  />
                )}
                {draft.trigger === "state_changed" && (
                  <>
                    <div className="grid gap-3 md:grid-cols-2">
                      <Select
                        label="Source state before change"
                        optional
                        options={resources.states}
                        value={options.from_state}
                        onChange={(from_state) => setOptions({ from_state })}
                      />
                      <Select
                        label="Source state after change"
                        optional
                        options={[...resources.states, { id: "group:completed", name: "Completed State Group" }]}
                        value={options.to_group ? `group:${options.to_group}` : options.to_state}
                        onChange={(value) =>
                          setOptions(
                            value === "group:completed"
                              ? { to_group: "completed", to_state: "", enter_group_only: true }
                              : { to_state: value, to_group: "", enter_group_only: false }
                          )
                        }
                      />
                    </div>
                    {options.subtask_only && (
                      <p className="text-sm text-secondary">Only Subtasks entering the Completed State Group.</p>
                    )}
                    {sourceTransitionHint(draft, resources) && (
                      <p className={`text-sm ${options.enter_group_only ? "text-warning-primary" : "text-secondary"}`}>
                        {sourceTransitionHint(draft, resources)}
                      </p>
                    )}
                    {options.enter_group_only && (
                      <div className="text-sm space-y-2 text-warning-primary">
                        <p>
                          This saved configuration requires entering a different state group. A transition between
                          states in the same group does not qualify.
                        </p>
                        {button("Allow transitions within this group", () => setOptions({ enter_group_only: false }))}
                      </div>
                    )}
                  </>
                )}
                {draft.trigger === "priority_changed" && (
                  <div className="grid gap-3 md:grid-cols-2">
                    <Select
                      label="From Priority"
                      optional
                      options={priorityOptions}
                      value={options.from_priority}
                      onChange={(from_priority) => setOptions({ from_priority })}
                    />
                    <Select
                      label="To Priority"
                      optional
                      options={priorityOptions}
                      value={options.to_priority}
                      onChange={(to_priority) => setOptions({ to_priority })}
                    />
                  </div>
                )}
                {draft.trigger === "assignee_changed" && (
                  <div className="grid gap-3 md:grid-cols-2">
                    <Select
                      label="Previous Assignee"
                      optional
                      options={[{ id: "unassigned", name: "Unassigned" }, ...resources.members]}
                      value={options.previous_assignee}
                      onChange={(previous_assignee) => setOptions({ previous_assignee })}
                    />
                    <Select
                      label="New Assignee"
                      optional
                      options={[{ id: "unassigned", name: "Unassigned" }, ...resources.members]}
                      value={options.new_assignee}
                      onChange={(new_assignee) => setOptions({ new_assignee })}
                    />
                  </div>
                )}
                {draft.trigger === "comment_added" && (
                  <Select
                    label="Comment Author"
                    optional
                    options={resources.members}
                    value={options.author_id}
                    onChange={(author_id) => setOptions({ author_id })}
                  />
                )}
                {draft.trigger === "work_item_linked" && (
                  <>
                    <Select
                      label="Relation Type"
                      optional
                      options={(resources.catalog?.relations ?? []).map((id) => ({
                        id,
                        name: id === "blocking" ? "Blocks" : id.replaceAll("_", " "),
                      }))}
                      value={options.relation_type}
                      onChange={(relation_type) => setOptions({ relation_type })}
                    />
                    <Select
                      label="Source Work Item"
                      optional
                      options={resources.work_items}
                      value={options.source_id}
                      onChange={(source_id) => setOptions({ source_id })}
                    />
                    <Select
                      label="Target Work Item"
                      optional
                      options={resources.work_items}
                      value={options.target_id}
                      onChange={(target_id) => setOptions({ target_id })}
                    />
                  </>
                )}
                {draft.trigger === "scheduled" && (
                  <>
                    <Select
                      label="Frequency"
                      options={[
                        { id: "daily", name: "Daily" },
                        { id: "weekly", name: "Weekly" },
                      ]}
                      value={options.frequency}
                      onChange={(frequency) =>
                        setOptions({ frequency, weekday: frequency === "weekly" ? 0 : undefined })
                      }
                    />
                    <Text
                      label="Execution Time"
                      type="time"
                      value={options.time}
                      onChange={(time) => setOptions({ time })}
                    />
                    <Text
                      label="Time Zone"
                      value={options.timezone}
                      onChange={(timezone) => setOptions({ timezone })}
                    />
                    {options.frequency === "weekly" && (
                      <Select
                        label="Day of Week"
                        options={["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map(
                          (name, i) => ({ id: String(i), name })
                        )}
                        value={String(options.weekday ?? 0)}
                        onChange={(weekday) => setOptions({ weekday: Number(weekday) })}
                      />
                    )}
                    <h4>Work Item Filters</h4>
                    {conditionEditor(options.filters ?? [], (filters) => setOptions({ filters }), true)}
                    <p className="text-sm text-secondary">
                      One run per local calendar occurrence. Rules start with the next scheduled time after Enable.
                    </p>
                  </>
                )}
              </div>
              <div className="space-y-3 border-l-2 border-subtle pl-4">
                <h3 className="font-semibold">If · Source work item conditions</h3>
                <p className="text-sm text-secondary">
                  All conditions must match (AND). These filter the source work item, including its type. With no
                  conditions, any source work item can match.
                </p>
                {conditionEditor(draft.conditions, (conditions) => setDraft({ ...draft, conditions }))}
              </div>
              <div className="space-y-3 border-l-2 border-subtle pl-4">
                <h3 className="font-semibold">Then · Actions</h3>
                <p className="text-sm text-secondary">
                  Actions run in order after When and If match. To create a Bug, select Create Work Item and choose Bug
                  as the new item type.
                </p>
                {draft.actions.map((action, index) => (
                  <div key={index} className="space-y-3 rounded border border-subtle p-4">
                    <Select
                      label="Action"
                      options={mapOptions(actions)}
                      value={action.type}
                      onChange={(type) =>
                        patchAction(
                          index,
                          type === "assign_user"
                            ? { type, mode: "specific_member", only_if_unassigned: true }
                            : type === "set_due_date"
                              ? { type, mode: "relative", days: 3, timezone: resources.timezone ?? "UTC" }
                              : type === "manage_labels"
                                ? { type, operation: "add" }
                                : { type }
                        )
                      }
                    />
                    {action.type === "assign_user" && (
                      <>
                        <Select
                          label="Assignment Mode"
                          options={[
                            { id: "specific_member", name: "Specific Member" },
                            { id: "project_lead", name: "Project Lead" },
                            { id: "creator", name: "Work Item Creator" },
                          ]}
                          value={action.mode}
                          onChange={(mode) => patchAction(index, { ...action, mode, member_id: undefined })}
                        />
                        {action.mode === "specific_member" && (
                          <Select
                            label="Assignee"
                            options={resources.members}
                            value={action.member_id}
                            onChange={(member_id) => patchAction(index, { ...action, member_id })}
                          />
                        )}
                        <label className="text-sm block">
                          <input
                            type="checkbox"
                            checked={action.only_if_unassigned ?? true}
                            onChange={(e) => patchAction(index, { ...action, only_if_unassigned: e.target.checked })}
                          />{" "}
                          Only If Unassigned
                        </label>
                        {!action.only_if_unassigned && (
                          <label className="text-sm block">
                            <input
                              type="checkbox"
                              checked={action.replace_assignees ?? false}
                              onChange={(e) => patchAction(index, { ...action, replace_assignees: e.target.checked })}
                            />{" "}
                            Replace Assignees (otherwise preserve existing Assignees)
                          </label>
                        )}
                      </>
                    )}
                    {action.type === "change_state" && (
                      <>
                        <Select
                          label="Target"
                          options={[
                            { id: "current", name: "Current Work Item" },
                            { id: "parent", name: "Parent Work Item" },
                          ]}
                          value={action.target ?? "current"}
                          onChange={(target) =>
                            patchAction(index, { ...action, target: target as "current" | "parent" })
                          }
                        />
                        <Select
                          label="Destination State"
                          options={resources.states}
                          value={action.state_id}
                          onChange={(state_id) => patchAction(index, { ...action, state_id })}
                        />
                        <p className="text-sm text-secondary">
                          The transition must be allowed by the target Work Item&apos;s workflow. Parent targets require
                          All Subtasks Completed.
                        </p>
                      </>
                    )}
                    {action.type === "change_priority" && (
                      <Select
                        label="Priority"
                        options={priorityOptions}
                        value={action.priority}
                        onChange={(priority) => patchAction(index, { ...action, priority })}
                      />
                    )}
                    {action.type === "manage_labels" && (
                      <>
                        <Select
                          label="Operation"
                          options={[
                            { id: "add", name: "Add Label" },
                            { id: "remove", name: "Remove Label" },
                          ]}
                          value={action.operation}
                          onChange={(operation) =>
                            patchAction(index, { ...action, operation: operation as "add" | "remove" })
                          }
                        />
                        <Select
                          label="Label"
                          options={resources.labels}
                          value={action.label_id}
                          onChange={(label_id) => patchAction(index, { ...action, label_id })}
                        />
                      </>
                    )}
                    {action.type === "add_comment" && (
                      <>
                        <label className="text-sm block">
                          Comment
                          <textarea
                            aria-label="Comment"
                            className={input}
                            value={action.text ?? ""}
                            onChange={(e) => patchAction(index, { ...action, text: e.target.value })}
                          />
                        </label>
                        <p className="text-xs text-secondary">
                          Placeholders:{" "}
                          {"{work_item_identifier}, {work_item_title}, {previous_state}, {new_state}, {actor_name}"}
                        </p>
                      </>
                    )}
                    {action.type === "set_due_date" && (
                      <>
                        <Select
                          label="Date Mode"
                          options={[
                            { id: "relative", name: "N Days After Trigger" },
                            { id: "fixed", name: "Fixed Date" },
                          ]}
                          value={action.mode ?? "relative"}
                          onChange={(mode) =>
                            patchAction(index, {
                              type: action.type,
                              mode,
                              ...(mode === "relative" ? { days: 3, timezone: resources.timezone ?? "UTC" } : {}),
                            })
                          }
                        />
                        {action.mode === "fixed" ? (
                          <Text
                            label="Due Date"
                            type="date"
                            value={action.date}
                            onChange={(date) => patchAction(index, { ...action, date })}
                          />
                        ) : (
                          <>
                            <Text
                              label="Number of Days"
                              type="number"
                              value={action.days}
                              onChange={(days) => patchAction(index, { ...action, days: Number(days) })}
                            />
                            <Text
                              label="Time Zone"
                              value={action.timezone ?? resources.timezone}
                              onChange={(timezone) => patchAction(index, { ...action, timezone })}
                            />
                            <p className="text-sm text-secondary">
                              Calendar days after the trigger&apos;s local date, including weekends.
                            </p>
                          </>
                        )}
                      </>
                    )}
                    {action.type === "create_work_item" && (
                      <>
                        <Select
                          label="New work item type (created target)"
                          options={resources.types}
                          availability={resourcesStatus}
                          value={action.type_id}
                          onChange={(type_id) => {
                            patchAction(index, {
                              ...action,
                              type_id,
                              state_id: undefined,
                            });
                          }}
                        />
                        <p className="text-sm text-secondary">
                          This is the type of the new item to create. It does not filter the source work item. The
                          source type belongs in When or If.
                        </p>
                        <label className="text-sm block space-y-1">
                          <span>Placement</span>
                          <select
                            className={input}
                            aria-label="Placement"
                            value={action.parent_mode ?? "none"}
                            onChange={(event) =>
                              patchAction(index, {
                                ...action,
                                parent_mode: event.target.value === "source" ? "source" : "none",
                              })
                            }
                          >
                            <option value="none">Top-level work item</option>
                            <option value="source">Child of source work item</option>
                          </select>
                        </label>
                        <p className="text-sm text-secondary">
                          Child placement nests the new item directly under the source work item. A Bug keeps its Bug
                          type: Epic → Task → Bug. The optional relation is separate from placement.
                        </p>
                        <Text
                          label="Title"
                          value={action.title}
                          onChange={(title) => patchAction(index, { ...action, title })}
                        />
                        <Text
                          label="Description"
                          value={action.description}
                          onChange={(description) => patchAction(index, { ...action, description })}
                        />
                        <Select
                          label="Priority"
                          options={priorityOptions}
                          value={action.priority}
                          onChange={(priority) => patchAction(index, { ...action, priority })}
                        />
                        <Select
                          label="Assignee (optional)"
                          options={resources.members}
                          value={action.member_id}
                          onChange={(member_id) => patchAction(index, { ...action, member_id: member_id || undefined })}
                        />
                        <Select
                          label="Created Work Item Relation to Triggering Work Item (optional)"
                          options={(resources.catalog?.relations ?? []).map((id) => ({
                            id,
                            name:
                              id === "blocking"
                                ? "Created Work Item BLOCKS Triggering Work Item"
                                : id.replaceAll("_", " "),
                          }))}
                          value={action.relation}
                          onChange={(relation) => patchAction(index, { ...action, relation: relation || undefined })}
                        />
                      </>
                    )}
                    {button(
                      "Remove Action",
                      () => setDraft({ ...draft, actions: draft.actions.filter((_, i) => i !== index) }),
                      draft.actions.length <= 1
                    )}
                  </div>
                ))}
                {button(
                  "Add Action",
                  () => setDraft({ ...draft, actions: [...draft.actions, { type: "add_comment", text: "" }] }),
                  draft.actions.length >= (resources.limits?.actions ?? 2)
                )}
              </div>
              <div className="sticky bottom-0 z-10 space-y-3 border-t border-subtle bg-surface-1 py-4">
                {message && messageIsError && (
                  <div role="alert" className="text-sm text-danger-primary">
                    {message}
                  </div>
                )}
                <p className="text-sm font-medium">
                  Unsaved draft{editing ? ` · editing saved revision ${editing.revision}` : " · new rule"}
                </p>
                <p className="text-sm text-secondary">
                  Changes take effect only after saving. Save disabled to check a dry-run first, or save and enable for
                  future matching events.
                </p>
                {resourcesStatus !== "ready" && (
                  <p className="text-sm text-warning-primary">
                    {resourcesStatus === "loading"
                      ? "Loading project resources before saving..."
                      : "Saving unavailable. Retry loading project resources above."}
                  </p>
                )}
                <div className="flex flex-wrap gap-2">
                  {button(
                    busy ? "Saving..." : "Save and enable",
                    () => saveDraft(true),
                    resourcesStatus !== "ready",
                    true
                  )}
                  {button("Save disabled", () => saveDraft(false), resourcesStatus !== "ready")}
                  {button("Cancel draft", () => {
                    navigate(paths.list);
                  })}
                </div>
              </div>
            </fieldset>
          )}
          {!isEditor && (
            <div className="my-4 space-y-3">
              {rulesStatus === "loading" && <p role="status">Loading saved rules...</p>}
              {rulesStatus === "error" && (
                <div role="alert">
                  <p>Could not refresh saved rules. Displayed rules may be out of date.</p>
                  {button("Retry loading rules", () => void run(refresh))}
                </div>
              )}
              {rulesStatus === "ready" && !rules.length && <p>{tr("no_rules", "No automation rules found.")}</p>}
              {rules.map((rule) => (
                <article key={rule.id} className="rounded border border-subtle p-4">
                  <div className="flex justify-between gap-3">
                    <h3 className="font-medium">{rule.name}</h3>
                    <span className="text-sm">
                      {rule.enabled ? "Enabled" : "Disabled"} · {rule.execution_count ?? 0} executions
                    </span>
                  </div>
                  <p className="text-xs mt-2 text-secondary">Saved configuration · Revision {rule.revision}</p>
                  <RuleSummary definition={rule} resources={resources} />
                  <div className="flex flex-wrap gap-2">
                    {button("Edit Rule", () => navigate(paths.edit(rule.id)), Boolean(draft))}
                    {button(
                      rule.enabled ? "Disable" : "Enable",
                      () =>
                        void run(async () => {
                          upsertRule(await service.setEnabled(w, p, rule.id, !rule.enabled));
                          setMessage(
                            rule.enabled
                              ? tr("disabled", "Automation rule disabled.")
                              : tr("enabled", "Automation rule enabled.")
                          );
                        }),
                      Boolean(draft)
                    )}
                    {button(
                      "Duplicate Rule",
                      () =>
                        void run(async () => {
                          upsertRule(await service.duplicate(w, p, rule.id));
                          setMessage("Rule duplicated and Disabled.");
                        }),
                      Boolean(draft)
                    )}
                    {button(
                      "Delete Rule",
                      () => {
                        if (window.confirm(`Delete rule "${rule.name}"? Execution History will be retained.`))
                          void run(async () => {
                            await service.remove(w, p, rule.id);
                            setRules((current) => current.filter((item) => item.id !== rule.id));
                            setMessage("Automation rule deleted.");
                          });
                      },
                      Boolean(draft)
                    )}
                  </div>
                  <RuleDryRun
                    key={`${rule.id}:${rule.revision}`}
                    service={service}
                    workspace={w}
                    project={p}
                    rule={rule}
                    resources={resources}
                    resourcesReady={resourcesStatus === "ready"}
                    hasDraft={Boolean(draft)}
                  />
                </article>
              ))}
            </div>
          )}
        </>
      )}
      {!isEditor && tab === "history" && (
        <>
          <div className="mb-4 flex items-end gap-3">
            <Select
              label="Execution Status"
              optional
              options={[
                { id: "success", name: "Success" },
                { id: "failed", name: "Failed" },
                { id: "skipped", name: "Skipped" },
              ]}
              value={status}
              onChange={(value) => {
                setStatus(value);
                setPage(0);
              }}
            />
            {button("Refresh history", () => setHistoryRefresh((value) => value + 1), historyStatus === "loading")}
          </div>
          {historyStatus === "loading" && <p role="status">Loading execution history...</p>}
          {historyStatus === "error" && <p role="alert">Could not load execution history. Refresh history to retry.</p>}
          {historyStatus === "ready" && !history.length && <p>No execution history found.</p>}
          {history.map((row) => (
            <article key={row.id} className="mb-3 rounded border border-subtle p-4">
              <div className="flex justify-between">
                <strong>{row.snapshot.definition.name ?? "Deleted rule"}</strong>
                <span>{row.status[0].toUpperCase() + row.status.slice(1)}</span>
              </div>
              <a
                className="text-accent text-sm my-2 block"
                href={`/${w}/projects/${p}/issues/${row.snapshot.work_item.id}`}
              >
                #{row.snapshot.work_item.sequence_id} {row.snapshot.work_item.name}
              </a>
              <time className="text-xs text-secondary">{new Date(row.created_at).toLocaleString("en-US")}</time>
              <p
                className={`text-sm my-2 ${row.status === "skipped" && historyTriggerMismatch(row) ? "text-warning-primary" : ""}`}
              >
                {row.status === "skipped" ? historyTriggerMismatch(row) || row.detail : row.detail}
              </p>
              {row.snapshot.parent_id && (
                <a className="text-sm text-accent block" href={`/${w}/projects/${p}/issues/${row.snapshot.parent_id}`}>
                  Parent Work Item
                </a>
              )}
              {historyCreatedWorkItemIds(row).map((createdIssueId) => (
                <a
                  key={createdIssueId}
                  className="text-sm text-accent block"
                  href={`/${w}/projects/${p}/issues/${createdIssueId}`}
                >
                  Created Work Item
                </a>
              ))}
              <details className="text-sm mt-3" open={row.status === "skipped" || row.status === "failed"}>
                <summary className="cursor-pointer font-medium">
                  Why this run{" "}
                  {row.status === "skipped" ? "was skipped" : row.status === "failed" ? "failed" : "matched"}
                </summary>
                <div className="mt-3 space-y-3">
                  {row.snapshot.evaluation ? (
                    <EvaluationDetails
                      evaluation={row.snapshot.evaluation}
                      resources={resources}
                      definition={row.snapshot.definition}
                    />
                  ) : (
                    <>
                      <p className="text-secondary">
                        This older run did not record detailed condition checks. Historical values cannot be
                        reconstructed from the work item&apos;s current values.
                      </p>
                    </>
                  )}
                  <p className="font-medium">Saved configuration at execution time</p>
                  <RuleSummary definition={row.snapshot.definition} resources={resources} />
                </div>
              </details>
            </article>
          ))}
          <div className="flex items-center gap-3">
            {button("Previous", () => setPage(page - 1), page === 0 || historyStatus === "loading")}
            <span>{page + 1}</span>
            {button("Next", () => setPage(page + 1), !hasMore || historyStatus === "loading")}
          </div>
        </>
      )}
    </section>
  );
}
