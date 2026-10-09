import { randomBytes, timingSafeEqual } from "node:crypto";
import {
  chmodSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import http from "node:http";
import path from "node:path";

const SESSION_COOKIE = "reachcut_local_session";
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

export function randomToken(bytes = 32) {
  return randomBytes(bytes).toString("base64url");
}

export function validateLocalHostname(value) {
  const hostname = value.trim().toLowerCase().replace(/\.$/, "");
  if (!hostname.endsWith(".localhost")) {
    throw new Error("REACHCUT_LOCAL_HOSTNAME must end with .localhost");
  }
  if (hostname.length > 253) {
    throw new Error("REACHCUT_LOCAL_HOSTNAME is too long");
  }
  const labels = hostname.split(".");
  if (
    labels.some(
      (label) =>
        label.length === 0 ||
        label.length > 63 ||
        !/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label),
    )
  ) {
    throw new Error("REACHCUT_LOCAL_HOSTNAME contains an invalid DNS label");
  }
  return hostname;
}

export function parsePort(value, name) {
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new Error(`${name} must be an integer between 1 and 65535`);
  }
  return port;
}

export function parseCommand(value, name, replacements = {}) {
  if (!value) return null;
  let command;
  try {
    command = JSON.parse(value);
  } catch {
    throw new Error(`${name} must be a JSON array of command arguments`);
  }
  if (
    !Array.isArray(command) ||
    command.length === 0 ||
    command.some((part) => typeof part !== "string" || part.length === 0)
  ) {
    throw new Error(
      `${name} must be a non-empty JSON array of non-empty strings`,
    );
  }
  return command.map((part) =>
    Object.entries(replacements).reduce(
      (result, [key, replacement]) =>
        result.replaceAll(`{${key}}`, String(replacement)),
      part,
    ),
  );
}

export function resolveUserDataDir(
  platform = process.platform,
  environment = process.env,
  homeDirectory = environment.HOME ?? environment.USERPROFILE,
  applicationDirectory = platform === "linux" ? "reachcut" : "ReachCut",
) {
  const platformPath = platform === "win32" ? path.win32 : path.posix;
  if (platform === "win32") {
    const base = environment.LOCALAPPDATA;
    if (!base)
      throw new Error(
        "LOCALAPPDATA is required by the packaged ReachCut agent",
      );
    return platformPath.join(base, applicationDirectory);
  }
  if (!homeDirectory) {
    throw new Error(
      "The user home directory is required by the packaged ReachCut agent",
    );
  }
  if (platform === "darwin") {
    return platformPath.join(
      homeDirectory,
      "Library",
      "Application Support",
      applicationDirectory,
    );
  }
  return platformPath.join(
    environment.XDG_DATA_HOME ??
      platformPath.join(homeDirectory, ".local", "share"),
    applicationDirectory,
  );
}

export function readActivationState(filePath, publicHostname, publicPort) {
  let state;
  try {
    state = JSON.parse(readFileSync(filePath, "utf8"));
  } catch (error) {
    throw new Error(
      `could not read the local activation state: ${error.message}`,
    );
  }
  if (
    state?.schemaVersion !== 1 ||
    state.hostname !== publicHostname ||
    state.port !== publicPort ||
    typeof state.token !== "string" ||
    state.token.length < 32
  ) {
    throw new Error(
      "local activation state is invalid or belongs to another profile",
    );
  }
  return state;
}

export function writeActivationState(
  filePath,
  { publicHostname, publicPort, activationToken },
) {
  const temporaryPath = `${filePath}.${process.pid}.${randomToken(8)}.tmp`;
  const payload = `${JSON.stringify({
    schemaVersion: 1,
    hostname: publicHostname,
    port: publicPort,
    token: activationToken,
  })}\n`;
  try {
    writeFileSync(temporaryPath, payload, { encoding: "utf8", mode: 0o600 });
    chmodSync(temporaryPath, 0o600);
    rmSync(filePath, { force: true });
    renameSync(temporaryPath, filePath);
  } catch (error) {
    rmSync(temporaryPath, { force: true });
    throw error;
  }
}

