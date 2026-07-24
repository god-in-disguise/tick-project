import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const args = process.argv.slice(2);
const port = Number(readArg("--port") ?? process.env.PORT ?? 5174);
const host = readArg("--host") ?? process.env.HOST ?? "0.0.0.0";

const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg"
};

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);
    const pathname = url.pathname === "/" ? "/index.html" : url.pathname;
    const safePath = normalize(pathname).replace(/^(\.\.[/\\])+/, "");
    const filePath = join(root, safePath);
    const data = await readFile(filePath);

    response.writeHead(200, {
      "Content-Type": types[extname(filePath)] ?? "application/octet-stream",
      "Cache-Control": "no-store"
    });
    response.end(data);
  } catch (error) {
    if (request.url?.includes(".")) {
      response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      response.end("Not found");
      return;
    }

    const data = await readFile(join(root, "index.html"));
    response.writeHead(200, {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store"
    });
    response.end(data);
  }
});

server.listen(port, host, () => {
  console.log(`TICK web app running at http://localhost:${port}`);
  console.log(`LAN: http://0.0.0.0:${port}`);
});

function readArg(name) {
  const index = args.indexOf(name);
  if (index === -1) return undefined;
  return args[index + 1];
}
