import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/vue";

import ConnectionManagerCard from "./ConnectionManagerCard.vue";
import { vuetify } from "../plugins/vuetify";
import type { Connection } from "../types/endpoints";

function buildConnection(overrides: Partial<Connection>): Connection {
  return {
    id: 1,
    project: "project-alpha",
    environment: "production",
    name: "Alpha upstream",
    connector_type: "http",
    description: null,
    config: { base_url: "https://alpha.example.com" },
    is_active: true,
    created_at: "2026-03-19T00:00:00Z",
    updated_at: "2026-03-19T00:00:00Z",
    ...overrides,
  };
}

describe("ConnectionManagerCard", () => {
  it("realigns list filters when preferred scope props change", async () => {
    const connections: Connection[] = [
      buildConnection({
        id: 1,
        project: "project-alpha",
        environment: "production",
        name: "Alpha upstream",
      }),
      buildConnection({
        id: 2,
        project: "project-beta",
        environment: "staging",
        name: "Beta upstream",
        config: { base_url: "https://beta.example.com" },
      }),
    ];

    const view = render(ConnectionManagerCard, {
      props: {
        connections,
        preferredProject: "project-alpha",
        preferredEnvironment: "production",
      },
      global: {
        plugins: [vuetify],
      },
    });

    expect(screen.getByText("Alpha upstream")).toBeInTheDocument();
    expect(screen.queryByText("Beta upstream")).not.toBeInTheDocument();

    await view.rerender({
      connections,
      preferredProject: "project-beta",
      preferredEnvironment: "staging",
    });

    expect(screen.getByText("Beta upstream")).toBeInTheDocument();
    expect(screen.queryByText("Alpha upstream")).not.toBeInTheDocument();
  });
});
