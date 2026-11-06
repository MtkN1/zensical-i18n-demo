# Translations

Gettext catalogs for the documentation site. Zensical has no built-in i18n, so
`uv run i18n` (see `src/zensical_i18n_demo/i18n.py`) converts Markdown to PO
files with Translate Toolkit's `md2po` and back with `po2md`, then builds one
Zensical site per language.

```
build/pot/*.pot      generated templates (not in git)
po/<lang>/*.po       translations, one file per Markdown page
po/<lang>/_config.po site name, navigation and other zensical.toml strings
```

Languages are listed in `[tool.i18n]` of `pyproject.toml`.

## Workflow

```sh
uv run i18n extract   # after editing docs/ or zensical.toml: update templates and merge into po/<lang>/
# translate: fill empty msgstr and review entries marked "#, fuzzy" (remove the flag when done)
uv run i18n check     # every entry translated, placeholders and markup preserved
uv run i18n build     # build site/ (source language) and site/<lang>/
```

## Translation rules

Only `msgstr` is translated. Never change `msgid`, `msgctxt`, `#:` comments or
the header entry.

Each `msgid` is a Markdown fragment. Translate the human-readable text and keep
the Markdown working:

- **Placeholders** `{1}`, `{2}`, ... stand for links, images or inline HTML.
  Keep every placeholder exactly once; you may move it within the sentence.
  The text in brackets just before it (`[documentation]{1}`) is link text and
  should be translated.
- **Inline code** in backticks (`` `zensical.toml` ``, `` `#!python ...` ``) is
  copied verbatim.
- **Block syntax keywords** stay verbatim at the start of the string:
  `!!! note`, `??? info`, `=== `, `[x] `, `[ ] `, `[^1]: `. Only a quoted title
  after them is translated: `!!! warning "Needs configuration"` →
  `!!! warning "設定が必要です"`.
- **Inline markup** is kept around the translated text: `**bold**`, `_italic_`,
  `==mark==`, `^^insert^^`, `~~delete~~`, `H~2~O`, `A^T^A`, `++ctrl+alt+del++`,
  `:emoji_name:`, footnote refs `[^1]`, math `$...$` / `$$...$$`, HTML tags.
- **Key names** in `++...++` are identifiers, not words: keep `++ctrl+alt+del++`
  (not `++strg+alt+entf++`), otherwise the keys are not rendered.
- **Line breaks**: if `msgid` has several lines (`\n`), `msgstr` has the same
  number of lines. Keep a trailing two-space or backslash hard break if present.
- **Nothing to translate** (only code, symbols, names or markup): copy `msgid`
  to `msgstr` unchanged.
- **Reference link labels** (a bare word such as `new` or `example` that names a
  `[label]: url` definition) are pre-filled with the source and must stay as is.
- Product and technical names stay in English: Zensical, Markdown, Python,
  Rust, MathJax, GitHub, TOML.
- Use the natural, concise register of technical documentation in the target
  language (e.g. です/ます in Japanese, "du" is fine in German developer docs).
- Escape `"` as `\"` and `\` as `\\` inside PO strings, as in `msgid`.
