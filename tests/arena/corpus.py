"""Generator für realistische DACH-Dokumente mit bekannter Ground Truth.

Jedes Dokument wird aus **registrierten Geheimnissen** zusammengebaut.
Ein Geheimnis ist ein PII-Wert (Name, IBAN, SVNR …), der nach der
Anonymisierung **nicht mehr** im Output auftauchen darf.

Wichtig für Fairness: PII wird so eingebettet, wie es in echten
Dokumenten steht — Namen mit Anrede/Titel, Firmen mit Rechtsform,
Adressen mit PLZ+Ort, BIC mit Kontextwort. Andernfalls würde die Arena
legitime Erkennungs-Grenzen als „Leck" fehldeuten.

Zwei Härtegrade:

* **Realistische Modi** (``clean``/``spacing``/``table``/``labelbreak``)
  — so sehen echte Belege, Formulare und aus PDF/Office extrahierte
  Texte aus. Diese Modi bilden das **Pass/Fail-Tor**.
* **Reflow-Stress** (``reflow``) — ein numerischer Wert (z. B. IBAN)
  wird mitten im Wert durch einen Zeilenumbruch zerrissen, wie es bei
  ungünstigem Umbruch passieren kann. Bewusst extrem; wird **separat**
  ausgewiesen, nicht im Pass/Fail-Tor gezählt.

Die PII-*Werte* sind erfunden, durchlaufen aber die echten
Prüfziffer-Verfahren (über ``tests.eval.synth``).
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from dataclasses import dataclass

from tests.eval.synth import (
    generate_at_iban,
    generate_at_svnr,
    generate_at_uid,
    generate_ch_ahv,
    generate_ch_iban,
    generate_de_iban,
    generate_de_steuer_id,
)

ALNUM_CATEGORIES: frozenset[str] = frozenset(
    {
        "IBAN",
        "SVNR",
        "UID",
        "STEUER_ID",
        "UST_ID",
        "AHV",
        "BIC",
        "PHONE",
        "BIRTHDATE",
    }
)


def canonical(category: str, value: str) -> str:
    """Vergleichs-Normalform eines Werts.

    Alphanumerische IDs → nur Buchstaben/Ziffern, Großschreibung (so
    wird ein über Leerzeichen/Umbruch zerrissener Wert erkannt).
    Text (Namen, Firmen, Adressen, E-Mail) → Whitespace zu einem
    Leerzeichen kollabiert, Groß/Klein erhalten.
    """
    if category in ALNUM_CATEGORIES:
        return re.sub(r"[^0-9A-Za-z]", "", value).upper()
    return re.sub(r"\s+", " ", value).strip()


@dataclass(frozen=True)
class Secret:
    """Ein eingebauter PII-Wert, der verschwinden muss."""

    value: str
    category: str

    @property
    def key(self) -> str:
        return canonical(self.category, self.value)


@dataclass
class Document:
    """Ein generiertes Dokument samt Ground Truth."""

    template: str
    mode: str
    country: str
    text: str
    secrets: list[Secret]


# --------------------------------------------------------------------------
# Pools (erfunden, DACH-typisch). Titel bewusst inkl. „DI"/„BSc" — das
# sind reale österreichische/moderne Titel; ob die Engine sie kennt,
# ist genau Teil des Tests.
# --------------------------------------------------------------------------

_FIRST_NAMES: tuple[str, ...] = (
    "Anna",
    "Markus",
    "Julia",
    "Stefan",
    "Katharina",
    "Thomas",
    "Eva",
    "Michael",
    "Sabine",
    "Andreas",
    "Petra",
    "Christian",
    "Birgit",
    "Wolfgang",
    "Claudia",
    "Bernhard",
    "Martina",
    "Florian",
    "Elisabeth",
    "Johannes",
    "Barbara",
    "Patrick",
    "Verena",
    "Daniel",
    "Nicole",
)
_LAST_NAMES: tuple[str, ...] = (
    "Hofer",
    "Gruber",
    "Huber",
    "Bauer",
    "Wagner",
    "Pichler",
    "Steiner",
    "Moser",
    "Mayer",
    "Berger",
    "Fuchs",
    "Eder",
    "Fischer",
    "Schmid",
    "Winkler",
    "Weber",
    "Schwarz",
    "Maier",
    "Reiter",
    "Lang",
)
_NOBILIARY: tuple[str, ...] = ("von", "van der", "zu")
_TITLES: tuple[str, ...] = ("Dr.", "Mag.", "DI", "BSc", "MMag.", "Dipl.-Ing.", "")
_SALUTATIONS: tuple[str, ...] = ("Herr", "Frau", "Herrn")

#: Vornamen BEWUSST ausserhalb der Gazetteer-Liste. In einem Justiz-Kontext
#: ohne Anrede (``Beklagter: …``) ist der Rollen-Anker die einzige Rettung —
#: prüft also genau die Lücke, die der Gazetteer (bekannter Vorname) nicht
#: abdeckt.
_FIRST_NAMES_RARE: tuple[str, ...] = (
    "Aloisia",
    "Cäcilia",
    "Notburga",
    "Ottokar",
    "Vinzenz",
    "Roswita",
)

_COMPANY_CORE: tuple[str, ...] = (
    "Hofer Bau",
    "Alpenland Logistik",
    "Donau Handels",
    "Bergblick Immobilien",
    "Wiener Tech",
    "Tirol Consulting",
    "Steirische Metall",
    "Nordwald Möbel",
    "Salzach Energie",
    "Kärnten Pharma",
)
_LEGAL_FORMS: tuple[str, ...] = ("GmbH", "AG", "GmbH & Co. KG", "KG", "e.U.")

_STREETS: tuple[str, ...] = (
    "Mariahilfer Straße",
    "Industriestraße",
    "Bahnhofgasse",
    "Lindenweg",
    "Hauptplatz",
    "Schillerstraße",
    "Königsallee",
    "Ringstraße",
)
_CITIES_AT = (("1010", "Wien"), ("4020", "Linz"), ("8010", "Graz"), ("5020", "Salzburg"))
_CITIES_DE = (("10115", "Berlin"), ("80331", "München"), ("20095", "Hamburg"))
_CITIES_CH = (("8001", "Zürich"), ("3011", "Bern"), ("4051", "Basel"))


class DocBuilder:
    """Baut ein Dokument zeilenweise und merkt sich alle Geheimnisse."""

    def __init__(
        self, rng: random.Random, mode: str, country: str, *, reflow: bool = False
    ) -> None:
        self.rng = rng
        self.mode = mode
        self.country = country
        self.reflow = reflow
        self._lines: list[str] = []
        self.secrets: list[Secret] = []

    # ---- Low-level -------------------------------------------------------

    def line(self, text: str) -> None:
        self._lines.append(text)

    def field(self, label: str, value: str) -> None:
        if self.mode == "labelbreak":
            self._lines.append(label + ":")
            self._lines.append("    " + value)
        elif self.mode == "table":
            self._lines.append(f"{label:<24}{value}")
        else:
            self._lines.append(f"{label}: {value}")

    def _register(self, value: str, category: str) -> None:
        self.secrets.append(Secret(value=value, category=category))

    def _reflow_num(self, surface: str) -> str:
        """Im Reflow-Stress einen numerischen Wert mittig umbrechen."""
        if self.reflow and len(surface) >= 8 and self.rng.random() < 0.6:
            half = len(surface) // 2
            return surface[:half] + "\n" + surface[half:]
        return surface

    # ---- PII-Emitter -----------------------------------------------------

    def person(self) -> str:
        first = self.rng.choice(_FIRST_NAMES)
        last = self.rng.choice(_LAST_NAMES)
        if self.rng.random() < 0.15:
            last = f"{self.rng.choice(_NOBILIARY)} {last}"
        name = f"{first} {last}"
        self._register(name, "PERSON")
        title = self.rng.choice(_TITLES)
        salu = self.rng.choice(_SALUTATIONS)
        prefix = f"{salu} {title}".strip()
        return f"{prefix} {name}"

    def person_bare(self, *, rare: bool = False) -> str:
        """Personenname OHNE Anrede/Titel. Mit ``rare=True`` ein Vorname
        ausserhalb des Gazetteers — dann muss der Rollen-Anker (z. B.
        ``Beklagter:``) den Namen allein fangen."""
        pool = _FIRST_NAMES_RARE if rare else _FIRST_NAMES
        first = self.rng.choice(pool)
        last = self.rng.choice(_LAST_NAMES)
        if self.rng.random() < 0.3:
            last = f"{self.rng.choice(_NOBILIARY)} {last}"
        name = f"{first} {last}"
        self._register(name, "PERSON")
        return name

    def company(self) -> str:
        core = self.rng.choice(_COMPANY_CORE)
        form = self.rng.choice(_LEGAL_FORMS)
        name = f"{core} {form}"
        self._register(name, "COMPANY")
        return name

    def address(self) -> str:
        street = self.rng.choice(_STREETS)
        nr = self.rng.randint(1, 188)
        plz, city = self.rng.choice(self._cities())
        addr = f"{street} {nr}, {plz} {city}"
        self._register(addr, "ADDRESS")
        return addr

    def iban(self) -> str:
        gen = {"AT": generate_at_iban, "DE": generate_de_iban, "CH": generate_ch_iban}[self.country]
        raw = gen(self.rng)
        self._register(raw, "IBAN")
        if self.mode in {"spacing", "table"}:
            return " ".join(raw[i : i + 4] for i in range(0, len(raw), 4))
        return self._reflow_num(raw)

    def bic(self) -> str:
        bank = "".join(self.rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(4))
        loc = "".join(self.rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789") for _ in range(2))
        bic = f"{bank}{self.country}{loc}"
        self._register(bic, "BIC")
        return f"BIC {bic}"

    def svnr(self) -> str:
        raw = generate_at_svnr(self.rng)
        self._register(raw, "SVNR")
        return self._reflow_num(raw)

    def uid(self) -> str:
        raw = generate_at_uid(self.rng)
        self._register(raw, "UID")
        return raw

    def steuer_id(self) -> str:
        raw = generate_de_steuer_id(self.rng)
        self._register(raw, "STEUER_ID")
        if self.mode in {"spacing", "table"}:
            return f"{raw[:2]} {raw[2:5]} {raw[5:8]} {raw[8:]}"
        return self._reflow_num(raw)

    def ahv(self) -> str:
        raw = generate_ch_ahv(self.rng)
        self._register(raw, "AHV")
        return raw

    def email(self) -> str:
        user = "".join(self.rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(7))
        dom = self.rng.choice(("example.at", "example.de", "kanzlei-example.com"))
        mail = f"{user}@{dom}"
        self._register(mail, "EMAIL")
        return mail

    def phone(self) -> str:
        cc = {"AT": "+43", "DE": "+49", "CH": "+41"}[self.country]
        num = f"{cc} {self.rng.randint(1, 699)} {self.rng.randint(1000000, 9999999)}"
        self._register(num, "PHONE")
        return num

    def birthdate(self) -> str:
        day = self.rng.randint(1, 28)
        month = self.rng.randint(1, 12)
        year = self.rng.randint(1950, 2005)
        date = f"{day:02d}.{month:02d}.{year}"
        self._register(date, "BIRTHDATE")
        return date

    # ---- Render ----------------------------------------------------------

    def _cities(self):
        return {"AT": _CITIES_AT, "DE": _CITIES_DE, "CH": _CITIES_CH}[self.country]

    def render(self, template: str) -> Document:
        return Document(
            template=template,
            mode="reflow" if self.reflow else self.mode,
            country=self.country,
            text="\n".join(self._lines),
            secrets=list(self.secrets),
        )


# --------------------------------------------------------------------------
# Dokument-Vorlagen
# --------------------------------------------------------------------------


def _t_lohnabrechnung(b: DocBuilder) -> Document:
    b.line("LOHN-/GEHALTSABRECHNUNG")
    b.line("")
    b.field("Dienstnehmer", b.person())
    b.field("Anschrift", b.address())
    b.field("Geburtsdatum", b.birthdate())
    b.field(
        "AHV-Nr." if b.country == "CH" else "SV-Nummer", b.ahv() if b.country == "CH" else b.svnr()
    )
    b.field("Gehaltskonto IBAN", b.iban())
    b.line("")
    b.field("Dienstgeber", b.company())
    if b.country == "AT":
        b.field("UID", b.uid())
    b.field("Firmen-IBAN", b.iban())
    b.line("")
    b.line(f"Bruttobezug: {b.rng.randint(2500, 7800)},00 EUR")
    b.line(f"Auszahlungsbetrag: {b.rng.randint(1800, 5200)},45 EUR")
    return b.render("lohnabrechnung")


def _t_steuerbescheid(b: DocBuilder) -> Document:
    b.line("FINANZAMT — EINKOMMENSTEUERBESCHEID")
    b.line("")
    b.field("Steuerpflichtige/r", b.person())
    b.field("Anschrift", b.address())
    if b.country == "DE":
        b.field("Steuer-Identifikationsnummer", b.steuer_id())
    elif b.country == "AT":
        b.field("Steuernummer (UID)", b.uid())
    b.field("Geburtsdatum", b.birthdate())
    b.field("Rückfragen E-Mail", b.email())
    b.line("")
    b.line(f"Festgesetzte Einkommensteuer: {b.rng.randint(3000, 41000)},00 EUR")
    return b.render("steuerbescheid")


def _t_mandantenbrief(b: DocBuilder) -> Document:
    b.line(f"{b.company()} — Steuerberatung")
    b.line("")
    b.line(f"An {b.person()}")
    b.field("Anschrift", b.address())
    b.line("")
    b.line("Sehr geehrte Damen und Herren,")
    b.line(
        "anbei die Unterlagen zur Umsatzsteuervoranmeldung. Den offenen "
        f"Betrag überweisen Sie bitte auf IBAN {b.iban()}."
    )
    b.field("Rückfragen Telefon", b.phone())
    b.field("E-Mail", b.email())
    b.line("Mit freundlichen Grüßen")
    b.line(b.person())
    return b.render("mandantenbrief")


def _t_arztbrief(b: DocBuilder) -> Document:
    b.line("ARZTBRIEF — VERTRAULICH")
    b.line("")
    b.field("Patient/in", b.person())
    b.field("Geburtsdatum", b.birthdate())
    b.field("Anschrift", b.address())
    b.field("AHV" if b.country == "CH" else "SV-Nummer", b.ahv() if b.country == "CH" else b.svnr())
    b.line("")
    b.line(
        "Diagnose: arterielle Hypertonie. Therapie laut beiliegendem Plan. "
        "Wir bitten um Mitbehandlung."
    )
    b.line(f"Mit kollegialen Grüßen, {b.person()}")
    return b.render("arztbrief")


def _t_anwaltsschriftsatz(b: DocBuilder) -> Document:
    b.line("IN DER RECHTSSACHE")
    b.line("")
    b.line(f"Klägerin: {b.company()}")
    b.field("vertreten durch", b.person())
    # Beklagter OHNE Anrede und mit gazetteer-fremdem Vornamen: nur der
    # Justiz-Rollen-Anker kann ihn fangen (Arena-Council L1).
    b.line(f"Beklagter: {b.person_bare(rare=True)}")
    b.field("wohnhaft", b.address())
    b.line("")
    b.line(f"Aktenzeichen wird per E-Mail {b.email()} übermittelt.")
    b.line(
        "Der Beklagte wird aufgefordert, den Betrag auf das Anderkonto "
        f"IBAN {b.iban()} ({b.bic()}) zu überweisen."
    )
    return b.render("anwaltsschriftsatz")


def _t_rechnung(b: DocBuilder) -> Document:
    b.line(f"RECHNUNG — {b.company()}")
    b.field("Rechnungsadresse", b.address())
    if b.country == "DE":
        b.field("USt-IdNr.", _de_ust(b))
    elif b.country == "AT":
        b.field("UID", b.uid())
    b.line("")
    b.field("Kunde", b.person())
    b.field("Kontakt", b.email())
    b.field("Telefon", b.phone())
    b.line("")
    b.line(f"Zahlbar auf IBAN {b.iban()}, {b.bic()}")
    b.line(f"Rechnungsbetrag: {b.rng.randint(120, 24000)},00 EUR inkl. USt")
    return b.render("rechnung")


def _de_ust(b: DocBuilder) -> str:
    """Gültige deutsche USt-IdNr (DE + 9 Ziffern) mit echter ISO-7064-
    MOD-11,10-Prüfziffer. Zufällige Ziffern würden vom Recognizer korrekt
    abgelehnt (strikte Validierung gegen FP auf Belegnummern) und fälschlich
    als „Leck" gezählt — die Arena verlangt prüfziffer-gültige Ground Truth."""
    body = [b.rng.randint(0, 9) for _ in range(8)]
    product = 10
    for d in body:
        s = (d + product) % 10 or 10
        product = (s * 2) % 11
    check = (11 - product) % 10
    val = "DE" + "".join(str(d) for d in body) + str(check)
    b._register(val, "UST_ID")
    return val


