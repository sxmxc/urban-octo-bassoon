import type { Endpoint, RouteDeployment, RouteImplementation } from "../types/endpoints";
import {
  resolveRuntimeRoutePublicationStatus,
  routePublicationColor,
} from "./routePublicationStatus";

export type RouteLiveRequestMode = "disabled" | "legacy_mock" | "live_active" | "live_disabled" | "draft_only";

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
  endpoint: Pick<Endpoint, "enabled" | "publication_status">,
  currentImplementation: Pick<RouteImplementation, "id" | "is_draft" | "version"> | null | undefined,
  deployments: Array<Pick<RouteDeployment, "id" | "environment" | "implementation_id" | "is_active">>,
): RouteTestState {
  const publicationStatus = resolveRuntimeRoutePublicationStatus(endpoint, currentImplementation, deployments);
  const activeDeployment = deployments.find((deployment) => deployment.is_active) ?? null;
  const activeEnvironment = activeDeployment?.environment ?? publicationStatus.active_deployment_environment ?? "production";
  const activeImplementationId = activeDeployment?.implementation_id ?? publicationStatus.active_implementation_id ?? null;
  const hasDeploymentHistory = publicationStatus.has_deployment_history || deployments.length > 0;
  const hasSavedImplementation =
    publicationStatus.has_saved_implementation ||
    (currentImplementation?.id !== null && currentImplementation?.id !== undefined);
  const hasRuntimeHistory = publicationStatus.has_runtime_history || hasSavedImplementation || hasDeploymentHistory;

  let liveMode: RouteLiveRequestMode;
  let liveStatusLabel: string;
  let liveStatusColor: string;
  let liveHeadline: string;
  let liveSummary: string;
  let executionsEmptyState: string;

  if (publicationStatus.code === "disabled") {
    liveMode = "disabled";
    liveStatusLabel = publicationStatus.label;
    liveStatusColor = routePublicationColor(publicationStatus);
    liveHeadline = activeDeployment ? "Route disabled over live config" : "Route disabled";
    liveSummary = activeDeployment
      ? `${activeEnvironment} has a deployment, but the route is disabled and returns 404 until re-enabled.`
      : hasRuntimeHistory
        ? "This route is disabled and currently returns 404."
        : "This route is disabled. Re-enable it before sending live requests.";
    executionsEmptyState = "This route is disabled, so live requests return 404. Contract preview is still available.";
  } else if (publicationStatus.code === "published_live") {
    liveMode = "live_active";
    liveStatusLabel = publicationStatus.label;
    liveStatusColor = routePublicationColor(publicationStatus);
    liveHeadline = `Implementation ${activeImplementationId ?? "current"} is live`;
    liveSummary = `Live requests use the active ${activeEnvironment} deployment and write traces below.`;
    executionsEmptyState = `No live runs yet. Send a request from the tester or another client to create the first ${activeEnvironment} trace.`;
  } else if (publicationStatus.code === "live_disabled") {
    liveMode = "live_disabled";
    liveStatusLabel = publicationStatus.label;
    liveStatusColor = routePublicationColor(publicationStatus);
    liveHeadline = "No active deployment";
    liveSummary = "No deployment is active. Live requests return 404 until you publish again.";
    executionsEmptyState = "No live runs yet because this route has no active deployment.";
  } else if (publicationStatus.code === "draft_only") {
    liveMode = "draft_only";
    liveStatusLabel = publicationStatus.label;
    liveStatusColor = routePublicationColor(publicationStatus);
    liveHeadline = "Draft only";
    liveSummary = "A draft is saved, but no deployment is active. Live requests return 404 until publish.";
    executionsEmptyState = "No live runs yet because this route has no active deployment.";
  } else {
    liveMode = "legacy_mock";
    liveStatusLabel = publicationStatus.label;
    liveStatusColor = routePublicationColor(publicationStatus);
    liveHeadline = "Legacy mock route";
    liveSummary = "This route still uses the legacy mock path.";
    executionsEmptyState = "Legacy mock requests do not create execution traces. Publish flow to start trace history.";
  }

  let currentDraftBadgeColor = "secondary";
  let currentDraftBadgeLabel = "Scaffold only";
  let draftHeadline = "No saved flow draft yet";
  let draftSummary = "The Flow tab is still on the default scaffold. Save the flow to create a real draft.";

  if (hasSavedImplementation && currentImplementation) {
    if (currentImplementation.is_draft === false) {
      currentDraftBadgeColor = "accent";
      currentDraftBadgeLabel = "Published base";
      if (activeImplementationId !== null && activeImplementationId === currentImplementation.id) {
        draftHeadline = "Published base matches live";
        draftSummary = `The latest saved implementation is already serving the active ${activeEnvironment} deployment.`;
      } else if (hasDeploymentHistory) {
        draftHeadline = "Published base saved";
        draftSummary = "The latest saved implementation is not editable and no deployment is active.";
      } else {
        draftHeadline = "Published base saved";
        draftSummary = "The latest saved implementation is not marked as an editable draft.";
      }
    } else {
      currentDraftBadgeColor = "warning";
      currentDraftBadgeLabel = "Draft";
      if (activeImplementationId !== null) {
        draftHeadline = `Draft v${currentImplementation.version} is ahead of live`;
        draftSummary = `The latest draft is not deployed. Live requests still use implementation ${activeImplementationId}.`;
      } else if (hasDeploymentHistory) {
        draftHeadline = `Draft v${currentImplementation.version} is saved`;
        draftSummary = "The latest draft is editable, but live traffic is disabled until you publish again.";
      } else {
        draftHeadline = `Draft v${currentImplementation.version} is saved`;
        draftSummary = "The latest draft is editable, but live requests return 404 until publish.";
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
    previewHeadline: "Contract preview",
    previewSummary:
      "Generate an admin-only sample from the saved contract and preview inputs.",
  };
}
