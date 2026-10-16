import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";

const source = await readFile(new URL("src/worker.js", import.meta.url), "utf8");
const { createWorker } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const paths = ["/dashboard/", "/dashboard/systems/", "/dashboard/results/", "/dashboard/methods/", "/dashboard/analyze/", "/dashboard/snapshot.json", "/dashboard/terrain.png", "/dashboard/workspace.js", "/dashboard/workspace-model.js", "/dashboard/workspace.css", "/dashboard/data/river-approved.json", ...["atmosphere","cryosphere","geosphere","hydrosphere","terrestrial-biosphere","aquatic-biosphere"].map(slug=>`/dashboard/systems/${slug}/`)];
const worker = createWorker(paths);

test("public geographic, system, results, and scope pages reach the asset handler", async () => {
  for (const path of ["/dashboard/", "/dashboard/systems/", "/dashboard/results/", "/dashboard/methods/", "/dashboard/snapshot.json?refresh=1", "/dashboard/terrain.png", "/dashboard/workspace.js", "/dashboard/workspace-model.js", "/dashboard/workspace.css", ...["atmosphere","cryosphere","geosphere","hydrosphere","terrestrial-biosphere","aquatic-biosphere"].map(slug=>`/dashboard/systems/${slug}/`)]) {
    let calls = 0;
    const response = await worker.fetch(new Request("https://example.test" + path), { ASSETS: { fetch() { calls++; return new Response("public asset"); } } });
    assert.equal(response.status, 200); assert.equal(calls, 1);
  }
});

test("internal and unknown paths bypass cached assets and return 404", async () => {
  for (const path of ["/dashboard/data/river-other.json", "/dashboard/data/dashboard-data.js", "/yellowstone_python_spec/fixes/example.md", "/dashboard/build_data.py", "/_worker.js", "/dashboard/no-such-file"]) {
    const response = await worker.fetch(new Request("https://example.test" + path), { ASSETS: { fetch() { throw Error("Private path reached asset handler"); } } });
    assert.equal(response.status, 404); assert.equal(response.headers.get("cache-control"), "no-store");
  }
});

test("root and slashless page paths resolve to public pages", async () => {
  for (const path of ["/", "/dashboard", "/dashboard/systems", "/dashboard/results", "/dashboard/methods", "/dashboard/systems/hydrosphere"]) {
    const response = await worker.fetch(new Request("https://example.test" + path), {});
    assert.equal(response.status, 302);
    assert.equal(response.headers.get("location"), "https://example.test" + (path === "/" ? "/dashboard/" : path + "/"));
  }
});

test("unsupported methods cannot reach the asset handler", async () => {
  const response = await worker.fetch(new Request("https://example.test/dashboard/", { method: "POST" }), {});
  assert.equal(response.status, 405);
});