_TEMPLATES: tuple[Callable[[DocBuilder], Document], ...] = (
    _t_lohnabrechnung,
    _t_steuerbescheid,
    _t_mandantenbrief,
    _t_arztbrief,
    _t_anwaltsschriftsatz,
    _t_rechnung,
)

#: Realistische Modi — Grundlage des Pass/Fail-Tors.
MODES: tuple[str, ...] = ("clean", "spacing", "table", "labelbreak")
COUNTRIES: tuple[str, ...] = ("AT", "DE", "CH")


def generate_documents(count: int, seed: int = 0) -> list[Document]:
    """Realistischer Korpus über Vorlagen × Modi × Länder (reproduzierbar)."""
    rng = random.Random(seed)
    docs: list[Document] = []
    for i in range(count):
        template = _TEMPLATES[i % len(_TEMPLATES)]
        mode = MODES[(i // len(_TEMPLATES)) % len(MODES)]
        # Land NICHT an ``i % 3`` koppeln: ``len(_TEMPLATES)`` (6) ist ein
        # Vielfaches von ``len(COUNTRIES)`` (3), sonst wäre jede Vorlage fix an
        # ein Land gebunden und AHV (nur CH-Vorlagen) bzw. USt-IdNr (nur
        # DE-Rechnung) würden NIE erzeugt (Arena-Council).
        country = COUNTRIES[(i // len(_TEMPLATES)) % len(COUNTRIES)]
        docs.append(template(DocBuilder(rng, mode=mode, country=country)))
    return docs


def generate_reflow_stress(count: int, seed: int = 1000) -> list[Document]:
    """Extrem-Korpus: numerische Werte mitten im Wert umgebrochen.

    Separat ausgewiesen — Reflow-Erkennung ist ein bewusst hartes Ziel.
    """
    rng = random.Random(seed)
    docs: list[Document] = []
    for i in range(count):
        template = _TEMPLATES[i % len(_TEMPLATES)]
        # Land entkoppeln (s. generate_documents): sonst je Vorlage fixes Land.
        country = COUNTRIES[(i // len(_TEMPLATES)) % len(COUNTRIES)]
        docs.append(template(DocBuilder(rng, mode="clean", country=country, reflow=True)))
    return docs
