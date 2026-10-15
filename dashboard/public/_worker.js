const PUBLIC_PATHS = ["/dashboard/analysis.css", "/dashboard/analysis.js", "/dashboard/analyze/index.html", "/dashboard/analyze/", "/dashboard/coverage.js", "/dashboard/data/aquatic-0d5d821d4d80e6d544cf10b233abeffa116cb7296e48ce916eb1153b81e48b61.json", "/dashboard/data/atmosphere-fda0d51af38fd0e1bf2f13c64ecc300b0004ec8d9080cc37c826063c9982bd41.json", "/dashboard/data/canopy-3c38b9f3cef3f8f5195123953ee790b51f77eabe4c3577efd11073450965fdb7.json", "/dashboard/data/land-47e9ca3e6a708aad84a57d328dfb072360a7e1ce6fd70cf497b8a8b156b0ffab.json", "/dashboard/data/river-cc2d4401b17168628f0e0e1140e2951e80fb3691693b3ea683cc6a916f79cb86.json", "/dashboard/data/snow-bad524353d60406a3ce43acbf0a9d8dddec1c67eeaad80e2aa99ba956c41aab4.json", "/dashboard/data/thermal-4059c6213623094c4269b2406fd8e6e15e47eeffc1f73a9a9113a5a5b372da62.json", "/dashboard/data/wildlife-689d556413a1430c6f4813d3224e96414450a8090cddf73fa191c31adac36d7c.json", "/dashboard/data-model.js", "/dashboard/explorer.css", "/dashboard/explorer.js", "/dashboard/ground-heat.png", "/dashboard/index.html", "/dashboard/", "/dashboard/landscape.png", "/dashboard/methods/index.html", "/dashboard/methods/", "/dashboard/results/index.html", "/dashboard/results/", "/dashboard/science.js", "/dashboard/snapshot.json", "/dashboard/systems/aquatic-biosphere/index.html", "/dashboard/systems/aquatic-biosphere/", "/dashboard/systems/atmosphere/index.html", "/dashboard/systems/atmosphere/", "/dashboard/systems/cryosphere/index.html", "/dashboard/systems/cryosphere/", "/dashboard/systems/geosphere/index.html", "/dashboard/systems/geosphere/", "/dashboard/systems/hydrosphere/index.html", "/dashboard/systems/hydrosphere/", "/dashboard/systems/index.html", "/dashboard/systems/", "/dashboard/systems/terrestrial-biosphere/index.html", "/dashboard/systems/terrestrial-biosphere/", "/dashboard/systems-model.js", "/dashboard/systems-workbench.css", "/dashboard/systems-workbench.js", "/dashboard/terrain.png", "/dashboard/workbench.css", "/dashboard/workbench.js", "/dashboard/workspace-model.js", "/dashboard/workspace.css", "/dashboard/workspace.js"];

export function createWorker(paths) {
  const approved = new Set(paths);
  return {
    async fetch(request, env) {
      const url = new URL(request.url);
      if (!["GET", "HEAD"].includes(request.method)) return new Response("Method unavailable", {status: 405});
      if (url.pathname === "/" || approved.has(url.pathname + "/")) {
        return Response.redirect(new URL(url.pathname === "/" ? "/dashboard/" : url.pathname + "/", url), 302);
      }
      if (!approved.has(url.pathname)) return new Response(request.method === "HEAD" ? null : "Page unavailable", {
        status: 404, headers: {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"}
      });
      return env.ASSETS.fetch(request);
    }
  };
}

export default createWorker(PUBLIC_PATHS);
