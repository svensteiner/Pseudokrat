"""Arena-Runner: Korpus erzeugen, prüfen, Nachweis-Report schreiben.

Aufruf::

    python -m tests.arena.runner --count 1500 --seed 0 --out arena_report

Erzeugt ``arena_report.json`` (Maschinen-Detail) und ``arena_report.md``
(lesbarer Nachweis). Exit-Code 1, sobald im **realistischen** Korpus ein
Leck auftritt oder ein Roundtrip scheitert — taugt damit als CI-Gate.
Der Reflow-Stress wird separat ausgewiesen.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from tests.arena.corpus import (
    MODES,
    Document,
    generate_documents,
    generate_reflow_stress,
)
from tests.arena.leakcheck import DocResult, Leak, check_document, make_store


@dataclass
class ArenaSummary:
    total_docs: int
    total_secrets: int
    leak_count: int
    roundtrip_failures: int
    by_mode: dict[str, dict[str, int]] = field(default_factory=dict)
    by_category: dict[str, dict[str, int]] = field(default_factory=dict)
    leaks: list[Leak] = field(default_factory=list)
    seed: int = 0

    @property
    def passed(self) -> bool:
        return self.leak_count == 0 and self.roundtrip_failures == 0


def _aggregate(docs: list[Document], results: list[DocResult], seed: int) -> ArenaSummary:
    all_leaks = [lk for r in results for lk in r.leaks]
    roundtrip_failures = sum(0 if r.roundtrip_ok else 1 for r in results)

    secrets_by_mode: Counter[str] = Counter()
    leaks_by_mode: Counter[str] = Counter()
    secrets_by_cat: Counter[str] = Counter()
    leaks_by_cat: Counter[str] = Counter()

    for doc, res in zip(docs, results, strict=True):
        secrets_by_mode[doc.mode] += res.secret_count
        for s in doc.secrets:
            secrets_by_cat[s.category] += 1
    for lk in all_leaks:
        leaks_by_mode[lk.mode] += 1
        leaks_by_cat[lk.category] += 1

    modes = sorted({d.mode for d in docs}) or list(MODES)
    return ArenaSummary(
        total_docs=len(docs),
        total_secrets=sum(r.secret_count for r in results),
        leak_count=len(all_leaks),
        roundtrip_failures=roundtrip_failures,
        by_mode={m: {"secrets": secrets_by_mode[m], "leaks": leaks_by_mode[m]} for m in modes},
        by_category={
            c: {"secrets": secrets_by_cat[c], "leaks": leaks_by_cat[c]}
            for c in sorted(secrets_by_cat)
        },
        leaks=all_leaks,
        seed=seed,
    )


def _run_corpus(docs: list[Document], seed: int) -> ArenaSummary:
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp) / "arena.sqlite")
        try:
            results = [check_document(d, store) for d in docs]
        finally:
            store.close()
    return _aggregate(docs, results, seed)


def run(count: int, seed: int = 0) -> ArenaSummary:
    return _run_corpus(generate_documents(count, seed=seed), seed)


def run_reflow(count: int, seed: int = 1000) -> ArenaSummary:
    return _run_corpus(generate_reflow_stress(count, seed=seed), seed)


def negative_control(seed: int = 0) -> bool:
    """Beweis, dass das Leck-Tor nicht blind grün ist: ein Geheimnis gegen
    seinen eigenen Klartext MUSS als Leck erkannt werden."""
    from tests.arena.leakcheck import _survives

    for doc in generate_documents(12, seed=seed):
        for secret in doc.secrets:
            if not _survives(secret, doc.text):
                return False
    return True


def _category_leak_table(summary: ArenaSummary) -> list[str]:
    lines = ["| Kategorie | Geheimnisse | Lecks |", "|---|---:|---:|"]
    for c, d in summary.by_category.items():
        lines.append(f"| {c} | {d['secrets']} | {d['leaks']} |")
    return lines


def _md_report(core: ArenaSummary, reflow: ArenaSummary | None) -> str:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    status = "BESTANDEN — 0 Lecks" if core.passed else "LECK GEFUNDEN"
    leak_rate = 0.0 if core.total_secrets == 0 else core.leak_count / core.total_secrets
    lines: list[str] = []
    lines.append("# Pseudokrat — Anonymisierungs-Nachweis (Testarena)")
    lines.append("")
    lines.append(f"**Ergebnis (realistischer Korpus):** {status}")
    lines.append("")
    lines.append(f"- Lauf-Zeitpunkt: {ts}")
    lines.append(f"- Seed (reproduzierbar): `{core.seed}`")
    lines.append(f"- Geprüfte Dokumente: **{core.total_docs}**")
    lines.append(f"- Geprüfte Geheimnisse (PII-Werte): **{core.total_secrets}**")
    lines.append(f"- Durchgerutschte Geheimnisse (Lecks): **{core.leak_count}**")
    lines.append(f"- Leck-Quote: **{leak_rate:.4%}**")
    lines.append(f"- Roundtrip-Fehler (Rückübersetzung): **{core.roundtrip_failures}**")
    lines.append(f"- Python: {platform.python_version()} · {platform.system()}")
    lines.append("")
    lines.append("## Nach Härtegrad (Formatierungs-Modus)")
    lines.append("")
    lines.append("| Modus | Geheimnisse | Lecks |")
    lines.append("|---|---:|---:|")
    for m, d in core.by_mode.items():
        lines.append(f"| {m} | {d['secrets']} | {d['leaks']} |")
    lines.append("")
    lines.append("## Nach PII-Kategorie")
    lines.append("")
    lines.extend(_category_leak_table(core))
    lines.append("")
    if core.leaks:
        lines.append("## Gefundene Lecks (Auszug, max. 50)")
        lines.append("")
        lines.append("| Kategorie | Modus | Land | Vorlage | Wert |")
        lines.append("|---|---|---|---|---|")
        for lk in core.leaks[:50]:
            safe = lk.value.replace("\n", "/").replace("|", "/")
            lines.append(f"| {lk.category} | {lk.mode} | {lk.country} | {lk.template} | {safe} |")
        lines.append("")
    else:
        lines.append("## Interpretation")
        lines.append("")
        lines.append(
            "Über alle Vorlagen, Formatierungs-Modi und Länder (AT/DE/CH) hinweg "
            "ist kein einziger der eingebauten PII-Werte im anonymisierten Text "
            "verblieben — auch nicht über Zeilenumbrüche oder ungewöhnliche "
            "Abstände zerrissen. Jede Rückübersetzung hat das Original exakt "
            "wiederhergestellt."
        )
        lines.append("")
    if reflow is not None:
        lines.append("## Reflow-Stress (separat, nicht im Pass/Fail-Tor)")
        lines.append("")
        lines.append(
            "Extremfall: numerische Werte (z. B. IBAN) mitten im Wert durch einen "
            "Zeilenumbruch zerrissen. Bewusst hart; zeigt die Robustheit gegen "
            "ungünstige Umbrüche."
        )
        lines.append("")
        lines.append(f"- Dokumente: {reflow.total_docs} · Geheimnisse: {reflow.total_secrets}")
        lines.append(f"- Lecks im Reflow-Stress: **{reflow.leak_count}**")
        lines.append("")
    lines.append("---")
    lines.append(
        "_PII-Werte sind synthetisch (erfunden), durchlaufen aber die echten "
        "Prüfziffer-Verfahren. Geprüft wird die Text-Pipeline; Datei-Formate "
        "(PDF/DOCX/XLSX) nutzen dieselbe Engine (siehe `tests/test_formats_*`)._"
    )
    return "\n".join(lines)


def _summary_json(s: ArenaSummary) -> dict:
    return {
        "passed": s.passed,
        "seed": s.seed,
        "total_docs": s.total_docs,
        "total_secrets": s.total_secrets,
        "leak_count": s.leak_count,
        "roundtrip_failures": s.roundtrip_failures,
        "by_mode": s.by_mode,
        "by_category": s.by_category,
        "leaks": [
            {"category": lk.category, "mode": lk.mode, "country": lk.country,
             "template": lk.template, "value": lk.value}
            for lk in s.leaks
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pseudokrat Testarena")
    parser.add_argument("--count", type=int, default=1500)
    parser.add_argument("--reflow-count", type=int, default=300)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=str, default="arena_report")
    parser.add_argument("--no-negative-control", action="store_true")
    args = parser.parse_args(argv)

    if not args.no_negative_control:
        if not negative_control(seed=args.seed):
            print("FEHLER: Negativ-Kontrolle versagt — Leck-Tor erkennt kein Leck.")
            return 2
        print("Negativ-Kontrolle ok (Leck-Tor erkennt eingebaute Lecks).")

    print(f"Arena (realistisch): {args.count} Dokumente, Seed {args.seed} ...")
    core = run(args.count, seed=args.seed)
    reflow = None
    if args.reflow_count > 0:
        print(f"Reflow-Stress: {args.reflow_count} Dokumente ...")
        reflow = run_reflow(args.reflow_count, seed=args.seed + 1000)

    payload = {
        "core": _summary_json(core),
        "reflow": _summary_json(reflow) if reflow else None,
        "generated": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.system(),
    }
    Path(f"{args.out}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path(f"{args.out}.md").write_text(_md_report(core, reflow), encoding="utf-8")

    print(
        f"Fertig: {core.total_docs} Dok., {core.total_secrets} Geheimnisse, "
        f"{core.leak_count} Lecks, {core.roundtrip_failures} Roundtrip-Fehler."
    )
    if reflow:
        print(f"Reflow-Stress: {reflow.leak_count} Lecks / {reflow.total_secrets} Geheimnisse.")
    print(f"Report: {args.out}.md / {args.out}.json")
    return 0 if core.passed else 1


if __name__ == "__main__":
    sys.exit(main())
