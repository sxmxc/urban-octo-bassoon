import type { Endpoint, RouteDeployment, RouteImplementation } from "../types/endpoints";

export type RouteLiveRequestMode = "disabled" | "legacy_mock" | "live_active" | "live_disabled";

export interface RouteTestState {
  hasRuntimeHistory: boolean;
  hasSavedImplementation: boolean;
  currentDraftBadgeColor: string;
  currentDraftBadgeLabel: string;
  draftHeadline: string;
  draftSummary: string;
  executionsEmptyState: string;
  liveHeadline: string;
  liveMode: RouteLiveRequestMode;
  liveStatusColor: string;
  liveStatusLabel: string;
  liveSummary: string;
  previewHeadline: string;
  previewSummary: string;
}

export function buildRouteTestState(
  endpoint: Pick<Endpoint, "enabled">,
  currentImplementation: Pick<RouteImplementation, "id" | "is_draft" | "version"> | null | undefined,
  deployments: Array<Pick<RouteDeployment, "environment" | "implementation_id" | "is_active">>,
): RouteTestState {
  const activeDeployment = deployments.find((deployment) => deployment.is_active) ?? null;
  const hasDeploymentHistory = deployments.length > 0;
  const hasSavedImplementation = currentImplementation?.id !== null && currentImplementation?.id !== undefined;
  const hasRuntimeHistory = hasSavedImplementation || hasDeploymentHistory;

  let liveMode: RouteLiveRequestMode;
  let liveStatusLabel: string;
  let liveStatusColor: string;
  let liveHeadline: string;
  let liveSummary: string;
  let executionsEmptyState: string;

  if (!endpoint.enabled) {
    liveMode = "disabled";
    liveStatusLabel = "Disabled";
    liveStatusColor = "error";
    liveHeadline = activeDeployment ? "Route disabled over live config" : "Route disabled";
    liveSummary = activeDeployment
      ? `A ${activeDeployment.environment} deployment exists, but disabled routes still return 404 until the route is re-enabled.`
      : hasRuntimeHistory
        ? "This route has saved runtime history, but the route definition is disabled, so live/public requests return 404."
        : "This route is disabled, so live/public requests return 404 until you re-enable it.";
    executionsEmptyState = "This route is disabled, so live/public requests currently return 404. Contract previews remain available.";
  } else if (activeDeployment) {
    liveMode = "live_active";
    liveStatusLabel = "Published live";
    liveStatusColor = "accent";
    liveHeadline = `Implementation ${activeDeployment.implementation_id} is live`;
    liveSummary = `Live/public requests execute the active ${activeDeployment.environment} deployment and can create execution traces below.`;
    executionsEmptyState = `No live executions yet. Send a public request from the route tester or another client to create the first ${activeDeployment.environment} trace.`;
  } else if (hasRuntimeHistory) {
    liveMode = "live_disabled";
    liveStatusLabel = "Not live";
    liveStatusColor = "warning";
    liveHeadline = hasDeploymentHistory ? "No active deployment" : "Draft only";
    liveSummary = hasDeploymentHistory
      ? "This route has entered the live-runtime path, but no deployment is currently active. Live/public requests return 404 until you publish again."
      : "This route has a saved flow draft but no active deployment. Live/public requests return 404 until you publish a flow implementation.";
    executionsEmptyState = "No live executions yet because this route does not currently have an active deployment.";
  } else {
    liveMode = "legacy_mock";
    liveStatusLabel = "Legacy mock";
    liveStatusColor = "secondary";
    liveHeadline = "Schema-driven public mock";
    liveSummary = "This route has not entered the live-runtime lifecycle yet. Live/public requests still use the schema-driven legacy mock path.";
    executionsEmptyState = "Legacy mock requests do not create live execution traces. Publish a flow implementation to start collecting runtime history.";
  }

  let currentDraftBadgeColor = "secondary";
  let currentDraftBadgeLabel = "Scaffold only";
  let draftHeadline = "No saved flow draft yet";
  let draftSummary =
    "The Flow tab is still showing the default scaffold for this route. Save the flow before treating it as a real runtime draft.";

  if (hasSavedImplementation && currentImplementation) {
    if (currentImplementation.is_draft === false) {
      currentDraftBadgeColor = "accent";
      currentDraftBadgeLabel = "Published base";
      if (activeDeployment && activeDeployment.implementation_id === currentImplementation.id) {
        draftHeadline = "Published base matches live";
        draftSummary = `The latest saved implementation is already serving the active ${activeDeployment.environment} deployment.`;
      } else if (hasDeploymentHistory) {
        draftHeadline = "Published base saved";
        draftSummary = "The latest saved implementation is not an editable draft, but no deployment is currently active.";
      } else {
        draftHeadline = "Published base saved";
        draftSummary = "The latest saved implementation is no longer marked as an editable draft.";
      }
    } else {
      currentDraftBadgeColor = "warning";
      currentDraftBadgeLabel = "Draft";
      if (activeDeployment) {
        draftHeadline = `Draft v${currentImplementation.version} is ahead of live`;
        draftSummary = `The latest saved draft is not deployed. Live/public requests still use implementation ${activeDeployment.implementation_id} until you publish again.`;
      } else if (hasDeploymentHistory) {
        draftHeadline = `Draft v${currentImplementation.version} is saved`;
        draftSummary = "The latest saved draft is editable, but live traffic is disabled until a deployment is published again.";
      } else {
        draftHeadline = `Draft v${currentImplementation.version} is saved`;
        draftSummary =
          "The latest saved draft is editable, but live/public requests still return 404 until you publish a deployment.";
      }
    }
  }

  return {
    hasRuntimeHistory,
    hasSavedImplementation,
    currentDraftBadgeColor,
    currentDraftBadgeLabel,
    draftHeadline,
    draftSummary,
    executionsEmptyState,
    liveHeadline,
    liveMode,
    liveStatusColor,
    liveStatusLabel,
    liveSummary,
    previewHeadline: "Schema-driven contract preview",
    previewSummary:
      "Generates an admin-only example from the saved request/response schema and preview inputs. It does not call live flow nodes, deployments, or connections.",
  };
}
