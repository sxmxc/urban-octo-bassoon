import type { Endpoint, RouteDeployment, RouteImplementation, RoutePublicationStatus } from "../types/endpoints";

const FALLBACK_ENABLED_STATUS: RoutePublicationStatus = {
  code: "legacy_mock",
  label: "Legacy mock",
  tone: "secondary",
  enabled: true,
  is_public: true,
  is_live: false,
  uses_legacy_mock: true,
  has_saved_implementation: false,
  has_runtime_history: false,
  has_deployment_history: false,
  has_active_deployment: false,
  active_deployment_environment: null,
  active_implementation_id: null,
  active_deployment_id: null,
};

const FALLBACK_DISABLED_STATUS: RoutePublicationStatus = {
  code: "disabled",
  label: "Disabled",
  tone: "error",
  enabled: false,
  is_public: false,
  is_live: false,
  uses_legacy_mock: false,
  has_saved_implementation: false,
  has_runtime_history: false,
  has_deployment_history: false,
  has_active_deployment: false,
  active_deployment_environment: null,
  active_implementation_id: null,
  active_deployment_id: null,
};

export function resolveRoutePublicationStatus(
  endpoint: Pick<Endpoint, "enabled" | "publication_status">,
): RoutePublicationStatus {
  if (endpoint.publication_status) {
    return endpoint.publication_status;
  }
  return endpoint.enabled ? FALLBACK_ENABLED_STATUS : FALLBACK_DISABLED_STATUS;
}

export function resolveRuntimeRoutePublicationStatus(
  endpoint: Pick<Endpoint, "enabled" | "publication_status">,
  currentImplementation?: Pick<RouteImplementation, "id"> | null,
  deployments?: Array<Pick<RouteDeployment, "id" | "environment" | "implementation_id" | "is_active">>,
): RoutePublicationStatus {
  const publicationStatus = resolveRoutePublicationStatus(endpoint);
  if (!endpoint.enabled) {
    return publicationStatus.code === "disabled"
      ? publicationStatus
      : {
          ...publicationStatus,
          code: "disabled",
          label: "Disabled",
          tone: "error",
          enabled: false,
          is_public: false,
          is_live: false,
          uses_legacy_mock: false,
          has_active_deployment: false,
          active_deployment_environment: null,
          active_implementation_id: null,
          active_deployment_id: null,
        };
  }

  const runtimeDeployments = deployments ?? [];
  const activeDeployment = runtimeDeployments.find((deployment) => deployment.is_active) ?? null;
  const hasSavedImplementation =
    publicationStatus.has_saved_implementation ||
    (currentImplementation?.id !== null && currentImplementation?.id !== undefined);
  const hasDeploymentHistory = publicationStatus.has_deployment_history || runtimeDeployments.length > 0;
  const hasRuntimeHistory = publicationStatus.has_runtime_history || hasSavedImplementation || hasDeploymentHistory;

  if (activeDeployment) {
    return {
      ...publicationStatus,
      code: "published_live",
      label: "Published live",
      tone: "success",
      enabled: true,
      is_public: true,
      is_live: true,
      uses_legacy_mock: false,
      has_saved_implementation: hasSavedImplementation,
      has_runtime_history: hasRuntimeHistory,
      has_deployment_history: true,
      has_active_deployment: true,
      active_deployment_environment: activeDeployment.environment,
      active_implementation_id: activeDeployment.implementation_id,
      active_deployment_id: activeDeployment.id ?? publicationStatus.active_deployment_id ?? null,
    };
  }

  if (runtimeDeployments.length > 0) {
    return {
      ...publicationStatus,
      code: "live_disabled",
      label: "Live disabled",
      tone: "warning",
      enabled: true,
      is_public: false,
      is_live: false,
      uses_legacy_mock: false,
      has_saved_implementation: hasSavedImplementation,
      has_runtime_history: hasRuntimeHistory,
      has_deployment_history: true,
      has_active_deployment: false,
      active_deployment_environment: null,
      active_implementation_id: null,
      active_deployment_id: null,
    };
  }

  if (hasSavedImplementation && runtimeDeployments.length === 0) {
    if (publicationStatus.code === "published_live" || publicationStatus.code === "live_disabled") {
      return {
        ...publicationStatus,
        has_saved_implementation: hasSavedImplementation,
        has_runtime_history: hasRuntimeHistory,
        has_deployment_history: publicationStatus.has_deployment_history || publicationStatus.code === "published_live",
      };
    }

    if (publicationStatus.has_deployment_history) {
      return {
        ...publicationStatus,
        code: "live_disabled",
        label: "Live disabled",
        tone: "warning",
        enabled: true,
        is_public: false,
        is_live: false,
        uses_legacy_mock: false,
        has_saved_implementation: hasSavedImplementation,
        has_runtime_history: hasRuntimeHistory,
        has_deployment_history: true,
        has_active_deployment: false,
        active_deployment_environment: null,
        active_implementation_id: null,
        active_deployment_id: null,
      };
    }
  }

  if (currentImplementation?.id !== null && currentImplementation?.id !== undefined) {
    return {
      ...publicationStatus,
      code: "draft_only",
      label: "Draft only",
      tone: "warning",
      enabled: true,
      is_public: false,
      is_live: false,
      uses_legacy_mock: false,
      has_saved_implementation: true,
      has_runtime_history: true,
      has_deployment_history: publicationStatus.has_deployment_history,
      has_active_deployment: false,
      active_deployment_environment: null,
      active_implementation_id: null,
      active_deployment_id: null,
    };
  }

  return publicationStatus;
}

export function routePublicationColor(status: Pick<RoutePublicationStatus, "code" | "tone">): string {
  if (status.code === "published_live") {
    return "accent";
  }
  if (status.code === "disabled") {
    return "error";
  }
  if (status.code === "legacy_mock") {
    return "secondary";
  }
  if (status.code === "draft_only" || status.code === "live_disabled") {
    return "warning";
  }

  if (status.tone === "success") {
    return "accent";
  }
  if (status.tone === "error") {
    return "error";
  }
  if (status.tone === "warning") {
    return "warning";
  }
  return "secondary";
}