export function removeActivationState(filePath, activationToken) {
  try {
    const state = JSON.parse(readFileSync(filePath, "utf8"));
    if (
      typeof state?.token === "string" &&
      equalSecret(state.token, activationToken)
    ) {
      rmSync(filePath, { force: true });
    }
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

export function gatewayIsRunning(publicHostname, publicPort, timeoutMs = 750) {
  return new Promise((resolve) => {
    const authority = `${publicHostname}${publicPort === 80 ? "" : `:${publicPort}`}`;
    const request = http.get(
      {
        hostname: "127.0.0.1",
        port: publicPort,
        path: "/__reachcut/health",
        headers: { Host: authority },
      },
      (response) => {
        response.resume();
        resolve(response.statusCode === 200);
      },
    );
    request.setTimeout(timeoutMs, () => request.destroy());
    request.once("error", () => resolve(false));
  });
}

export function requestGatewayActivation(
  publicHostname,
  publicPort,
  activationToken,
  timeoutMs = 2_000,
) {
  return new Promise((resolve, reject) => {
    const authority = `${publicHostname}${publicPort === 80 ? "" : `:${publicPort}`}`;
    const request = http.request(
      {
        hostname: "127.0.0.1",
        port: publicPort,
        path: "/__reachcut/activate",
        method: "POST",
        headers: {
          Host: authority,
          "Content-Length": "0",
          "X-ReachCut-Activation": activationToken,
        },
      },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          const body = Buffer.concat(chunks).toString("utf8");
          if (response.statusCode !== 200) {
            reject(
              new Error(
                `running ReachCut agent rejected activation (HTTP ${response.statusCode ?? "unknown"})`,
              ),
            );
            return;
          }
          try {
            const payload = JSON.parse(body);
            if (typeof payload.url !== "string")
              throw new Error("activation response did not include a URL");
            const url = new URL(payload.url);
            if (
              url.protocol !== "http:" ||
              url.hostname !== publicHostname ||
              Number(url.port || 80) !== publicPort ||
              url.pathname !== "/__reachcut/bootstrap" ||
              !url.hash.startsWith("#token=")
            ) {
              throw new Error("activation response included an invalid URL");
            }
            resolve(payload.url);
          } catch (error) {
            reject(
              new Error(
                `invalid response from running ReachCut agent: ${error.message}`,
              ),
            );
          }
        });
      },
    );
    request.setTimeout(timeoutMs, () =>
      request.destroy(new Error("timed out activating running ReachCut agent")),
    );
    request.once("error", reject);
    request.end();
  });
}

function equalSecret(actual, expected) {
  const actualBuffer = Buffer.from(actual);
  const expectedBuffer = Buffer.from(expected);
  return (
    actualBuffer.length === expectedBuffer.length &&
    timingSafeEqual(actualBuffer, expectedBuffer)
  );
}

function cookies(request) {
  return new Map(
    (request.headers.cookie ?? "")
      .split(";")
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => {
        const separator = item.indexOf("=");
        return separator === -1
          ? [item, ""]
          : [item.slice(0, separator), item.slice(separator + 1)];
      }),
  );
}

function requestPath(request) {
  try {
    return new URL(request.url ?? "/", "http://reachcut.invalid").pathname;
  } catch {
    return null;
  }
}

function sendJson(response, statusCode, body) {
  const payload = Buffer.from(JSON.stringify(body));
  response.writeHead(statusCode, {
    "Cache-Control": "no-store",
    "Content-Length": payload.length,
    "Content-Type": "application/json; charset=utf-8",
    "X-Content-Type-Options": "nosniff",
  });
  response.end(payload);
}

function sendUnauthorized(response) {
  const payload = Buffer.from(
    '<!doctype html><html lang="en"><meta charset="utf-8">' +
      "<title>ReachCut authorization required</title>" +
      "<body><h1>Open ReachCut from its application shortcut</h1>" +
      "<p>This local session is not authorized. Relaunch ReachCut to continue.</p></body></html>",
  );
  response.writeHead(401, {
    "Cache-Control": "no-store",
    "Content-Length": payload.length,
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    "Content-Type": "text/html; charset=utf-8",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  });
  response.end(payload);
}

function bootstrapPage(response) {
  const nonce = randomToken(18);
  const payload = Buffer.from(`<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="referrer" content="no-referrer">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Opening ReachCut…</title>
  </head>
  <body>
    <main><h1>Opening ReachCut…</h1><p id="status">Authorizing this local browser session.</p></main>
    <script nonce="${nonce}">
      const token = new URLSearchParams(location.hash.slice(1)).get("token");
      history.replaceState(null, "", "/__reachcut/bootstrap");
      if (!token) {
        document.querySelector("#status").textContent = "Launch ReachCut again to authorize this browser.";
      } else {
        fetch("/__reachcut/session", {
          method: "POST",
          headers: { "X-ReachCut-Bootstrap": token },
        }).then((response) => {
          if (!response.ok) throw new Error("authorization failed");
          location.replace("/");
        }).catch(() => {
          document.querySelector("#status").textContent = "Authorization failed. Launch ReachCut again.";
        });
      }
    </script>
  </body>
</html>`);
  response.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Length": payload.length,
    "Content-Security-Policy": `default-src 'none'; script-src 'nonce-${nonce}'`,
    "Content-Type": "text/html; charset=utf-8",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  });
  response.end(payload);
}

