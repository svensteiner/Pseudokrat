"""PRL Gap-Phase: priorisiert die offenste Lücke aus Eval + Audit gegen das Gate.

Aufruf::

    python -m tools.gap_select --eval eval_report.json --audit audit_report.json
    python -m tools.gap_select --eval eval_report.json --output next_gap.md
    python -m tools.gap_select --eval eval_report.json --gate PRODUCTION_READY_GATE.md

Liest:

* ``eval_report.json`` (Format aus ``tests.eval.runner.render_report``).
* Optional ``audit_report.json`` (Format aus ``tools.audit_run.render_report``).
* ``PRODUCTION_READY_GATE.md`` für Schwellen (Tier-1 Tabelle + FP-Rate).

Schreibt einen ``next_gap.md``-Bericht mit **genau einer** priorisierten
Lücke + Liste aller weiteren. Exit 0 wenn keine Lücke offen, sonst 1.

**Bewusste Trade-Offs:**

* Wir parsen das Gate per Regex, nicht per Markdown-AST. Das Gate-Format
  ist absichtlich klein gehalten (Tier-1-Tabelle + ein Inline-Match für
  FP-Rate), Regex-Parsing ist robust genug für diese Form.
* Wir mappen Gate-Kategorien per Alias-Tabelle auf interne
  Recognizer-Namen (``ORG`` → ``COMPANY``), weil das Gate vorher als
  Vertrag mit dem Pentest/DSGVO-Adressaten formuliert wurde und seinen
  Namen behalten soll.
* ML-Pflicht-Kategorien (PERSON, ADDRESS, DATE) werden im
  Recognizers-Only-Mode **nur dann** als Lücke geflaggt, wenn sie nach
  Iter-7 nicht mehr regelbasiert abgedeckt sind (Recognizer aktuell:
  voll). Existiert ein Score im Report, gilt der Schwellwert.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GATE = REPO_ROOT / "PRODUCTION_READY_GATE.md"

#: Gate spricht von ``ORG``, der Eval-Report (und damit die Recognizer)
#: von ``COMPANY``. Die Tabelle hier ist die einzige Stelle, an der das
#: Vokabular gebrückt wird.
CATEGORY_ALIASES: dict[str, str] = {
    "ORG": "COMPANY",
}

#: Kategorien, deren Detection ML-Modell benötigen würde, falls die
#: regelbasierten Recognizer sie nicht abdecken. Aktuell deckt der
#: Recognizer-Bundle alle drei ab (PERSON Iter-6, ADDRESS Iter-7,
#: DATE Iter-5), aber wenn das Eval-Report im ``recognizers-only``-
#: Mode keine Werte liefert, sind das die Kategorien, bei denen wir das
#: nicht als harten Gate-Fail werten.
ML_DEPENDENT_CATEGORIES: frozenset[str] = frozenset({"PERSON", "ADDRESS", "DATE"})


# ---------- Datentypen ------------------------------------------------------


@dataclass(frozen=True)
class GateThreshold:
    """Eine Zeile der Tier-1-Tabelle aus dem Gate."""

    category: str  # bereits über CATEGORY_ALIASES normalisiert
    min_f1: float


@dataclass(frozen=True)
class GateSpec:
    """Vollständige Gate-Spezifikation, geladen aus PRODUCTION_READY_GATE.md."""

    thresholds: tuple[GateThreshold, ...]
    max_fp_rate: float

    def threshold_for(self, category: str) -> GateThreshold | None:
        for t in self.thresholds:
            if t.category == category:
                return t
        return None


@dataclass(frozen=True)
class Gap:
    """Eine offene Lücke gegen das Gate."""

    # Severity: 1 = Tier-1 (Erkennungs-Qualität), 2 = Globale FP-Rate,
    # 3 = Tier-2/3 (Audit). Niedriger = wichtiger.
    severity: int
    tier: str
    title: str
    detail: str
    fix_hint: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------- Gate-Parsing ----------------------------------------------------


# Match-Format: ``| `PERSON` | **0.95** | …``.
_GATE_ROW_RE = re.compile(
    r"^\|\s*`([A-Z_]+)`\s*\|\s*\*\*([0-9.]+)\*\*",
    re.MULTILINE,
)

# Match-Format: ``… `≤ 0.02` …``.
_FP_RATE_RE = re.compile(
    r"Falsch-Positiv-Rate.*?`\s*≤\s*([0-9.]+)\s*`",
    re.DOTALL,
)


def parse_gate(gate_md: str) -> GateSpec:
    """Lies Tier-1-Schwellen + FP-Rate aus dem Gate-Markdown."""
    thresholds: list[GateThreshold] = []
    seen: set[str] = set()
    for cat, val in _GATE_ROW_RE.findall(gate_md):
        canonical = CATEGORY_ALIASES.get(cat, cat)
        if canonical in seen:
            continue
        seen.add(canonical)
        thresholds.append(GateThreshold(canonical, float(val)))
    fp_match = _FP_RATE_RE.search(gate_md)
    fp_max = float(fp_match.group(1)) if fp_match else 0.02
    return GateSpec(thresholds=tuple(thresholds), max_fp_rate=fp_max)


# ---------- Gap-Identifikation ----------------------------------------------


def _fp_rate(totals: dict[str, Any]) -> float | None:
    tp = int(totals.get("tp", 0))
    fp = int(totals.get("fp", 0))
    detected = tp + fp
    if detected == 0:
        return None
    return fp / detected


def _dominant_error(score: dict[str, Any]) -> str:
    fn = int(score.get("fn", 0))
    fp = int(score.get("fp", 0))
    if fn > fp:
        return "hauptsächlich FN (Recall)"
    if fp > fn:
        return "hauptsächlich FP (Precision)"
    return "FN und FP gleich"


def identify_gaps(
    *,
    eval_report: dict[str, Any],
    audit_report: dict[str, Any] | None,
    gate: GateSpec,
) -> list[Gap]:
    """Sammle alle offenen Lücken — sortiert nach Severity (1 = wichtigster)."""
    gaps: list[Gap] = []
    per_cat = eval_report.get("per_category", {}) or {}
    mode = eval_report.get("mode", "recognizers-only")
    is_ml_mode = mode == "with-ml"

    # ----- Tier-1: pro Kategorie -----
    for th in gate.thresholds:
        score = per_cat.get(th.category)
        if score is None:
            # ML-Kategorie ohne Score im Recognizer-Only-Mode: nur warnen
            # mit Severity 3 (Phase-2-Ausstand, nicht harter Block).
            if not is_ml_mode and th.category in ML_DEPENDENT_CATEGORIES:
                gaps.append(
                    Gap(
                        severity=3,
                        tier="tier-1",
                        title=(f"{th.category} im recognizers-only-Report nicht enthalten"),
                        detail=(
                            "Kategorie braucht entweder Recognizer-Coverage oder "
                            "den ML-Pfad (`--with-ml`)."
                        ),
                        fix_hint=(
                            f"Fixture mit {th.category}-Slot anlegen oder Recognizer registrieren."
                        ),
                        metadata={"category": th.category, "min_f1": th.min_f1},
                    )
                )
                continue
            gaps.append(
                Gap(
                    severity=1,
                    tier="tier-1",
                    title=f"{th.category} fehlt im Eval-Report",
                    detail=(
                        f"Gate fordert F1 ≥ {th.min_f1}, Kategorie ist im "
                        f"`{mode}`-Report nicht enthalten."
                    ),
                    fix_hint=(
                        f"Fixture mit {th.category}-Slot anlegen oder Recognizer registrieren."
                    ),
                    metadata={"category": th.category, "min_f1": th.min_f1},
                )
            )
            continue
        f1 = float(score.get("f1", 0.0))
        if f1 < th.min_f1:
            gaps.append(
                Gap(
                    severity=1,
                    tier="tier-1",
                    title=(f"Eval-Defizit: {th.category} F1 = {f1:.2f} < {th.min_f1}"),
                    detail=(
                        f"Precision={float(score.get('precision', 0.0)):.2f}, "
                        f"Recall={float(score.get('recall', 0.0)):.2f}, "
                        f"TP={score.get('tp', 0)}, FP={score.get('fp', 0)}, "
                        f"FN={score.get('fn', 0)}."
                    ),
                    fix_hint=(
                        f"Recognizer/Detector für {th.category} härten ({_dominant_error(score)})."
                    ),
                    metadata={
                        "category": th.category,
                        "min_f1": th.min_f1,
                        "f1": f1,
                        "tp": score.get("tp"),
                        "fp": score.get("fp"),
                        "fn": score.get("fn"),
                    },
                )
            )

    # ----- Tier-1b: Globale FP-Rate -----
    totals = eval_report.get("totals", {}) or {}
    fp_rate = _fp_rate(totals)
    if fp_rate is not None and fp_rate > gate.max_fp_rate:
        gaps.append(
            Gap(
                severity=2,
                tier="tier-1",
                title=(f"FP-Rate {fp_rate:.4f} > Gate-Limit {gate.max_fp_rate}"),
                detail=(
                    f"{totals.get('fp', 0)} False Positives bei "
                    f"{int(totals.get('tp', 0)) + int(totals.get('fp', 0))} "
                    "Detections insgesamt."
                ),
                fix_hint=(
                    "Recognizer mit höchstem FP-Beitrag identifizieren "
                    "(per-category-Tabelle im Eval-Report) und Pattern "
                    "verschärfen oder Kontext-Anker einführen."
                ),
                metadata={"fp_rate": fp_rate, "limit": gate.max_fp_rate},
            )
        )

    # ----- Tier-2 / Tier-3: Audit-Checks -----
    if audit_report is not None:
        for check in audit_report.get("checks", []) or []:
            status = check.get("status", "")
            if status != "fail":
                continue
            name = check.get("name", "?")
            extra = check.get("extra") or {}
            missing = extra.get("missing") or []
            if name == "trust-boundary-coverage" and missing:
                gaps.append(
                    Gap(
                        severity=3,
                        tier="tier-3",
                        title=(f"Trust-Boundary ohne Test-Coverage: {len(missing)} offen"),
                        detail="Ungetestete Boundaries:\n  - "
                        + "\n  - ".join(str(m) for m in missing),
                        fix_hint=(
                            "Pro fehlende Boundary einen Test mit S<N>-Marker "
                            "oder Schlüsselbegriff aus dem Titel ergänzen."
                        ),
                        metadata={"missing": list(missing)},
                    )
                )
            else:
                gaps.append(
                    Gap(
                        severity=3,
                        tier="tier-2",
                        title=f"Audit-Check '{name}' fehlgeschlagen",
                        detail=(
                            (check.get("stderr_tail") or check.get("stdout_tail") or "")[:600]
                            or "Kein Stderr/Stdout im Report."
                        ),
                        fix_hint=(
                            f"Befund von `{name}` adressieren — Tool lokal "
                            "ausführen und Diff einspielen."
                        ),
                        metadata={"check": name},
                    )
                )

    gaps.sort(key=lambda g: (g.severity, g.title))
    return gaps


# ---------- Rendering -------------------------------------------------------


def render_next_gap(
    gaps: list[Gap],
    *,
    mode: str,
    gate: GateSpec,
) -> str:
    """Schreibt ein Markdown-Dokument mit der priorisierten Lücke + Liste."""
    if not gaps:
        return (
            "# Keine offenen Lücken\n\n"
            f"Alle Gate-Bedingungen im Mode `{mode}` erfüllt.\n\n"
            f"- Tier-1-Schwellen: {len(gate.thresholds)} Kategorien geprüft.\n"
            f"- FP-Rate-Limit: ≤ {gate.max_fp_rate}.\n"
        )
    top = gaps[0]
    lines: list[str] = []
    lines.append("# Nächste Lücke (PRL Gap-Phase)")
    lines.append("")
    lines.append(f"**Eval-Mode:** `{mode}`")
    lines.append(f"**Offen gesamt:** {len(gaps)}")
    lines.append(f"**Top-Severity:** {top.severity} ({top.tier})")
    lines.append("")
    lines.append(f"## {top.title}")
    lines.append("")
    lines.append(top.detail)
    lines.append("")
    lines.append(f"**Fix-Vorschlag:** {top.fix_hint}")
    if len(gaps) > 1:
        lines.append("")
        lines.append("## Weitere Lücken")
        for g in gaps[1:]:
            lines.append(f"- [{g.tier}, sev {g.severity}] {g.title}")
    lines.append("")
    return "\n".join(lines)


# ---------- CLI -------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PRL Gap-Select")
    parser.add_argument(
        "--eval",
        type=Path,
        required=True,
        help="eval_report.json (von tests.eval.runner).",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=None,
        help="audit_report.json (von tools.audit_run). Optional.",
    )
    parser.add_argument(
        "--gate",
        type=Path,
        default=DEFAULT_GATE,
        help="Pfad zu PRODUCTION_READY_GATE.md.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Pfad für next_gap.md (Default: stdout).",
    )
    args = parser.parse_args(argv)

    eval_report = json.loads(args.eval.read_text(encoding="utf-8"))
    audit_report: dict[str, Any] | None = None
    if args.audit is not None:
        audit_report = json.loads(args.audit.read_text(encoding="utf-8"))
    gate = parse_gate(args.gate.read_text(encoding="utf-8"))
    gaps = identify_gaps(eval_report=eval_report, audit_report=audit_report, gate=gate)
    mode = eval_report.get("mode", "recognizers-only")
    output = render_next_gap(gaps, mode=mode, gate=gate)
    if args.output is None:
        sys.stdout.write(output)
    else:
        args.output.write_text(output, encoding="utf-8")
        print(f"Gap-Report geschrieben nach {args.output}", file=sys.stderr)

    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
