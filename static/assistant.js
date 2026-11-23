(() => {
  "use strict";

  let apiToken = "";
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

  function setStatus(message, error = false) {
    statusNode.textContent = message;
    statusNode.dataset.state = error ? "error" : "ok";
  }

  async function apiRequest(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Authorization", "Bearer " + apiToken);
    if (options.body) {
      headers.set("Content-Type", "application/json");
    }
    return fetch(path, { ...options, headers, credentials: "same-origin" });
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
    const response = await apiRequest("/api/tenant/session");
    if (!response.ok) {
      throw new Error(response.status === 401 ? "Token nieprawidłowy lub wygasł." : "Nie udało się sprawdzić uprawnień.");
    }
    const session = await response.json();
    sessionRoles = Array.isArray(session.roles) ? session.roles : [];
    accountPanel.hidden = !sessionRoles.includes("admin");
    if (sessionRoles.includes("admin")) {
      try {
        await loadCredentials();
      } catch (error) {
        addMessage("assistant", error.message || "Panel zarządzania dostępami jest niedostępny.");
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
    if (!apiToken || !window.confirm("Rotować ten token? Poprzedni zostanie natychmiast unieważniony.")) return;
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
    }
  }

  async function revokeCredential(credentialId) {
    if (!apiToken || !window.confirm("Unieważnić ten token? Tej operacji nie można cofnąć.")) return;
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
    const candidate = tokenInput.value.trim();
    if (!candidate) return;
    connectButton.disabled = true;
    setStatus("Sprawdzam dostęp…");
    sessionGeneration += 1;
    const generation = sessionGeneration;
    apiToken = candidate;
    try {
      await loadSession();
      if (generation !== sessionGeneration) return;
      await loadDocuments();
      if (generation !== sessionGeneration) return;
      tokenInput.value = "";
      workspace.hidden = false;
      logoutButton.hidden = false;
      sendButton.disabled = false;
      setStatus("Połączono. Token jest przechowywany tylko w pamięci karty.");
      questionInput.focus();
    } catch (error) {
      if (generation !== sessionGeneration) return;
      apiToken = "";
      setStatus(error.message || "Nie udało się połączyć.", true);
    } finally {
      connectButton.disabled = false;
    }
  });

  logoutButton.addEventListener("click", () => {
    sessionGeneration += 1;
    apiToken = "";
    workspace.hidden = true;
    logoutButton.hidden = true;
    accountPanel.hidden = true;
    sessionRoles = [];
    credentialList.replaceChildren();
    showIssuedToken("");
    copyTokenButton.textContent = "Kopiuj token";
    sendButton.disabled = true;
    messages.replaceChildren();
    addMessage("assistant", "Sesja została zakończona. Strona odrzuciła referencję do tokena.");
    setStatus("Rozłączono.");
    tokenInput.focus();
  });

  credentialForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!apiToken || !sessionRoles.includes("admin")) return;
    const subject = credentialSubject.value.trim();
    if (!subject) return;
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
      if (generation === sessionGeneration) button.disabled = false;
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
    if (!apiToken || !question) return;
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
})();
