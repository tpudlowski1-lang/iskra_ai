"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("static/assistant.js", "utf8");
const start = source.indexOf("  function setCredentialMutationPending(pending) {");
const end = source.indexOf("\n  function setStatus(", start);
assert.notEqual(start, -1, "credential mutation lock must exist");
assert.notEqual(end, -1, "credential mutation lock block must be complete");

const controls = {
  connect: { disabled: false },
  token: { disabled: false },
  logout: { disabled: false },
  form: [{ disabled: false }, { disabled: false }],
  list: [{ disabled: false }],
};
const sandbox = {
  credentialMutationPending: false,
  connectButton: controls.connect,
  tokenInput: controls.token,
  logoutButton: controls.logout,
  credentialForm: { querySelectorAll: () => controls.form },
  credentialList: { querySelectorAll: () => controls.list },
};
const context = vm.createContext(sandbox);
new vm.Script(
  source.slice(start, end) +
  "\n;globalThis.beginMutation = beginCredentialMutation;" +
  "\n;globalThis.endMutation = endCredentialMutation;"
).runInContext(context);

assert.equal(context.beginMutation(), true);
for (const control of [controls.connect, controls.token, controls.logout, ...controls.form, ...controls.list]) {
  assert.equal(control.disabled, true, "session switching and concurrent credential actions must be locked");
}
assert.equal(context.beginMutation(), false, "a second credential mutation must not start concurrently");
context.endMutation();
for (const control of [controls.connect, controls.token, controls.logout, ...controls.form, ...controls.list]) {
  assert.equal(control.disabled, false, "controls must be restored after mutation completion");
}

// Session switching must clear the prior tenant's sensitive UI state before assigning the new token.
const connectStart = source.indexOf('connectForm.addEventListener("submit"');
const connectEnd = source.indexOf('\n  logoutButton.addEventListener', connectStart);
const connectHandler = source.slice(connectStart, connectEnd);
assert.ok(connectHandler.indexOf("credentialList.replaceChildren()") < connectHandler.indexOf("apiToken = candidate"));
assert.ok(connectHandler.indexOf('showIssuedToken("")') < connectHandler.indexOf("apiToken = candidate"));
assert.ok(connectHandler.indexOf("documentList.replaceChildren()") < connectHandler.indexOf("apiToken = candidate"));
assert.ok(connectHandler.includes("workspace.hidden = true"));

const logoutStart = source.indexOf('logoutButton.addEventListener("click"');
const logoutHandler = source.slice(logoutStart, source.indexOf('\n  credentialForm.addEventListener', logoutStart));
assert.ok(logoutHandler.includes("if (credentialMutationPending) return;"));

const issueStart = source.indexOf('credentialForm.addEventListener("submit"');
const issueHandler = source.slice(issueStart, source.indexOf('\n  copyTokenButton.addEventListener', issueStart));
assert.ok(issueHandler.includes("button.disabled = false;"), "issue button must be restored even after generation changes");
assert.ok(issueHandler.includes("endCredentialMutation();"));

process.stdout.write("assistant tenant admin mutation/session regression: PASS\n");
