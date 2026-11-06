"""Gettext-based i18n workflow for Zensical.

Zensical has no built-in i18n support, so each language is built as an
independent Zensical site and the results are assembled into one output:

    site/            <- source language (e.g. en)
    site/<lang>/     <- each translated language

Commands (run with ``uv run i18n <command>``):

    extract  Markdown/zensical.toml -> build/pot/*.pot -> po/<lang>/*.po
    check    validate translations in po/<lang>/*.po
    build    po/<lang>/*.po -> translated Markdown -> site/

Languages are configured in ``[tool.i18n]`` of ``pyproject.toml``.
"""

from __future__ import annotations

import argparse
import copy
import re
import shutil
import subprocess
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import tomli_w
from translate.storage import po

ROOT = Path.cwd()
PO_DIR = ROOT / "po"
POT_DIR = ROOT / "build" / "pot"
WORK_DIR = ROOT / "build" / "i18n"
SITE_DIR = ROOT / "site"
CONFIG_FILE = ROOT / "zensical.toml"
CONFIG_DOMAIN = "_config"

# Options shared by md2po and po2md: never extract code blocks or front
# matter, never reflow lines (reflowing breaks Python-Markdown block syntax).
MD_OPTS = ["--no-code-blocks", "--no-frontmatter", "--maxlinelength=0"]


@dataclass(frozen=True)
class Language:
    code: str
    name: str


@dataclass(frozen=True)
class Settings:
    source: Language
    targets: list[Language]

    @property
    def all(self) -> list[Language]:
        return [self.source, *self.targets]


def load_settings() -> Settings:
    with (ROOT / "pyproject.toml").open("rb") as f:
        cfg = tomllib.load(f)["tool"]["i18n"]
    langs = [Language(x["code"], x["name"]) for x in cfg["languages"]]
    source = next(x for x in langs if x.code == cfg["source"])
    return Settings(source, [x for x in langs if x is not source])


def load_config() -> dict:
    with CONFIG_FILE.open("rb") as f:
        return tomllib.load(f)


def docs_dir(config: dict) -> Path:
    return ROOT / config["project"].get("docs_dir", "docs")


