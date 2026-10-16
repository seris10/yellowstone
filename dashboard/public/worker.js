const PUBLIC_PATHS = /* PUBLIC_PATHS */ [];

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
