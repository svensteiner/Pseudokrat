/*
 * Pseudokrat Excel Add-in — Taskpane-Logik.
 *
 * Ruft das lokale Pseudokrat-HTTP-Backend (127.0.0.1:31337) auf, lässt
 * markierte Zellen anonymisieren oder deanonymisieren und schreibt das
 * Ergebnis zurück. Authentifizierung erfolgt über einen Bearer-Token,
 * der beim Backend-Start ausgegeben wurde (siehe pseudokrat.server).
 */

import "./taskpane.css";

interface AnonymizeRequest {
  texts: string[];
  profile: string;
}

interface AnonymizeResponse {
  results: { input: string; output: string }[];
}

const BACKEND_URL = "https://127.0.0.1:31337";
const STORAGE_TOKEN_KEY = "pseudokrat:bearer";
const STORAGE_PROFILE_KEY = "pseudokrat:profile";

Office.onReady((info) => {
  if (info.host !== Office.HostType.Excel) {
    setBackendState(`Falscher Host: ${info.host}`, "error");
    return;
  }
  bootstrap().catch((err) => {
    console.error(err);
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
    .addEventListener("click", () => runOnSelection("anonymize"));
  document
    .getElementById("deanonymize-selection")!
    .addEventListener("click", () => runOnSelection("deanonymize"));

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

async function runOnSelection(op: "anonymize" | "deanonymize"): Promise<void> {
  const profile = (document.getElementById("profile-name") as HTMLInputElement).value;
  if (!profile) {
    log("Bitte zuerst ein Profil eintragen.", "warn");
    return;
  }

  try {
    await Excel.run(async (context) => {
      const range = context.workbook.getSelectedRange();
      range.load(["values", "rowCount", "columnCount"]);
      await context.sync();

      const flat: { row: number; col: number; text: string }[] = [];
      const values = range.values as unknown[][];
      for (let r = 0; r < values.length; r++) {
        for (let c = 0; c < values[r].length; c++) {
          const v = values[r][c];
          if (typeof v === "string" && v.length > 0) {
            flat.push({ row: r, col: c, text: v });
          }
        }
      }

      if (flat.length === 0) {
        log("Keine String-Zellen in der Auswahl gefunden.", "warn");
        return;
      }

      const response = await callBackend(op, {
        texts: flat.map((e) => e.text),
        profile,
      });

      const updated = values.map((row) => row.slice());
      for (let i = 0; i < flat.length; i++) {
        const entry = flat[i];
        updated[entry.row][entry.col] = response.results[i].output;
      }
      range.values = updated as Excel.RangeValues;
      await context.sync();
      log(`${op}: ${flat.length} Zelle(n) verarbeitet.`, "ok");
    });
  } catch (err) {
    log(`${op} fehlgeschlagen: ${describe(err)}`, "error");
  }
}

async function callBackend(
  op: "anonymize" | "deanonymize",
  body: AnonymizeRequest
): Promise<AnonymizeResponse> {
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
