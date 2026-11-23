"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("static/assistant.js", "utf8");
const startMarker = "  async function loadSession() {";
const endMarker = "\n  async function loadCredentials() {";
const start = source.indexOf(startMarker);
const end = source.indexOf(endMarker, start);

assert.notEqual(start, -1, "loadSession() must exist");
assert.notEqual(end, -1, "loadCredentials() must follow loadSession()");

const loadSessionSource = source.slice(start, end);

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function harness(fetch, apiRequest) {
  const sandbox = {
    sessionGeneration: 1,
    sessionRoles: [],
    csrfToken: "",
    accountPanel: { hidden: true },
    fetch,
    apiRequest,
    loadCredentialsCalls: 0,
    loadCredentials: async () => {
      sandbox.loadCredentialsCalls += 1;
    },
    addMessage: () => {},
  };
  const context = vm.createContext(sandbox);
  new vm.Script(
    loadSessionSource + "\n;globalThis.loadSessionUnderTest = loadSession;"
  ).runInContext(context);
  return context;
}

function assertSessionUnchanged(context) {
  assert.deepEqual(Array.from(context.sessionRoles), []);
  assert.equal(context.accountPanel.hidden, true);
  assert.equal(context.loadCredentialsCalls, 0);
}

async function staleBootstrapFetchResponseCannotChangeSession() {
  const fetchResult = deferred();
  let jsonCalls = 0;
  let apiCalls = 0;
  const context = harness(
    () => fetchResult.promise,
    async () => {
      apiCalls += 1;
      throw new Error("tenant API must not be called for stale bootstrap");
    }
  );

  const pending = context.loadSessionUnderTest();
  context.sessionGeneration = 2;
  fetchResult.resolve({
    ok: true,
    json: async () => {
      jsonCalls += 1;
      return { csrf_token: "csrf" };
    },
  });

  await pending;
  assertSessionUnchanged(context);
  assert.equal(jsonCalls, 0);
  assert.equal(apiCalls, 0);
}

async function staleBootstrapJsonResponseCannotChangeSession() {
  const jsonResult = deferred();
  let markJsonStarted;
  const jsonStarted = new Promise((resolve) => {
    markJsonStarted = resolve;
  });
  let apiCalls = 0;
  const context = harness(
    async () => ({
      ok: true,
      json: () => {
        markJsonStarted();
        return jsonResult.promise;
      },
    }),
    async () => {
      apiCalls += 1;
      throw new Error("tenant API must not be called for stale bootstrap JSON");
    }
  );

  const pending = context.loadSessionUnderTest();
  await jsonStarted;
  context.sessionGeneration = 2;
  jsonResult.resolve({ csrf_token: "csrf" });
  await pending;

  assertSessionUnchanged(context);
  assert.equal(apiCalls, 0);
}

async function staleTenantFetchResponseCannotChangeSession() {
  const tenantResponse = deferred();
  let jsonCalls = 0;
  const context = harness(
    async () => ({ ok: true, json: async () => ({ csrf_token: "csrf" }) }),
    () => tenantResponse.promise
  );

  const pending = context.loadSessionUnderTest();
  context.sessionGeneration = 2;
  tenantResponse.resolve({
    ok: true,
    json: async () => {
      jsonCalls += 1;
      return { roles: ["admin"] };
    },
  });
  await pending;

  assertSessionUnchanged(context);
  assert.equal(jsonCalls, 0);
}

async function staleTenantJsonResponseCannotChangeSession() {
  const jsonResult = deferred();
  let markJsonStarted;
  const jsonStarted = new Promise((resolve) => {
    markJsonStarted = resolve;
  });
  const context = harness(
    async () => ({ ok: true, json: async () => ({ csrf_token: "csrf" }) }),
    async () => ({
      ok: true,
      json: () => {
        markJsonStarted();
        return jsonResult.promise;
      },
    })
  );

  const pending = context.loadSessionUnderTest();
  await jsonStarted;
  context.sessionGeneration = 2;
  jsonResult.resolve({ roles: ["admin"] });
  await pending;

  assertSessionUnchanged(context);
}

(async () => {
  await staleBootstrapFetchResponseCannotChangeSession();
  await staleBootstrapJsonResponseCannotChangeSession();
  await staleTenantFetchResponseCannotChangeSession();
  await staleTenantJsonResponseCannotChangeSession();
  process.stdout.write("assistant session race regression: PASS (4 cases)\n");
})().catch((error) => {
  process.stderr.write(String(error && error.stack || error) + "\n");
  process.exitCode = 1;
});
