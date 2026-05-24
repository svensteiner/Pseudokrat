/*
 * Pseudokrat Outlook Add-in — Taskpane-Logik.
 *
 * Zwei Modi:
 *   - Compose: anonymisiert / deanonymisiert den E-Mail-Entwurf via
 *     Office.context.mailbox.item.body.getAsync / setAsync.
 *   - Read: liest die geöffnete E-Mail, deanonymisiert lokal und zeigt
 *     den Klartext in der Taskpane an (Schreibzugriff auf empfangene
 *     Mails ist nicht zulässig — Read-Form-API erlaubt nur Lesen).
 *
 * Backend: 127.0.0.1:31337 (pseudokrat server start), Bearer-Token.
 */

import "./taskpane.css";

interface AnonymizeRequest {
  texts: string[];
  profile: string;
}

interface AnonymizeResponse {
  results: { input: string; output: string }[];
}

type Op = "anonymize" | "deanonymize";

const BACKEND_URL = "https://127.0.0.1:31337";
const STORAGE_TOKEN_KEY = "pseudokrat:bearer";
const STORAGE_PROFILE_KEY = "pseudokrat:profile";

Office.onReady((info) => {
  if (info.host !== Office.HostType.Outlook) {
    setBackendState(`Falscher Host: ${info.host}`, "error");
    return;
  }
  bootstrap().catch((err) => {
    setBackendState(`Initialisierung fehlgeschlagen: ${describe(err)}`, "error");
  });
});

async function bootstrap(): Promise<void> {
  const profileInput = document.getElementById("profile-name") as HTMLInputElement;
  profileInput.value = localStorage.getItem(STORAGE_PROFILE_KEY) ?? "default";
  profileInput.addEventListener("change", () => {
    localStorage.setItem(STORAGE_PROFILE_KEY, profileInput.value);
  });

  const item = Office.context.mailbox.item;
  if (!item) {
    setMode("none");
    log("Kein E-Mail-Item geöffnet.", "warn");
    return;
  }

  // Compose-Form-Items haben setAsync auf body. Read-Form-Items haben das nicht.
  const isCompose = typeof (item.body as Office.Body).setAsync === "function";
  setMode(isCompose ? "compose" : "read");

  if (isCompose) {
    document
      .getElementById("anonymize-compose")!
      .addEventListener("click", () => runCompose("anonymize"));
    document
      .getElementById("deanonymize-compose")!
      .addEventListener("click", () => runCompose("deanonymize"));
  } else {
    document
      .getElementById("deanonymize-read")!
      .addEventListener("click", () => runRead());
  }

  await checkBackend();
}

function setMode(mode: "compose" | "read" | "none"): void {
  const label = document.getElementById("mode-label");
  if (label) {
    label.textContent =
      mode === "compose" ? "Verfassen" : mode === "read" ? "Lesen" : "—";
  }
  const compose = document.getElementById("compose-actions");
  const read = document.getElementById("read-actions");
  if (compose) compose.hidden = mode !== "compose";
  if (read) read.hidden = mode !== "read";
}

async function checkBackend(): Promise<void> {
  try {
    const res = await fetch(`${BACKEND_URL}/health`, {
      method: "GET",
      headers: authHeaders(),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = (await res.json()) as { version: string; profiles: string[] };
    setBackendState(
      `OK — Pseudokrat v${body.version}, ${body.profiles.length} Profil(e)`,
      "ok"
    );
  } catch (err) {
    setBackendState(
      `Backend nicht erreichbar (${describe(err)}). Starten mit:  pseudokrat server start --port 31337`,
      "error"
    );
  }
}

function getBodyAsync(item: Office.MessageCompose | Office.MessageRead): Promise<string> {
  return new Promise((resolve, reject) => {
    item.body.getAsync(Office.CoercionType.Text, (result) => {
      if (result.status === Office.AsyncResultStatus.Succeeded) {
        resolve(result.value);
      } else {
        reject(new Error(result.error?.message ?? "getAsync fehlgeschlagen"));
      }
    });
  });
}

function setBodyAsync(item: Office.MessageCompose, content: string): Promise<void> {
  return new Promise((resolve, reject) => {
    item.body.setAsync(
      content,
      { coercionType: Office.CoercionType.Text },
      (result) => {
        if (result.status === Office.AsyncResultStatus.Succeeded) {
          resolve();
        } else {
          reject(new Error(result.error?.message ?? "setAsync fehlgeschlagen"));
        }
      }
    );
  });
}

async function runCompose(op: Op): Promise<void> {
  const profile = (document.getElementById("profile-name") as HTMLInputElement).value;
  if (!profile) {
    log("Bitte zuerst ein Profil eintragen.", "warn");
    return;
  }
  const item = Office.context.mailbox.item as Office.MessageCompose;
  try {
    const original = await getBodyAsync(item);
    if (!original || original.trim().length === 0) {
      log("Mail-Entwurf ist leer.", "warn");
      return;
    }
    const response = await callBackend(op, { texts: [original], profile });
    const replacement = response.results[0]?.output ?? original;
    await setBodyAsync(item, replacement);
    log(`${op}: ${original.length} Zeichen verarbeitet.`, "ok");
  } catch (err) {
    log(`${op} fehlgeschlagen: ${describe(err)}`, "error");
  }
}

async function runRead(): Promise<void> {
  const profile = (document.getElementById("profile-name") as HTMLInputElement).value;
  if (!profile) {
    log("Bitte zuerst ein Profil eintragen.", "warn");
    return;
  }
  const item = Office.context.mailbox.item as Office.MessageRead;
  try {
    const original = await getBodyAsync(item);
    if (!original || original.trim().length === 0) {
      log("Mail-Inhalt ist leer.", "warn");
      return;
    }
    const response = await callBackend("deanonymize", { texts: [original], profile });
    const result = response.results[0]?.output ?? original;
    const output = document.getElementById("read-output");
    const body = document.getElementById("read-output-body");
    if (output && body) {
      body.textContent = result;
      output.hidden = false;
    }
    log(`Deanonymisiert: ${original.length} Zeichen — Ergebnis unten.`, "ok");
  } catch (err) {
    log(`Deanonymisieren fehlgeschlagen: ${describe(err)}`, "error");
  }
}

async function callBackend(op: Op, body: AnonymizeRequest): Promise<AnonymizeResponse> {
  const res = await fetch(`${BACKEND_URL}/v1/${op}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as AnonymizeResponse;
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem(STORAGE_TOKEN_KEY) ?? "";
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function setBackendState(text: string, kind: "ok" | "error"): void {
  const el = document.getElementById("backend-state");
  if (!el) return;
  el.textContent = text;
  el.classList.remove("status-ok", "status-error");
  el.classList.add(kind === "ok" ? "status-ok" : "status-error");
}

function log(message: string, kind: "ok" | "warn" | "error"): void {
  const list = document.getElementById("log-list") as HTMLOListElement;
  const li = document.createElement("li");
  li.textContent = `${new Date().toLocaleTimeString()} — ${message}`;
  li.dataset.kind = kind;
  list.prepend(li);
}

function describe(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}
