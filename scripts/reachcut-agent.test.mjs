import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { after, before, describe, test } from "node:test";

import {
  createGateway,
  gatewayIsRunning,
  parseCommand,
  parsePort,
  readActivationState,
  removeActivationState,
  requestGatewayActivation,
  resolveUserDataDir,
  validateLocalHostname,
  writeActivationState,
} from "./reachcut-agent-lib.mjs";

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolve(server.address().port));
  });
}

function close(server) {
  return new Promise((resolve) => server.close(resolve));
}

function request({
  port,
  path = "/",
  method = "GET",
  headers = {},
  body = "",
}) {
  return new Promise((resolve, reject) => {
    const outgoing = http.request(
      { hostname: "127.0.0.1", port, path, method, headers },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () =>
          resolve({
            status: response.statusCode,
            headers: response.headers,
            body: Buffer.concat(chunks).toString("utf8"),
          }),
        );
      },
    );
    outgoing.on("error", reject);
    if (body) outgoing.write(body);
    outgoing.end();
  });
}

describe("local agent configuration", () => {
  test("accepts branded localhost subdomains", () => {
    assert.equal(
      validateLocalHostname("Studio.ReachCut.Localhost."),
      "studio.reachcut.localhost",
    );
  });

  test("rejects hostnames which could leave the loopback namespace", () => {
    assert.throws(
      () => validateLocalHostname("studio.reachcut.example"),
      /end with \.localhost/,
    );
    assert.throws(
      () => validateLocalHostname("bad_name.localhost"),
      /invalid DNS label/,
    );
  });

  test("validates ports and command overrides", () => {
    assert.equal(parsePort("47321", "PORT"), 47_321);
    assert.throws(() => parsePort("0", "PORT"), /between 1 and 65535/);
    assert.deepEqual(
      parseCommand('["backend","--port","{apiPort}"]', "COMMAND", {
        apiPort: 48_100,
      }),
      ["backend", "--port", "48100"],
    );
    assert.throws(
      () => parseCommand('"backend"', "COMMAND"),
      /non-empty JSON array/,
    );
  });

  test("uses each operating system's user data convention", () => {
    assert.equal(
      resolveUserDataDir("win32", {
        LOCALAPPDATA: "C:\\Users\\me\\AppData\\Local",
      }),
      "C:\\Users\\me\\AppData\\Local\\ReachCut",
    );
    assert.equal(
      resolveUserDataDir("darwin", {}, "/Users/me"),
      "/Users/me/Library/Application Support/ReachCut",
    );
    assert.equal(
      resolveUserDataDir("linux", { XDG_DATA_HOME: "/data" }, "/home/me"),
      "/data/reachcut",
    );
    assert.equal(
      resolveUserDataDir("linux", {}, "/home/me"),
      "/home/me/.local/share/reachcut",
    );
    assert.equal(
      resolveUserDataDir("darwin", {}, "/Users/me", "ReachCut Personal"),
      "/Users/me/Library/Application Support/ReachCut Personal",
    );
    assert.equal(
      resolveUserDataDir(
        "linux",
        { XDG_DATA_HOME: "/data" },
        "/home/me",
        "reachcut-personal",
      ),
      "/data/reachcut-personal",
    );
  });

  test("stores the running-agent activation secret in a private profile file", () => {
    const directory = mkdtempSync(path.join(os.tmpdir(), "reachcut-agent-"));
    const statePath = path.join(directory, "agent-activation.json");
    const activationToken = "a".repeat(43);
    try {
      writeActivationState(statePath, {
        publicHostname: "studio.personal.reachcut.localhost",
        publicPort: 47_331,
        activationToken,
      });
      if (process.platform !== "win32") {
        assert.equal(statSync(statePath).mode & 0o777, 0o600);
      }
      assert.deepEqual(
        readActivationState(
          statePath,
          "studio.personal.reachcut.localhost",
          47_331,
        ),
        {
          schemaVersion: 1,
          hostname: "studio.personal.reachcut.localhost",
          port: 47_331,
          token: activationToken,
        },
      );
      assert.throws(
        () =>
          readActivationState(statePath, "studio.reachcut.localhost", 47_321),
        /another profile/,
      );
      removeActivationState(statePath, "wrong-token".repeat(4));
      assert.match(readFileSync(statePath, "utf8"), /schemaVersion/);
      removeActivationState(statePath, activationToken);
      assert.throws(() => readFileSync(statePath, "utf8"), /ENOENT/);
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
});

describe("authenticated local gateway", () => {
  const publicHostname = "studio.reachcut.localhost";
  const apiToken = "internal-api-secret";
  const activationToken = "launcher-activation-secret";
  const bootstrapToken = "one-time-bootstrap";
  const sessionToken = "browser-session";
  let apiServer;
  let webServer;
  let gateway;
  let apiPort;
  let webPort;
  let gatewayPort;
  let authority;
  let origin;

  before(async () => {
    apiServer = http.createServer((incoming, response) => {
      const chunks = [];
      incoming.on("data", (chunk) => chunks.push(chunk));
      incoming.on("end", () => {
        response.setHeader("Content-Type", "application/json");
        response.end(
          JSON.stringify({
            agentToken: incoming.headers["x-reachcut-agent-token"],
            cookie: incoming.headers.cookie ?? null,
            body: Buffer.concat(chunks).toString("utf8"),
          }),
        );
      });
    });
    webServer = http.createServer((_incoming, response) => {
      response.setHeader("Content-Type", "text/html");
      response.end("<h1>ReachCut</h1>");
    });
    apiPort = await listen(apiServer);
    webPort = await listen(webServer);
    gateway = createGateway({
      publicHostname,
      publicPort: null,
      apiPort,
      webPort,
      apiToken,
      activationToken,
      bootstrapToken,
      sessionToken,
    });
    gatewayPort = await listen(gateway.server);
    authority = `${publicHostname}:${gatewayPort}`;
    origin = `http://${authority}`;
  });

  after(async () => {
    await Promise.all([
      close(gateway.server),
      close(apiServer),
      close(webServer),
    ]);
  });

  test("rejects an unexpected Host header", async () => {
    const response = await request({
      port: gatewayPort,
      headers: { Host: "127.0.0.1" },
    });
    assert.equal(response.status, 421);
  });

  test("detects an existing local agent without a browser session", async () => {
    assert.equal(await gatewayIsRunning(publicHostname, gatewayPort), true);
  });

  test("requires a browser session for application routes", async () => {
    const response = await request({
      port: gatewayPort,
      headers: { Host: authority },
    });
    assert.equal(response.status, 401);
    assert.match(response.body, /application shortcut/);
  });

  test("exchanges the fragment bootstrap secret once and sets an HttpOnly cookie", async () => {
    const page = await request({
      port: gatewayPort,
      path: "/__reachcut/bootstrap",
      headers: { Host: authority },
    });
    assert.equal(page.status, 200);
    assert.doesNotMatch(page.body, new RegExp(bootstrapToken));

    const exchange = await request({
      port: gatewayPort,
      path: "/__reachcut/session",
      method: "POST",
      headers: {
        Host: authority,
        Origin: origin,
        "X-ReachCut-Bootstrap": bootstrapToken,
      },
    });
    assert.equal(exchange.status, 204);
    assert.match(exchange.headers["set-cookie"][0], /HttpOnly/);
    assert.match(exchange.headers["set-cookie"][0], /SameSite=Strict/);

    const replay = await request({
      port: gatewayPort,
      path: "/__reachcut/session",
      method: "POST",
      headers: {
        Host: authority,
        Origin: origin,
        "X-ReachCut-Bootstrap": bootstrapToken,
      },
    });
    assert.equal(replay.status, 401);
  });

  test("issues a fresh one-time browser URL to an authenticated second launch", async () => {
    await assert.rejects(
      requestGatewayActivation(
        publicHostname,
        gatewayPort,
        "wrong-activation-secret",
      ),
      /rejected activation/,
    );

    const firstUrl = await requestGatewayActivation(
      publicHostname,
      gatewayPort,
      activationToken,
    );
    const secondUrl = await requestGatewayActivation(
      publicHostname,
      gatewayPort,
      activationToken,
    );
    assert.notEqual(firstUrl, secondUrl);

    const url = new URL(firstUrl);
    const freshToken = new URLSearchParams(url.hash.slice(1)).get("token");
    const exchange = await request({
      port: gatewayPort,
      path: "/__reachcut/session",
      method: "POST",
      headers: {
        Host: authority,
        Origin: origin,
        "X-ReachCut-Bootstrap": freshToken,
      },
    });
    assert.equal(exchange.status, 204);

    const replay = await request({
      port: gatewayPort,
      path: "/__reachcut/session",
      method: "POST",
      headers: {
        Host: authority,
        Origin: origin,
        "X-ReachCut-Bootstrap": freshToken,
      },
    });
    assert.equal(replay.status, 401);
  });

  test("proxies authorized UI requests and adds browser security headers", async () => {
    const response = await request({
      port: gatewayPort,
      headers: {
        Host: authority,
        Cookie: `reachcut_local_session=${sessionToken}`,
      },
    });
    assert.equal(response.status, 200);
    assert.equal(response.body, "<h1>ReachCut</h1>");
    assert.equal(response.headers["x-frame-options"], "DENY");
    assert.match(
      response.headers["content-security-policy"],
      /default-src 'self'/,
    );
  });

  test("checks mutation origins and injects the private API token", async () => {
    const rejected = await request({
      port: gatewayPort,
      path: "/api/example",
      method: "POST",
      headers: {
        Host: authority,
        Cookie: `reachcut_local_session=${sessionToken}`,
      },
      body: "payload",
    });
    assert.equal(rejected.status, 403);

    const accepted = await request({
      port: gatewayPort,
      path: "/api/example",
      method: "POST",
      headers: {
        Host: authority,
        Origin: origin,
        Cookie: `reachcut_local_session=${sessionToken}`,
        "Content-Type": "text/plain",
      },
      body: "payload",
    });
    assert.equal(accepted.status, 200);
    assert.deepEqual(JSON.parse(accepted.body), {
      agentToken: apiToken,
      cookie: null,
      body: "payload",
    });
  });
});
