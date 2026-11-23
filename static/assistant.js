(() => {
  "use strict";

  let csrfToken = "";
  let sessionGeneration = 0;
  const connectForm = document.getElementById("connect-form");
  const tokenInput = document.getElementById("api-token");
  const connectButton = document.getElementById("connect-button");
  const logoutButton = document.getElementById("logout-button");
  const statusNode = document.getElementById("connection-status");
  const workspace = document.getElementById("workspace");
  const documentList = document.getElementById("document-list");
  const documentCount = document.getElementById("document-count");
  const messages = document.getElementById("messages");
  const chatForm = document.getElementById("chat-form");
  const questionInput = document.getElementById("question");
  const sendButton = document.getElementById("send-button");
  const accountPanel = document.getElementById("account-panel");
  const credentialForm = document.getElementById("credential-form");
  const credentialSubject = document.getElementById("credential-subject");
  const credentialRole = document.getElementById("credential-role");
  const credentialList = document.getElementById("credential-list");
  const issuedTokenPanel = document.getElementById("issued-token-panel");
  const issuedToken = document.getElementById("issued-token");
  const copyTokenButton = document.getElementById("copy-token");
  let sessionRoles = [];
  let credentialMutationPending = false;

  function setCredentialMutationPending(pending) {
    credentialMutationPending = pending;
    connectButton.disabled = pending;
    tokenInput.disabled = pending;
    logoutButton.disabled = pending;
    credentialForm.querySelectorAll("button, input, select").forEach((control) => {
      control.disabled = pending;
    });
    credentialList.querySelectorAll("button").forEach((control) => {
      control.disabled = pending;
    });
  }

  function beginCredentialMutation() {
    if (credentialMutationPending) return false;
    setCredentialMutationPending(true);
    return true;
  }

  function endCredentialMutation() {
    if (credentialMutationPending) setCredentialMutationPending(false);
  }

  function setStatus(message, error = false) {
    statusNode.textContent = message;
    statusNode.dataset.state = error ? "error" : "ok";
  }

  async function apiRequest(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const method = String(options.method || "GET").toUpperCase();
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken) headers.set("X-CSRF-Token", csrfToken);
    return fetch(path, { ...options, headers, credentials: "same-origin", cache: "no-store" });
  }

  function addMessage(role, text, citations = []) {
    const article = document.createElement("article");
    article.className = "message " + (role === "user" ? "user-message" : "assistant-message");

    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent = role === "user" ? "TY" : "ISKRA";

    const paragraph = document.createElement("p");
    paragraph.textContent = String(text || "");

    article.append(label, paragraph);

    if (Array.isArray(citations) && citations.length) {
      const list = document.createElement("ul");
      list.className = "citations";
      citations.forEach((citation) => {
        const item = document.createElement("li");
        const name = document.createElement("strong");
        name.textContent = String(citation.filename || "Dokument");
        const location = document.createElement("span");
        location.textContent = "fragment " + String(citation.chunk_index ?? "—");
        item.append(name, location);
        list.append(item);
      });
      article.append(list);
    }

    messages.append(article);
    messages.scrollTop = messages.scrollHeight;
  }

  async function loadSession() {
    const generation = sessionGeneration;
    const bootstrapResponse = await fetch("/api/browser/session", { credentials: "same-origin", cache: "no-store" });
    if (generation !== sessionGeneration) return;
    if (!bootstrapResponse.ok) {
      throw new Error(bootstrapResponse.status === 401
        ? "Sesja wygasła lub nie jest aktywna. Wprowadź ponownie token dostępu."
        : "Nie udało się odnowić sesji przeglądarki.");
    }
    const bootstrap = await bootstrapResponse.json();
    if (generation !== sessionGeneration) return;
    csrfToken = String(bootstrap.csrf_token || "");
    if (!csrfToken) throw new Error("Serwer nie zwrócił tokenu CSRF.");
    const response = await apiRequest("/api/tenant/session");
    if (generation !== sessionGeneration) return;
    if (!response.ok) {
      throw new Error(response.status === 401 ? "Sesja wygasła lub token został unieważniony." : "Nie udało się sprawdzić uprawnień.");
    }
    const session = await response.json();
    if (generation !== sessionGeneration) return;
    sessionRoles = Array.isArray(session.roles) ? session.roles : [];
    accountPanel.hidden = !sessionRoles.includes("admin");
    if (sessionRoles.includes("admin")) {
      try {
        await loadCredentials();
      } catch (error) {
        if (generation === sessionGeneration) {
          addMessage("assistant", error.message || "Panel zarządzania dostępami jest niedostępny.");
        }
      }
    }
  }

  async function loadCredentials() {
    const generation = sessionGeneration;
    const response = await apiRequest("/api/tenant/credentials");
    if (!response.ok) throw new Error("Nie udało się pobrać listy dostępów.");
    const data = await response.json();
    if (generation !== sessionGeneration) return;
    credentialList.replaceChildren();
    (Array.isArray(data.credentials) ? data.credentials : []).forEach((credential) => {
      const item = document.createElement("li");
      item.className = "credential-item";
      const detail = document.createElement("span");
      detail.textContent = String(credential.subject || "Użytkownik") + " · " +
        (Array.isArray(credential.roles) ? credential.roles.join(", ") : "") +
        (credential.active ? " · aktywny" : " · nieaktywny");
      item.append(detail);
      if (credential.active) {
        const actions = document.createElement("div");
        actions.className = "credential-actions";
        const rotate = document.createElement("button");
        rotate.type = "button";
        rotate.className = "quiet-button";
        rotate.textContent = "Rotuj";
        rotate.addEventListener("click", () => rotateCredential(credential.credential_id));
        const revoke = document.createElement("button");
        revoke.type = "button";
        revoke.className = "quiet-button";
        revoke.textContent = "Unieważnij";
        revoke.addEventListener("click", () => revokeCredential(credential.credential_id));
        actions.append(rotate, revoke);
        item.append(actions);
      }
      credentialList.append(item);
    });
    if (!credentialList.children.length) {
      const empty = document.createElement("li");
      empty.className = "empty-documents";
      empty.textContent = "Brak dostępów.";
      credentialList.append(empty);
    }
  }

  function showIssuedToken(token) {
    issuedToken.value = String(token || "");
    issuedTokenPanel.hidden = !issuedToken.value;
  }

  async function rotateCredential(credentialId) {
    if (!csrfToken || !window.confirm("Rotować ten token? Poprzedni zostanie natychmiast unieważniony.")) return;
    if (!beginCredentialMutation()) return;
    const generation = sessionGeneration;
    try {
      const response = await apiRequest("/api/tenant/credentials/" + encodeURIComponent(credentialId) + "/rotate", {
        method: "POST",
        body: JSON.stringify({}),
      });
      const data = await response.json().catch(() => ({}));
      if (generation !== sessionGeneration) return;
      if (!response.ok) throw new Error("Nie udało się rotować tokenu (" + response.status + ").");
      showIssuedToken(data.token);
      try {
        await loadCredentials();
      } catch (_error) {
        setStatus("Token został obrócony. Jeśli był to bieżący token, połącz się ponownie nowym tokenem.", true);
      }
    } catch (error) {
      if (generation === sessionGeneration) addMessage("assistant", error.message || "Błąd rotacji tokenu.");
    } finally {
      endCredentialMutation();
    }
  }

  async function revokeCredential(credentialId) {
    if (!csrfToken || !window.confirm("Unieważnić ten token? Tej operacji nie można cofnąć.")) return;
    if (!beginCredentialMutation()) return;
    const generation = sessionGeneration;
    try {
      const response = await apiRequest("/api/tenant/credentials/" + encodeURIComponent(credentialId), {
        method: "DELETE",
      });
      if (generation !== sessionGeneration) return;
      if (!response.ok) throw new Error("Nie udało się unieważnić tokenu (" + response.status + ").");
      try {
        await loadCredentials();
      } catch (_error) {
        setStatus("Token unieważniony. Jeśli był to bieżący token, połącz się ponownie.", true);
      }
    } catch (error) {
      if (generation === sessionGeneration) addMessage("assistant", error.message || "Błąd unieważniania tokenu.");
    } finally {
      endCredentialMutation();
    }
  }

  async function loadDocuments() {
    const generation = sessionGeneration;
    const response = await apiRequest("/api/tenant/documents");
    if (!response.ok) {
      throw new Error(response.status === 401 ? "Token nieprawidłowy lub wygasł." : "Nie udało się pobrać listy dokumentów.");
    }
    const data = await response.json();
    if (generation !== sessionGeneration) return;
    const documents = Array.isArray(data.documents) ? data.documents : [];
    documentList.replaceChildren();
    documents.forEach((doc) => {
      const item = document.createElement("li");
      item.textContent = String(doc.filename || "Dokument");
      documentList.append(item);
    });
    documentCount.textContent = String(documents.length);
    if (!documents.length) {
      const item = document.createElement("li");
      item.className = "empty-documents";
      item.textContent = "Brak dokumentów w tej organizacji.";
      documentList.append(item);
    }
  }

  connectForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    let candidate = tokenInput.value.trim();
    if (!candidate || credentialMutationPending) return;
    tokenInput.value = "";
    connectButton.disabled = true;
    tokenInput.disabled = true;
    setStatus("Sprawdzam dostęp…");
    sessionGeneration += 1;
    const generation = sessionGeneration;
    workspace.hidden = true;
    logoutButton.hidden = true;
    accountPanel.hidden = true;
    sessionRoles = [];
    credentialList.replaceChildren();
    showIssuedToken("");
    documentList.replaceChildren();
    documentCount.textContent = "0";
    messages.replaceChildren();
    sendButton.disabled = true;
    credentialSubject.value = "";
    try {
      const loginResponse = await fetch("/api/browser/session", {
        method: "POST",
        headers: { "Authorization": "Bearer " + candidate, "Content-Type": "application/json" },
        body: JSON.stringify({}),
        credentials: "same-origin",
        cache: "no-store",
      });
      const loginData = await loginResponse.json().catch(() => ({}));
      if (!loginResponse.ok) {
        throw new Error(loginResponse.status === 403
          ? "Do logowania przez przeglądarkę wymagany jest aktywny token z trwałego rejestru."
          : "Nie udało się utworzyć bezpiecznej sesji (" + loginResponse.status + ").");
      }
      csrfToken = String(loginData.csrf_token || "");
      if (!csrfToken) throw new Error("Serwer nie zwrócił tokenu CSRF.");
      await loadSession();
      if (generation !== sessionGeneration) return;
      await loadDocuments();
      if (generation !== sessionGeneration) return;
      workspace.hidden = false;
      logoutButton.hidden = false;
      sendButton.disabled = false;
      setStatus("Połączono. Token API nie jest przechowywany; sesję chroni ciasteczko HttpOnly.");
      questionInput.focus();
    } catch (error) {
      if (generation !== sessionGeneration) return;
      if (csrfToken) {
        try {
          await fetch("/api/browser/session/logout", { method: "POST", headers: { "X-CSRF-Token": csrfToken }, credentials: "same-origin" });
        } catch (_logoutError) {
          // Server-side expiry remains the fallback if logout cannot be reached.
        }
      }
      csrfToken = "";
      setStatus(error.message || "Nie udało się połączyć.", true);
    } finally {
      candidate = "";
      tokenInput.value = "";
      connectButton.disabled = credentialMutationPending;
      tokenInput.disabled = credentialMutationPending;
    }
  });

  logoutButton.addEventListener("click", async () => {
    if (credentialMutationPending) return;
    try {
      const response = await apiRequest("/api/browser/session/logout", { method: "POST" });
      if (!response.ok) throw new Error("Serwer nie potwierdził zakończenia sesji.");
    } catch (error) {
      setStatus(error.message || "Nie udało się zakończyć sesji na serwerze.", true);
      return;
    }
    sessionGeneration += 1;
    csrfToken = "";
    workspace.hidden = true;
    logoutButton.hidden = true;
    accountPanel.hidden = true;
    sessionRoles = [];
    credentialList.replaceChildren();
    showIssuedToken("");
    copyTokenButton.textContent = "Kopiuj token";
    sendButton.disabled = true;
    messages.replaceChildren();
    addMessage("assistant", "Sesja została unieważniona na serwerze. Ciasteczko HttpOnly zostało usunięte.");
    setStatus("Rozłączono.");
    tokenInput.focus();
  });

  credentialForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!csrfToken || !sessionRoles.includes("admin") || credentialMutationPending) return;
    const subject = credentialSubject.value.trim();
    if (!subject || !beginCredentialMutation()) return;
    const generation = sessionGeneration;
    const button = document.getElementById("issue-credential");
    button.disabled = true;
    try {
      const response = await apiRequest("/api/tenant/credentials", {
        method: "POST",
        body: JSON.stringify({ subject, roles: [credentialRole.value] }),
      });
      const data = await response.json().catch(() => ({}));
      if (generation !== sessionGeneration) return;
      if (!response.ok) throw new Error("Nie udało się utworzyć dostępu (" + response.status + ").");
      showIssuedToken(data.token);
      credentialSubject.value = "";
      try {
        await loadCredentials();
      } catch (_error) {
        setStatus("Dostęp utworzony, ale lista nie odświeżyła się. Zapisz token i odśwież listę później.", true);
      }
    } catch (error) {
      if (generation === sessionGeneration) addMessage("assistant", error.message || "Błąd tworzenia dostępu.");
    } finally {
      button.disabled = false;
      endCredentialMutation();
    }
  });

  copyTokenButton.addEventListener("click", async () => {
    if (!issuedToken.value) return;
    try {
      await navigator.clipboard.writeText(issuedToken.value);
      copyTokenButton.textContent = "Skopiowano";
    } catch (_error) {
      issuedToken.focus();
      issuedToken.select();
      copyTokenButton.textContent = "Zaznaczono — skopiuj ręcznie";
    }
  });

  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = questionInput.value.trim();
    if (!csrfToken || !question) return;
    const generation = sessionGeneration;
    sendButton.disabled = true;
    addMessage("user", question);
    questionInput.value = "";
    try {
      const response = await apiRequest("/api/tenant/chat", {
        method: "POST",
        body: JSON.stringify({ question }),
      });
      const data = await response.json().catch(() => ({}));
      if (generation !== sessionGeneration) return;
      if (response.status === 401) throw new Error("Sesja wygasła lub token jest nieprawidłowy. Połącz się ponownie.");
      if (response.status === 503) throw new Error("Usługa wnioskowania lub dokumentów jest niedostępna. Sprawdź konfigurację dostawcy i bazę wiedzy.");
      if (response.status === 502) throw new Error("Model zwrócił odpowiedź bez poprawnych cytowań. Spróbuj sformułować pytanie inaczej.");
      if (!response.ok) throw new Error("Nie udało się uzyskać odpowiedzi (" + response.status + ").");
      addMessage("assistant", data.answer || "Brak odpowiedzi.", data.citations || []);
    } catch (error) {
      if (generation === sessionGeneration) {
        addMessage("assistant", error.message || "Wystąpił błąd połączenia.");
      }
    } finally {
      if (generation === sessionGeneration) {
        sendButton.disabled = false;
        questionInput.focus();
      }
    }
  });
  async function restoreBrowserSession() {
    sessionGeneration += 1;
    const generation = sessionGeneration;
    try {
      await loadSession();
      if (generation !== sessionGeneration) return;
      await loadDocuments();
      if (generation !== sessionGeneration) return;
      workspace.hidden = false;
      logoutButton.hidden = false;
      sendButton.disabled = false;
      setStatus("Przywrócono bezpieczną sesję przeglądarki.");
    } catch (_error) {
      if (generation !== sessionGeneration) return;
      csrfToken = "";
      workspace.hidden = true;
      logoutButton.hidden = true;
      accountPanel.hidden = true;
      sessionRoles = [];
      credentialList.replaceChildren();
      showIssuedToken("");
      documentList.replaceChildren();
      documentCount.textContent = "0";
      sendButton.disabled = true;
      setStatus("Brak aktywnej sesji. Wprowadź token dostępu.", false);
    }
  }

  restoreBrowserSession();
})();
