const PUBLIC_PATHS = new Set([
  "/dashboard/", "/dashboard/index.html", "/dashboard/systems/", "/dashboard/systems/index.html",
  "/dashboard/results/", "/dashboard/results/index.html", "/dashboard/methods/", "/dashboard/methods/index.html",
  "/dashboard/explorer.css", "/dashboard/explorer.js", "/dashboard/coverage.js", "/dashboard/science.js",
  "/dashboard/snapshot.json", "/dashboard/terrain.png", "/dashboard/landscape.png"
]);

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!["GET", "HEAD"].includes(request.method)) return new Response("Method unavailable", { status: 405 });
    if (url.pathname === "/" || ["/dashboard", "/dashboard/systems", "/dashboard/results", "/dashboard/methods"].includes(url.pathname)) {
      return Response.redirect(new URL(url.pathname === "/" ? "/dashboard/" : url.pathname + "/", url), 302);
    }
    if (!PUBLIC_PATHS.has(url.pathname)) {
      return new Response(request.method === "HEAD" ? null : "Page unavailable", {
        status: 404, headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" }
      });
    }
    return env.ASSETS.fetch(request);
  }
};
