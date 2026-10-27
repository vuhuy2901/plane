/* oxlint-disable react/no-array-index-key -- These read-only snapshots have no item IDs or row state. */
import { useState } from "react";
import { Button } from "@makeplane/propel/components/button";
import type {
  AutomationDefinition,
  AutomationEvaluation,
  AutomationResources,
  AutomationRule,
  AutomationService,
  AutomationTestResult,
} from "@/services/automation.service";
import {
  actionSummary,
  automationError,
  checkExplanation,
  conditionSummary,
  displayValue,
  dryRunSummary,
  triggerSummary,
} from "./rule-presentation";

export function RuleSummary({
  definition,
  resources,
}: {
  definition: AutomationDefinition;
  resources: AutomationResources;
}) {
  return (
    <dl className="text-sm my-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 break-words">
      <dt className="font-medium">When</dt>
      <dd>{triggerSummary(definition, resources)}</dd>
      <dt className="font-medium">If</dt>
      <dd>
        {definition.conditions.map((condition) => conditionSummary(condition, resources)).join(" AND ") ||
          "Any source work item (no conditions)"}
      </dd>
      <dt className="font-medium">Then</dt>
      <dd className="space-y-1">
        {definition.actions.map((action, index) => (
          <p key={index}>
            {index + 1}. {actionSummary(action, resources)}
          </p>
        ))}
      </dd>
    </dl>
  );
}

export function EvaluationDetails({
  evaluation,
  resources,
  definition,
}: {
  evaluation: AutomationEvaluation;
  resources: AutomationResources;
  definition?: AutomationDefinition;
}) {
  return (
    <div className="text-sm space-y-3">
      <div>
        <p className="font-medium">When: {evaluation.trigger.matched ? "Matched" : "Not matched"}</p>
        {evaluation.trigger.expected && (
          <p>Expected source event: {displayValue("trigger", evaluation.trigger.expected, resources)}</p>
        )}
        {evaluation.trigger.actual && (
          <p>Evaluated source events: {displayValue("trigger", evaluation.trigger.actual, resources)}</p>
        )}
        {!evaluation.trigger.matched && (
          <p className="text-warning-primary">
            Review the source event and trigger filters in When. Changing the type in Then only changes the item to
            create.
          </p>
        )}
        <ul className="mt-1 space-y-2">
          {evaluation.trigger.checks.map((check, index) => (
            <li key={index} className={check.matched ? "text-secondary" : "text-warning-primary"}>
              {checkExplanation(check, resources)}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="font-medium">If: all conditions must match</p>
        {evaluation.conditions.length ? (
          <ul className="mt-1 space-y-2">
            {evaluation.conditions.map((check, index) => (
              <li key={index} className={check.matched ? "text-secondary" : "text-warning-primary"}>
                {checkExplanation(check, resources)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-secondary">
            {definition?.conditions.length === 0
              ? "No conditions configured."
              : !evaluation.trigger.matched
                ? "Conditions not evaluated because the source event did not match."
                : "No condition checks recorded."}
          </p>
        )}
      </div>
    </div>
  );
}

export function RuleDryRun({
  service,
  workspace,
  project,
  rule,
  resources,
  resourcesReady,
  hasDraft,
}: {
  service: AutomationService;
  workspace: string;
  project: string;
  rule: AutomationRule;
  resources: AutomationResources;
  resourcesReady: boolean;
  hasDraft: boolean;
}) {
  const [issueId, setIssueId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AutomationTestResult>();
  const test = async () => {
    setBusy(true);
    setError("");
    setResult(undefined);
    try {
      setResult(await service.test(workspace, project, rule.id, issueId));
    } catch (testError) {
      setError(automationError(testError));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mt-4 space-y-3 border-t border-subtle pt-3">
      <p className="text-sm font-medium">Test saved rule · Dry-run</p>
      <p className="text-sm text-secondary">
        Checks the latest recorded source event when available. Actions are prepared, never executed. With no recorded
        event, the server uses a creation simulation or the current snapshot and explains the limits.
      </p>
      {hasDraft && (
        <p className="text-sm text-warning-primary">Save or cancel your open draft before testing a saved rule.</p>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm min-w-0 space-y-1">
          <span className="block">Source work item (200 most recent)</span>
          <select
            aria-label={`Source work item for ${rule.name}`}
            className="w-full rounded border border-subtle bg-surface-1 px-3 py-2"
            value={issueId}
            disabled={busy || !resourcesReady || hasDraft}
            onChange={(event) => {
              setIssueId(event.target.value);
              setResult(undefined);
              setError("");
            }}
          >
            <option value="">
              {resourcesReady
                ? resources.work_items.length
                  ? "Select a source work item"
                  : "No work items available"
                : "Project resources unavailable"}
            </option>
            {resources.work_items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <Button
          stretch="auto"
          size="sm"
          variant="secondary"
          label={busy ? "Checking latest event..." : "Check latest event (dry-run)"}
          disabled={busy || !issueId || !resourcesReady || hasDraft}
          onClick={() => void test()}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger-primary">
          Dry-run failed. {error}
        </p>
      )}
      {result && (
        <div role="status" className="text-sm space-y-3 rounded border border-subtle p-3">
          <p className="font-medium">{dryRunSummary(result)}</p>
          <p>
            {result.preview_mode === "recorded_event"
              ? "Preview source: latest recorded event for this work item."
              : result.preview_mode === "simulated_created"
                ? "Preview source: simulated creation using current values. No recorded event was available."
                : result.preview_mode === "current_snapshot"
                  ? "Preview source: current values only. No recorded event was available; a state transition or other change cannot be inferred."
                  : "Preview source: not reported by this server. A real source event was not verified."}
          </p>
          {result.reason && <p>{result.reason}</p>}
          {result.evaluation ? (
            <EvaluationDetails evaluation={result.evaluation} resources={resources} definition={rule} />
          ) : (
            <p className="text-secondary">Detailed trigger and condition checks are unavailable from this server.</p>
          )}
          <p className="font-medium">Configured actions (not executed)</p>
          <ul className="space-y-1">
            {rule.actions.map((action, index) => (
              <li key={index}>{actionSummary(action, resources)}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
