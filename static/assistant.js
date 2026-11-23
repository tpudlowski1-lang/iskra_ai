(() => {
  "use strict";

  let apiToken = "";
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

  function setStatus(message, error = false) {
    statusNode.textContent = message;
    statusNode.dataset.state = error ? "error" : "ok";
  }

  async function apiRequest(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Authorization", "Bearer " + apiToken);
    if (options.body && !(options.body instanceof FormData)) {
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

  async function loadDocuments() {
    const response = await apiRequest("/api/tenant/documents");
    if (!response.ok) {
      throw new Error(response.status === 401 ? "Token nieprawidłowy lub wygasł." : "Nie udało się pobrać listy dokumentów.");
    }
    const data = await response.json();
    const documents = Array.isArray(data.documents) ? data.documents : [];
    documentList.replaceChildren();
    documents.forEach((document) => {
      const item = document.createElement("li");
      item.textContent = String(document.filename || "Dokument");
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
    apiToken = candidate;
    try {
      await loadDocuments();
      tokenInput.value = "";
      workspace.hidden = false;
      logoutButton.hidden = false;
      sendButton.disabled = false;
      setStatus("Połączono. Token jest przechowywany tylko w pamięci karty.");
      questionInput.focus();
    } catch (error) {
      apiToken = "";
      setStatus(error.message || "Nie udało się połączyć.", true);
    } finally {
      connectButton.disabled = false;
    }
  });

  logoutButton.addEventListener("click", () => {
    apiToken = "";
    workspace.hidden = true;
    logoutButton.hidden = true;
    sendButton.disabled = true;
    messages.replaceChildren();
    addMessage("assistant", "Sesja została zakończona. Token nie jest już przechowywany w pamięci strony.");
    setStatus("Rozłączono.");
    tokenInput.focus();
  });

  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = questionInput.value.trim();
    if (!apiToken || !question) return;
    sendButton.disabled = true;
    addMessage("user", question);
    questionInput.value = "";
    try {
      const response = await apiRequest("/api/tenant/chat", {
        method: "POST",
        body: JSON.stringify({ question }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) throw new Error("Sesja wygasła lub token jest nieprawidłowy. Połącz się ponownie.");
      if (response.status === 503) throw new Error("Usługa wnioskowania lub dokumentów jest niedostępna. Sprawdź konfigurację dostawcy i bazę wiedzy.");
      if (response.status === 502) throw new Error("Model zwrócił odpowiedź bez poprawnych cytowań. Spróbuj sformułować pytanie inaczej.");
      if (!response.ok) throw new Error("Nie udało się uzyskać odpowiedzi (" + response.status + ").");
      addMessage("assistant", data.answer || "Brak odpowiedzi.", data.citations || []);
    } catch (error) {
      addMessage("assistant", error.message || "Wystąpił błąd połączenia.");
    } finally {
      sendButton.disabled = false;
      questionInput.focus();
    }
  });
})();
