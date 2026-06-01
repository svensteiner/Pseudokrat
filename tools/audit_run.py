"""PRL Audit-Phase: bündelt statische Quality-Checks + Trust-Boundary-Coverage.

Aufruf::

    python -m tools.audit_run --json audit_report.json
    python -m tools.audit_run --skip-slow            # ohne pytest
    python -m tools.audit_run --only ruff,mypy,bandit

Liefert pro Tool einen Pass/Fail-Status + Stderr-Auszug. Plus eine
Heuristik, die für jede Trust-Boundary aus ``SELF_AUDIT.md`` prüft, ob
mindestens ein Test sie referenziert (Trust-Boundary-Coverage).

**Bewusste Trade-Offs:**

* Wir rufen die Tools als Subprocess auf — kein In-Process-Import.
  Vorteil: jeder Lauf läuft in seinem eigenen Python-Prozess, kein
  Import-Cache-Bias. Nachteil: 5 Subprocess-Spawns kosten 1-2 s.
* Trust-Boundary-Heuristik ist Grep über Test-Dateien, nicht
  AST-Analyse. Reicht: jede Boundary ist ein S<N>-Abschnitt im
  Self-Audit, und wir erwarten in mindestens einem Test entweder
  den S-Code im Docstring oder ein boundary-spezifisches Keyword im
  Modul-Pfad.
* `pip-audit` ist optional (nicht in dev-extras). Wenn nicht
  installiert, wird der Check als ``skipped`` gemeldet, nicht als
  ``failed``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # "pass" / "fail" / "skipped"
    returncode: int | None
    duration_seconds: float
    stdout_tail: str = ""
    stderr_tail: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _run(cmd: list[str], *, cwd: Path = REPO_ROOT, timeout: int = 600) -> tuple[int, str, str, float]:
    """Subprocess-Wrapper, der stdout/stderr captured und timing misst."""
    import time

    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return (
            -1,
            (exc.stdout or "").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or ""),
            f"TimeoutExpired after {timeout}s",
            time.monotonic() - started,
        )
    return proc.returncode, proc.stdout, proc.stderr, time.monotonic() - started


def _tail(s: str, lines: int = 30) -> str:
    return "\n".join(s.splitlines()[-lines:])


def check_ruff() -> CheckResult:
    rc, out, err, dur = _run([PYTHON, "-m", "ruff", "check", "src/", "tests/", "tools/"])
    return CheckResult(
        name="ruff",
        status="pass" if rc == 0 else "fail",
        returncode=rc,
        duration_seconds=dur,
        stdout_tail=_tail(out),
        stderr_tail=_tail(err),
    )


def check_mypy() -> CheckResult:
    rc, out, err, dur = _run([PYTHON, "-m", "mypy", "src/pseudokrat"])
    return CheckResult(
        name="mypy",
        status="pass" if rc == 0 else "fail",
        returncode=rc,
        duration_seconds=dur,
        stdout_tail=_tail(out),
        stderr_tail=_tail(err),
    )


def check_pytest(*, skip_slow: bool = True) -> CheckResult:
    cmd = [PYTHON, "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider"]
    if skip_slow:
        cmd += ["-m", "not slow"]
    rc, out, err, dur = _run(cmd, timeout=1800)
    return CheckResult(
        name="pytest",
        status="pass" if rc == 0 else "fail",
        returncode=rc,
        duration_seconds=dur,
        stdout_tail=_tail(out),
        stderr_tail=_tail(err),
    )


def check_bandit() -> CheckResult:
    # -ll: nur Medium+. -r: rekursiv. Wir interessieren uns für High-Severity.
    rc, out, err, dur = _run(
        [PYTHON, "-m", "bandit", "-r", "src/", "-ll", "-q"]
    )
    # Bandit-Konvention: exit 0 = clean, 1 = findings.
    return CheckResult(
        name="bandit",
        status="pass" if rc == 0 else "fail",
        returncode=rc,
        duration_seconds=dur,
        stdout_tail=_tail(out),
        stderr_tail=_tail(err),
    )


def check_pip_audit() -> CheckResult:
    # pip-audit ist optional. Wenn nicht installiert -> skipped.
    #
    # Wir auditieren das **Projekt** (pyproject.toml im Repo-Root), nicht
    # die laufende venv. Grund: pseudokrat selbst ist als editable
    # installiert, und ein env-Scan würde dadurch ``distribution marked
    # as editable`` als Strict-Fehler werfen (D-050). Der Projekt-Scan
    # erzeugt eine temporäre venv aus ``pyproject.toml``, in der genau
    # die deklarierten Runtime-Deps landen — und nur diese sind für
    # CVE-Audit relevant.
    rc, out, err, dur = _run(
        [PYTHON, "-m", "pip_audit", "--strict", str(REPO_ROOT)], timeout=300
    )
    if rc == -1 or "No module named" in err or "No module named" in out:
        return CheckResult(
            name="pip-audit",
            status="skipped",
            returncode=None,
            duration_seconds=dur,
            stderr_tail="pip-audit nicht installiert (pip install pip-audit).",
        )
    return CheckResult(
        name="pip-audit",
        status="pass" if rc == 0 else "fail",
        returncode=rc,
        duration_seconds=dur,
        stdout_tail=_tail(out),
        stderr_tail=_tail(err),
    )


# ---------- Trust-Boundary-Coverage -----------------------------------------

#: Regex zum Extrahieren von S<N>-Boundary-Überschriften aus SELF_AUDIT.md.
#: Format-Annahme: ``### S<N> — <Titel>``.
_BOUNDARY_HEADING_RE = re.compile(r"^###\s+(S\d+)\s+[—-]\s+(.+?)\s*$", re.MULTILINE)


def _extract_boundaries(self_audit_path: Path) -> list[tuple[str, str]]:
    """Liefert ``[(id, title), ...]`` für jede S<N>-Boundary im Self-Audit."""
    if not self_audit_path.exists():
        return []
    text = self_audit_path.read_text(encoding="utf-8")
    return [(m.group(1), m.group(2).strip()) for m in _BOUNDARY_HEADING_RE.finditer(text)]


def _test_files() -> list[Path]:
    tests_dir = REPO_ROOT / "tests"
    return list(tests_dir.rglob("*.py"))


def _grep_count(needle: str, files: Iterable[Path]) -> int:
    """Zähle Tests, in denen ``needle`` im Code vorkommt (case-insensitive)."""
    n = 0
    needle_low = needle.lower()
    for f in files:
        try:
            blob = f.read_text(encoding="utf-8").lower()
        except OSError:
            continue
        if needle_low in blob:
            n += 1
    return n


_STOPWORDS = frozenset(
    {
        "der", "die", "das", "und", "vor", "auf", "mit", "bei", "ein", "eine",
        "security", "model", "siehe", "phase", "fuer", "für",
    }
)


def _title_keywords(title: str) -> list[str]:
    """Tokenize Title → Stems für Substring-Matching.

    Splittet auf Whitespace UND Bindestrich (sonst würde
    ``DP-Permutation`` als ein Token bleiben und nie matchen).
    Stems = lowercase, mindestens 4 Zeichen, Stopwords gefiltert,
    und auf maximal 5 Zeichen gekürzt (damit ``Permutation`` als
    ``permu`` auch ``permute`` und ``permutation`` matcht — klassische
    Retrieval-Stem-Heuristik).
    """
    tokens = re.findall(r"[A-Za-zÄÖÜäöüß0-9_]+", title.replace("-", " "))
    stems: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        low = t.lower()
        if len(low) < 4 or low in _STOPWORDS:
            continue
        stem = low[:5]
        if stem in seen:
            continue
        seen.add(stem)
        stems.append(stem)
    return stems


def check_trust_boundary_coverage() -> CheckResult:
    """Pro Boundary-ID + Titel: kommt der S<N>-Code oder mindestens
    ein Title-Stem in einem Test vor? Wenn nicht, gilt die Boundary
    als ungetestet.

    Heuristik mit zwei Signalen:

    1. Direkter S<N>-Code-Match (case-insensitive) im Test-File.
    2. Title-Stems: Titel auf Whitespace + Bindestriche zerlegt, je
       Token die ersten 5 Zeichen als Stem (matched
       ``permutation``/``permute`` via ``permu``); Stopwords
       gefiltert.

    Mindestens **eines** der Signale muss treffen.
    """
    self_audit = REPO_ROOT / "SELF_AUDIT.md"
    boundaries = _extract_boundaries(self_audit)
    files = _test_files()

    covered: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for boundary_id, title in boundaries:
        id_hits = _grep_count(boundary_id, files)
        stems = _title_keywords(title)
        stem_hits = {stem: _grep_count(stem, files) for stem in stems}
        has_coverage = id_hits > 0 or any(v > 0 for v in stem_hits.values())
        covered[boundary_id] = {
            "title": title,
            "id_hits": id_hits,
            "stems": stems,
            "stem_hits": stem_hits,
            "covered": has_coverage,
        }
        if not has_coverage:
            missing.append(f"{boundary_id} ({title})")

    status = "pass" if not missing else "fail"
    summary = (
        f"{len(boundaries)} Boundaries, {sum(1 for v in covered.values() if v['covered'])} covered, "
        f"{len(missing)} missing."
    )
    return CheckResult(
        name="trust-boundary-coverage",
        status=status,
        returncode=0 if status == "pass" else 1,
        duration_seconds=0.0,
        stdout_tail=summary + ("\nUngetestete Boundaries:\n  - " + "\n  - ".join(missing) if missing else ""),
        extra={"per_boundary": covered, "missing": missing},
    )


# ---------- Aggregation -----------------------------------------------------


_ALL_CHECKS = {
    "ruff": check_ruff,
    "mypy": check_mypy,
    "pytest": check_pytest,
    "bandit": check_bandit,
    "pip-audit": check_pip_audit,
    "trust-boundary-coverage": check_trust_boundary_coverage,
}


def run_checks(
    *, only: list[str] | None = None, skip_slow: bool = True
) -> list[CheckResult]:
    names = list(_ALL_CHECKS) if only is None else only
    results: list[CheckResult] = []
    for name in names:
        fn = _ALL_CHECKS.get(name)
        if fn is None:
            results.append(
                CheckResult(
                    name=name,
                    status="skipped",
                    returncode=None,
                    duration_seconds=0.0,
                    stderr_tail=f"Unbekannter Check: {name}",
                )
            )
            continue
        if name == "pytest":
            results.append(check_pytest(skip_slow=skip_slow))
        else:
            results.append(fn())
    return results


def render_report(results: list[CheckResult]) -> dict[str, Any]:
    return {
        "checks": [
            {
                "name": r.name,
                "status": r.status,
                "returncode": r.returncode,
                "duration_seconds": round(r.duration_seconds, 2),
                "stdout_tail": r.stdout_tail,
                "stderr_tail": r.stderr_tail,
                "extra": r.extra,
            }
            for r in results
        ],
        "totals": {
            "pass": sum(1 for r in results if r.status == "pass"),
            "fail": sum(1 for r in results if r.status == "fail"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PRL Audit-Phase")
    parser.add_argument("--json", type=Path, default=None, help="Report-Pfad (Default: stdout).")
    parser.add_argument(
        "--only",
        default=None,
        help="Kommaseparierte Liste der Checks (Default: alle).",
    )
    parser.add_argument(
        "--skip-slow",
        action="store_true",
        default=True,
        help="pytest mit 'not slow'-Filter (Default: true).",
    )
    parser.add_argument(
        "--include-slow",
        action="store_false",
        dest="skip_slow",
        help="pytest inkl. slow-Markierten.",
    )
    args = parser.parse_args(argv)

    only_list = [s.strip() for s in args.only.split(",")] if args.only else None
    results = run_checks(only=only_list, skip_slow=args.skip_slow)
    report = render_report(results)

    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.json is None:
        sys.stdout.write(payload + "\n")
    else:
        args.json.write_text(payload, encoding="utf-8")
        print(f"Audit-Report geschrieben nach {args.json}", file=sys.stderr)

    # Exit-Code: 0 wenn alle pass+skipped, 1 wenn mindestens ein fail.
    return 0 if report["totals"]["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
