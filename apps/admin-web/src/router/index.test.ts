import { describe, expect, it } from "vitest";
import { mapLegacySchemaEditorRedirect } from "./index";

describe("mapLegacySchemaEditorRedirect", () => {
  it("redirects legacy schema links into the route Contract tab", () => {
    const redirect = mapLegacySchemaEditorRedirect({
      params: { endpointId: "42" },
      query: {},
    } as never);

    expect(redirect).toEqual({
      name: "endpoints-edit",
      params: { endpointId: "42" },
      query: { tab: "contract" },
    });
  });

  it("preserves request/response schema subtabs from legacy query params", () => {
    const redirect = mapLegacySchemaEditorRedirect({
      params: { endpointId: "7" },
      query: { tab: "request", source: "deeplink" },
    } as never);

    expect(redirect).toEqual({
      name: "endpoints-edit",
      params: { endpointId: "7" },
      query: {
        tab: "contract",
        contractTab: "request",
        source: "deeplink",
      },
    });
  });
});
