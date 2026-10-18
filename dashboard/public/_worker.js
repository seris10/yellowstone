const PUBLIC_PATHS = ["/dashboard/analysis.css", "/dashboard/analysis.js", "/dashboard/analyze/index.html", "/dashboard/analyze/", "/dashboard/coverage.js", "/dashboard/data/aquatic-fa995e5220098811f513ba4ec3d73712219ba0bd61d065397cddd23688327986.json", "/dashboard/data/atmosphere-e87c6bbbba5e645c68f093bbc8b331a2320a5ceb2d6752e85842016d6a9ad9b8.json", "/dashboard/data/canopy-157fbd7fbb8fcaf67258d360c433d51e423f900055ac1d26a792b630966faabf.json", "/dashboard/data/land-5acd01253a1039bb5b2f329dcaf30ac519d384f3e0d2b463c0d588f7ec6389c7.json", "/dashboard/data/process-hyporheic-4fd8c664f52d2a530015ebd026808d29b40ba986bc290ff402d0b8675fb8b207.json", "/dashboard/data/process-mat-6605635a4c7a4e0802cc297abe6c7d704fa4f656071d220e4cd77c1737e64f7c.json", "/dashboard/data/process-steam-89ae186f5a7f4bc2991a00c99a05f1f7f9edc5326f6789243c2130cc9b07a3f0.json", "/dashboard/data/river-cc2d4401b17168628f0e0e1140e2951e80fb3691693b3ea683cc6a916f79cb86.json", "/dashboard/data/snow-fb310c540bb53a22f79d6b0c99f7fe49eb377a00b41898e827143db83d68da4e.json", "/dashboard/data/thermal-a032030082b069cd23ff0fc94153ac6941b04636c30b1865623c9fa4a3b5ef6f.json", "/dashboard/data/wildlife-2ec21f2a4d68a5dee5a6d68c1bd8258a392d58c06e81c3a4b274a7909537eeaa.json", "/dashboard/data-model.js", "/dashboard/explorer.css", "/dashboard/explorer.js", "/dashboard/ground-heat.png", "/dashboard/index.html", "/dashboard/", "/dashboard/landscape.png", "/dashboard/methods/index.html", "/dashboard/methods/", "/dashboard/process-data.js", "/dashboard/process-ecology.css", "/dashboard/process-ecology.js", "/dashboard/process-thermal.css", "/dashboard/process-thermal.js", "/dashboard/process-visuals.css", "/dashboard/process-visuals.js", "/dashboard/results/index.html", "/dashboard/results/", "/dashboard/science.js", "/dashboard/snapshot.json", "/dashboard/systems/aquatic-biosphere/index.html", "/dashboard/systems/aquatic-biosphere/", "/dashboard/systems/atmosphere/index.html", "/dashboard/systems/atmosphere/", "/dashboard/systems/cryosphere/index.html", "/dashboard/systems/cryosphere/", "/dashboard/systems/geosphere/index.html", "/dashboard/systems/geosphere/", "/dashboard/systems/hydrosphere/index.html", "/dashboard/systems/hydrosphere/", "/dashboard/systems/index.html", "/dashboard/systems/", "/dashboard/systems/terrestrial-biosphere/index.html", "/dashboard/systems/terrestrial-biosphere/", "/dashboard/systems-model.js", "/dashboard/systems-workbench.css", "/dashboard/systems-workbench.js", "/dashboard/terrain.png", "/dashboard/workbench.css", "/dashboard/workbench.js", "/dashboard/workspace-model.js", "/dashboard/workspace.css", "/dashboard/workspace.js"];

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
