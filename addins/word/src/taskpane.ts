/*
 * Pseudokrat Word Add-in — Taskpane-Logik.
 *
 * Ruft das lokale Pseudokrat-HTTP-Backend (127.0.0.1:31337) auf, lässt
 * den aktuell markierten Bereich (oder das gesamte Dokument) anonymisieren
 * oder deanonymisieren und schreibt das Ergebnis zurück. Authentifizierung
 * erfolgt über einen Bearer-Token, der beim Backend-Start ausgegeben
 * wurde (siehe pseudokrat.server).
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
type Scope = "selection" | "document";

const BACKEND_URL = "https://127.0.0.1:31337";
const STORAGE_TOKEN_KEY = "pseudokrat:bearer";
const STORAGE_PROFILE_KEY = "pseudokrat:profile";

Office.onReady((info) => {
  if (info.host !== Office.HostType.Word) {
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

  document
    .getElementById("anonymize-selection")!
    .addEventListener("click", () => run("anonymize", "selection"));
  document
    .getElementById("deanonymize-selection")!
    .addEventListener("click", () => run("deanonymize", "selection"));
  document
    .getElementById("anonymize-document")!
    .addEventListener("click", () => run("anonymize", "document"));
  document
    .getElementById("deanonymize-document")!
    .addEventListener("click", () => run("deanonymize", "document"));

  await checkBackend();
}

async function checkBackend(): Promise<void> {
  try {
    const res = await fetch(`${BACKEND_URL}/health`, {
      method: "GET",
      headers: authHeaders(),
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const body = (await res.json()) as { version: string; profiles: string[] };
    setBackendState(`OK — Pseudokrat v${body.version}, ${body.profiles.length} Profil(e)`, "ok");
  } catch (err) {
    setBackendState(
      `Backend nicht erreichbar (${describe(err)}). Starten mit:  pseudokrat server start --port 31337`,
      "error"
    );
  }
}

async function run(op: Op, scope: Scope): Promise<void> {
  const profile = (document.getElementById("profile-name") as HTMLInputElement).value;
  if (!profile) {
    log("Bitte zuerst ein Profil eintragen.", "warn");
    return;
  }

  try {
    await Word.run(async (context) => {
      const range = scope === "selection"
        ? context.document.getSelection()
        : context.document.body.getRange();
      range.load("text");
      await context.sync();

      const original = range.text;
      if (!original || original.trim().length === 0) {
        log(scope === "selection"
          ? "Keine Auswahl oder Auswahl ist leer."
          : "Dokument ist leer.", "warn");
        return;
      }

      const response = await callBackend(op, {
        texts: [original],
        profile,
      });
      const replacement = response.results[0]?.output ?? original;
      // insertText mit "Replace" ersetzt den gesamten Bereich verlustfrei in einem Schritt.
      range.insertText(replacement, Word.InsertLocation.replace);
      await context.sync();
      log(`${op} (${scope}): ${original.length} Zeichen verarbeitet.`, "ok");
    });
  } catch (err) {
    log(`${op} fehlgeschlagen: ${describe(err)}`, "error");
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
