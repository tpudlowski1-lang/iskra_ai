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

function harness(apiRequest) {
  const sandbox = {
    sessionGeneration: 1,
    sessionRoles: [],
    accountPanel: { hidden: true },
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

async function staleFetchResponseCannotChangeSession() {
  const fetchResult = deferred();
  let jsonCalls = 0;
  const context = harness(() => fetchResult.promise);

  const pending = context.loadSessionUnderTest();
  context.sessionGeneration = 2;
  fetchResult.resolve({
    ok: true,
    json: async () => {
      jsonCalls += 1;
      return { roles: ["admin"] };
    },
  });

  await pending;
  assert.deepEqual(Array.from(context.sessionRoles), []);
  assert.equal(context.accountPanel.hidden, true);
  assert.equal(context.loadCredentialsCalls, 0);
  assert.equal(jsonCalls, 0);
}

async function staleJsonResponseCannotChangeSession() {
  const jsonResult = deferred();
  let jsonStarted = false;
  const context = harness(() =>
    Promise.resolve({
      ok: true,
      json: () => {
        jsonStarted = true;
        return jsonResult.promise;
      },
    })
  );

  const pending = context.loadSessionUnderTest();
  await Promise.resolve();
  assert.equal(jsonStarted, true, "test must pause after response.json() starts");

  context.sessionGeneration = 2;
  jsonResult.resolve({ roles: ["admin"] });
  await pending;

  assert.deepEqual(Array.from(context.sessionRoles), []);
  assert.equal(context.accountPanel.hidden, true);
  assert.equal(context.loadCredentialsCalls, 0);
}

(async () => {
  await staleFetchResponseCannotChangeSession();
  await staleJsonResponseCannotChangeSession();
  process.stdout.write("assistant session race regression: PASS (2 cases)\n");
})().catch((error) => {
  process.stderr.write(String(error && error.stack || error) + "\n");
  process.exitCode = 1;
});