function sanitizedProxyHeaders(request, targetPort, apiToken, publicAuthority) {
  const headers = { ...request.headers };
  for (const name of HOP_BY_HOP_HEADERS) delete headers[name];
  delete headers.cookie;
  delete headers["x-reachcut-agent-token"];
  headers.host = `127.0.0.1:${targetPort}`;
  headers["x-forwarded-for"] = "127.0.0.1";
  headers["x-forwarded-host"] = publicAuthority;
  headers["x-forwarded-proto"] = "http";
  if (apiToken) headers["x-reachcut-agent-token"] = apiToken;
  return headers;
}

function applySecurityHeaders(headers, development) {
  const result = { ...headers };
  for (const name of Object.keys(result)) {
    if (HOP_BY_HOP_HEADERS.has(name.toLowerCase())) delete result[name];
  }
  const scripts = development
    ? "'self' 'unsafe-inline' 'unsafe-eval'"
    : "'self' 'unsafe-inline'";
  const connections = development ? "'self' ws: wss:" : "'self'";
  result["content-security-policy"] = [
    "default-src 'self'",
    `script-src ${scripts}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "media-src 'self' blob:",
    `connect-src ${connections}`,
    "font-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
  ].join("; ");
  result["cross-origin-opener-policy"] = "same-origin";
  result["permissions-policy"] = "camera=(), geolocation=(), microphone=()";
  result["referrer-policy"] = "no-referrer";
  result["x-content-type-options"] = "nosniff";
  result["x-frame-options"] = "DENY";
  return result;
}

export function createGateway({
  publicHostname,
  publicPort,
  apiPort,
  webPort,
  apiToken,
  activationToken,
  bootstrapToken,
  sessionToken,
  bootstrapLifetimeMs = 120_000,
  development = false,
  logger = console,
}) {
  const hostname = validateLocalHostname(publicHostname);
  const bootstrapTokens = new Map([[bootstrapToken, Date.now()]]);
  let server;

  function pruneBootstrapTokens() {
    const cutoff = Date.now() - bootstrapLifetimeMs;
    for (const [token, createdAt] of bootstrapTokens) {
      if (createdAt < cutoff) bootstrapTokens.delete(token);
    }
  }

  function freshBootstrapUrl() {
    pruneBootstrapTokens();
    const token = randomToken();
    bootstrapTokens.set(token, Date.now());
    return `${origin()}/__reachcut/bootstrap#token=${encodeURIComponent(token)}`;
  }

  function consumeBootstrapToken(supplied) {
    if (typeof supplied !== "string") return false;
    pruneBootstrapTokens();
    for (const token of bootstrapTokens.keys()) {
      if (equalSecret(supplied, token)) {
        bootstrapTokens.delete(token);
        return true;
      }
    }
    return false;
  }

  function resolvedPort() {
    if (publicPort) return publicPort;
    const address = server.address();
    if (!address || typeof address === "string")
      throw new Error("gateway is not listening");
    return address.port;
  }

  function origin() {
    const port = resolvedPort();
    return `http://${hostname}${port === 80 ? "" : `:${port}`}`;
  }

  function authorized(request) {
    return equalSecret(
      cookies(request).get(SESSION_COOKIE) ?? "",
      sessionToken,
    );
  }

  function validAuthority(request) {
    return request.headers.host?.toLowerCase() === new URL(origin()).host;
  }

  function validMutationOrigin(request) {
    if (["GET", "HEAD", "OPTIONS"].includes(request.method ?? "GET"))
      return true;
    return request.headers.origin === origin();
  }

  function proxy(request, response) {
    const path = requestPath(request);
    if (path === null) {
      sendJson(response, 400, { detail: "invalid request path" });
      return;
    }
    const isApi = path === "/api" || path.startsWith("/api/");
    const targetPort = isApi ? apiPort : webPort;
    const upstream = http.request(
      {
        hostname: "127.0.0.1",
        port: targetPort,
        method: request.method,
        path: request.url,
        headers: sanitizedProxyHeaders(
          request,
          targetPort,
          isApi ? apiToken : null,
          new URL(origin()).host,
        ),
      },
      (upstreamResponse) => {
        response.writeHead(
          upstreamResponse.statusCode ?? 502,
          applySecurityHeaders(upstreamResponse.headers, development),
        );
        upstreamResponse.pipe(response);
      },
    );
    upstream.on("error", (error) => {
      logger.error(`ReachCut upstream request failed: ${error.message}`);
      if (!response.headersSent)
        sendJson(response, 503, { detail: "ReachCut is starting" });
      else response.destroy(error);
    });
    request.on("aborted", () => upstream.destroy());
    request.pipe(upstream);
  }

  server = http.createServer((request, response) => {
    if (!validAuthority(request)) {
      sendJson(response, 421, { detail: "unrecognized local hostname" });
      return;
    }

    const path = requestPath(request);
    if (path === null) {
      sendJson(response, 400, { detail: "invalid request path" });
      return;
    }
    if (request.method === "GET" && path === "/__reachcut/bootstrap") {
      bootstrapPage(response);
      return;
    }
    if (request.method === "POST" && path === "/__reachcut/activate") {
      const supplied = request.headers["x-reachcut-activation"];
      if (
        typeof activationToken !== "string" ||
        typeof supplied !== "string" ||
        !equalSecret(supplied, activationToken)
      ) {
        sendJson(response, 401, { detail: "invalid activation token" });
        return;
      }
      sendJson(response, 200, { url: freshBootstrapUrl() });
      return;
    }
    if (request.method === "POST" && path === "/__reachcut/session") {
      if (!validMutationOrigin(request)) {
        sendJson(response, 403, { detail: "invalid request origin" });
        return;
      }
      const supplied = request.headers["x-reachcut-bootstrap"];
      if (!consumeBootstrapToken(supplied)) {
        sendJson(response, 401, {
          detail: "invalid or expired bootstrap token",
        });
        return;
      }
      response.writeHead(204, {
        "Cache-Control": "no-store",
        "Set-Cookie": `${SESSION_COOKIE}=${sessionToken}; HttpOnly; SameSite=Strict; Max-Age=31536000; Path=/`,
      });
      response.end();
      return;
    }
    if (request.method === "GET" && path === "/__reachcut/health") {
      sendJson(response, 200, { status: "ok" });
      return;
    }
    if (!authorized(request)) {
      sendUnauthorized(response);
      return;
    }
    if (!validMutationOrigin(request)) {
      sendJson(response, 403, { detail: "invalid request origin" });
      return;
    }
    proxy(request, response);
  });

  server.requestTimeout = 0;
  server.headersTimeout = 60_000;
  server.keepAliveTimeout = 5_000;

  server.on("upgrade", (request, socket, head) => {
    if (!validAuthority(request) || !authorized(request)) {
      socket.end("HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n");
      return;
    }
    if (request.headers.origin && request.headers.origin !== origin()) {
      socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
      return;
    }
    const path = requestPath(request);
    if (path === null) {
      socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n");
      return;
    }
    const isApi = path === "/api" || path.startsWith("/api/");
    const targetPort = isApi ? apiPort : webPort;
    const upstreamRequest = http.request({
      hostname: "127.0.0.1",
      port: targetPort,
      method: request.method,
      path: request.url,
      headers: {
        ...sanitizedProxyHeaders(
          request,
          targetPort,
          isApi ? apiToken : null,
          new URL(origin()).host,
        ),
        connection: "Upgrade",
        upgrade: request.headers.upgrade ?? "websocket",
      },
    });
    upstreamRequest.on(
      "upgrade",
      (upstreamResponse, upstreamSocket, upstreamHead) => {
        const headers = Object.entries(upstreamResponse.headers)
          .flatMap(([name, value]) =>
            Array.isArray(value)
              ? value.map((item) => `${name}: ${item}`)
              : [`${name}: ${value}`],
          )
          .join("\r\n");
        socket.write(`HTTP/1.1 101 Switching Protocols\r\n${headers}\r\n\r\n`);
        if (upstreamHead.length) socket.write(upstreamHead);
        if (head.length) upstreamSocket.write(head);
        upstreamSocket.pipe(socket).pipe(upstreamSocket);
      },
    );
    upstreamRequest.on("response", (upstreamResponse) => {
      socket.end(
        `HTTP/1.1 ${upstreamResponse.statusCode ?? 502} Bad Gateway\r\n\r\n`,
      );
    });
    upstreamRequest.on("error", () => {
      socket.end(
        "HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\n\r\n",
      );
    });
    upstreamRequest.end();
  });

  return {
    server,
    origin,
    bootstrapUrl() {
      return `${origin()}/__reachcut/bootstrap#token=${encodeURIComponent(bootstrapToken)}`;
    },
  };
}

export async function waitForHttp(
  url,
  { headers = {}, timeoutMs = 60_000 } = {},
) {
  const deadline = Date.now() + timeoutMs;
  let lastError = new Error("service did not respond");
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, {
        headers,
        redirect: "manual",
        signal: AbortSignal.timeout(2_000),
      });
      if (response.ok || (response.status >= 300 && response.status < 500))
        return;
      lastError = new Error(`service returned HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError.message}`);
}
