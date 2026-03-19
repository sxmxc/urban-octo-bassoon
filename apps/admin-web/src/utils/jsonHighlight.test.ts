import { describe, expect, it } from "vitest";

import { highlightJson } from "./jsonHighlight";

describe("highlightJson", () => {
  it("wraps keys and values in syntax token spans", () => {
    const html = highlightJson({
      name: "Artificer",
      count: 3,
      active: true,
      empty: null,
    });

    expect(html).toContain('class="json-token json-token--key"');
    expect(html).toContain('class="json-token json-token--string"');
    expect(html).toContain('class="json-token json-token--number"');
    expect(html).toContain('class="json-token json-token--boolean"');
    expect(html).toContain('class="json-token json-token--null"');
  });

  it("escapes html-sensitive characters before highlighting", () => {
    const html = highlightJson({
      snippet: "<script>alert(1)</script>",
    });

    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
    expect(html).not.toContain("<script>");
  });
});