def run(*args: str | Path) -> None:
    cmd = [str(a) for a in args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{result.stdout}{result.stderr}")


def tool(name: str) -> Path:
    return Path(sys.executable).parent / name


# ---------------------------------------------------------------------------
# zensical.toml strings
# ---------------------------------------------------------------------------


def iter_nav_titles(nav: list) -> list[str]:
    titles = []
    for item in nav:
        if isinstance(item, dict):
            for title, value in item.items():
                titles.append(title)
                if isinstance(value, list):
                    titles.extend(iter_nav_titles(value))
    return titles


def config_strings(config: dict) -> list[tuple[str, str]]:
    """Return (context, text) pairs of translatable strings in zensical.toml."""
    project = config["project"]
    strings = [("site_name", project["site_name"])]
    if desc := project.get("site_description"):
        strings.append(("site_description", desc))
    strings += [("nav", t) for t in iter_nav_titles(project.get("nav", []))]
    for palette in project.get("theme", {}).get("palette", []):
        if name := palette.get("toggle", {}).get("name"):
            strings.append(("theme.palette.toggle.name", name))
    return strings


def translate_nav(nav: list, tr: dict[str, str]) -> list:
    result = []
    for item in nav:
        if isinstance(item, dict):
            result.append({
                tr.get(k, k): translate_nav(v, tr) if isinstance(v, list) else v
                for k, v in item.items()
            })
        else:
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------

REF_DEF = re.compile(r"^ {0,3}\[([^\]]+)\]:\s", re.MULTILINE)


def write_config_pot(config: dict, path: Path) -> None:
    store = po.pofile()
    seen = set()
    for ctx, text in config_strings(config):
        if (ctx, text) in seen:
            continue
        seen.add((ctx, text))
        unit = store.addsourceunit(text)
        unit.setcontext(ctx)
        unit.addlocation(f"{CONFIG_FILE.name}:{ctx}")
    path.parent.mkdir(parents=True, exist_ok=True)
    store.savefile(str(path))


def finalize_po(path: Path, lang: Language, ref_labels: set[str]) -> None:
    """Set the Language header and pre-fill reference link labels.

    Reference labels such as ``[example]: https://...`` are extracted by md2po
    but must stay identical, otherwise links break.
    """
    store = po.pofile.parsefile(str(path))
    store.updateheader(add=True, Language=lang.code.replace("-", "_"))
    for unit in store.units:
        if unit.isheader() or unit.istranslated():
            continue
        if unit.source in ref_labels:
            unit.target = unit.source
    store.savefile(str(path))


def cmd_extract(settings: Settings) -> None:
    config = load_config()
    docs = docs_dir(config)
    pots: dict[str, set[str]] = {}

    if POT_DIR.exists():
        shutil.rmtree(POT_DIR)
    for md in sorted(docs.rglob("*.md")):
        rel = md.relative_to(docs).with_suffix("")
        pot = POT_DIR / rel.with_suffix(".pot")
        pot.parent.mkdir(parents=True, exist_ok=True)
        run(tool("md2po"), *MD_OPTS, "--duplicates=merge", "--pot",
            md.relative_to(ROOT), pot)
        pots[rel.as_posix()] = set(REF_DEF.findall(md.read_text("utf-8")))
    write_config_pot(config, POT_DIR / f"{CONFIG_DOMAIN}.pot")
    pots[CONFIG_DOMAIN] = set()

    for lang in settings.targets:
        for rel, labels in pots.items():
            pot = POT_DIR / f"{rel}.pot"
            dest = PO_DIR / lang.code / f"{rel}.po"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                # Merge: keep existing translations, mark changed ones fuzzy.
                tmp = dest.with_suffix(".po.new")
                run(tool("pot2po"), "-t", dest, "-i", pot, "-o", tmp)
                tmp.replace(dest)
            else:
                run(tool("pot2po"), "-i", pot, "-o", dest)
            finalize_po(dest, lang, labels)
        for stale in (PO_DIR / lang.code).rglob("*.po"):
            rel = stale.relative_to(PO_DIR / lang.code).with_suffix("").as_posix()
            if rel not in pots:
                print(f"warning: {stale.relative_to(ROOT)} has no source; remove it")
        print(f"{lang.code}: {stats(PO_DIR / lang.code)}")


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

# Tokens that must survive translation unchanged (as a multiset).
PRESERVE = [
    re.compile(r"\{\d+\}"),  # md2po inline placeholders (links, images, ...)
    re.compile(r"`[^`]+`"),  # inline code
    re.compile(r"\[\^[^\]]+\]"),  # footnote references
    re.compile(r":[a-z0-9_+-]+:"),  # emoji shortcodes
    re.compile(r"\$\$.+?\$\$|\$[^$\s][^$]*\$"),  # math
    re.compile(r"\+\+[\w-]+(?:\+[\w-]+)*\+\+"),  # keys (++ctrl+alt+del++)
]
# Block syntax prefix that must be kept verbatim (admonitions, tabs, tasks).
PREFIX = re.compile(r'^(?:(?:!!!|\?\?\?\+?) [\w-]+|===\+? |\[[ xX]\] |\[\^[^\]]+\]: )')


def check_unit(unit) -> list[str]:
    src, tgt = unit.source, unit.target
    errors = []
    for pattern in PRESERVE:
        a, b = Counter(pattern.findall(src)), Counter(pattern.findall(tgt))
        if a != b:
            errors.append(f"tokens differ: {sorted(a.elements())} != {sorted(b.elements())}")
    if (m := PREFIX.match(src)) and not tgt.startswith(m.group(0)):
        errors.append(f"must start with {m.group(0)!r}")
    if src.count("\n") != tgt.count("\n"):
        errors.append("line count differs")
    return errors


def stats(lang_dir: Path) -> str:
    total = translated = fuzzy = 0
    for path in lang_dir.rglob("*.po"):
        for unit in po.pofile.parsefile(str(path)).units:
            if unit.isheader():
                continue
            total += 1
            translated += unit.istranslated()
            fuzzy += unit.isfuzzy()
    return f"{translated}/{total} translated, {fuzzy} fuzzy"


def cmd_check(settings: Settings) -> None:
    failed = False
    for lang in settings.targets:
        lang_dir = PO_DIR / lang.code
        for path in sorted(lang_dir.rglob("*.po")):
            store = po.pofile.parsefile(str(path))
            for unit in store.units:
                if unit.isheader():
                    continue
                where = f"{path.relative_to(ROOT)}: {unit.source[:60]!r}"
                if not unit.istranslated():
                    print(f"{where}: {'fuzzy' if unit.isfuzzy() else 'untranslated'}")
                    failed = True
                    continue
                for error in check_unit(unit):
                    print(f"{where}: {error}")
                    failed = True
        print(f"{lang.code}: {stats(lang_dir)}")
    if failed:
        sys.exit(1)


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def lang_config(config: dict, settings: Settings, lang: Language) -> dict:
    cfg = copy.deepcopy(config)
    project = cfg["project"]
    site_url = project.get("site_url", "/")
    base = site_url.rstrip("/") + "/"
    base_path = urlsplit(base).path or "/"
    is_source = lang == settings.source

    project["docs_dir"] = "docs"
    project["site_dir"] = "site"
    project["site_url"] = base if is_source else f"{base}{lang.code}/"
    project.setdefault("theme", {})["language"] = lang.code
    project.setdefault("extra", {})["alternate"] = [
        {
            "name": alt.name,
            "lang": alt.code,
            "link": base_path if alt == settings.source else f"{base_path}{alt.code}/",
        }
        for alt in settings.all
    ]

    if not is_source:
        pofile = PO_DIR / lang.code / f"{CONFIG_DOMAIN}.po"
        tr: dict[tuple[str, str], str] = {}
        if pofile.exists():
            for unit in po.pofile.parsefile(str(pofile)).units:
                if unit.istranslated():
                    tr[(unit.getcontext(), unit.source)] = unit.target
        get = lambda ctx, s: tr.get((ctx, s), s)  # noqa: E731
        project["site_name"] = get("site_name", project["site_name"])
        if "site_description" in project:
            project["site_description"] = get("site_description", project["site_description"])
        nav_tr = {s: t for (ctx, s), t in tr.items() if ctx == "nav"}
        if "nav" in project:
            project["nav"] = translate_nav(project["nav"], nav_tr)
        for palette in project["theme"].get("palette", []):
            if name := palette.get("toggle", {}).get("name"):
                palette["toggle"]["name"] = get("theme.palette.toggle.name", name)
    return cfg


def cmd_build(settings: Settings) -> None:
    config = load_config()
    docs = docs_dir(config)
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)

    for lang in settings.all:
        work = WORK_DIR / lang.code
        work_docs = work / "docs"
        # Copy everything (assets, overrides referenced from docs, ...).
        shutil.copytree(docs, work_docs)
        if lang != settings.source:
            for md in sorted(docs.rglob("*.md")):
                rel = md.relative_to(docs)
                pofile = PO_DIR / lang.code / rel.with_suffix(".po")
                if not pofile.exists():
                    print(f"warning: {pofile.relative_to(ROOT)} missing; using source")
                    continue
                run(tool("po2md"), *MD_OPTS, "-t", md, "-i", pofile, "-o", work_docs / rel)
        with (work / "zensical.toml").open("wb") as f:
            tomli_w.dump(lang_config(config, settings, lang), f)
        run(tool("zensical"), "build", "--clean", "-f", work / "zensical.toml")

        dest = SITE_DIR if lang == settings.source else SITE_DIR / lang.code
        shutil.copytree(work / "site", dest, dirs_exist_ok=True)
        print(f"{lang.code}: built -> {dest.relative_to(ROOT)}/")


def main() -> None:
    parser = argparse.ArgumentParser(prog="i18n", description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["extract", "check", "build"])
    args = parser.parse_args()
    settings = load_settings()
    {"extract": cmd_extract, "check": cmd_check, "build": cmd_build}[args.command](settings)


if __name__ == "__main__":
    main()
