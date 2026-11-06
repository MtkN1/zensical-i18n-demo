# zensical-i18n-demo

An experiment in building a multilingual [Zensical](https://zensical.org/) site.
Zensical has no built-in i18n, so the pages are translated through Gettext PO
files with [Translate Toolkit](https://docs.translatehouse.org/projects/translate-toolkit/)
(`md2po` / `po2md`), and each language is built as a separate Zensical site:

| Language | Path |
| --- | --- |
| English (source) | `/` |
| हिन्दी, 简体中文, Português (Brasil), 日本語, Bahasa Indonesia, Deutsch, Русский, Français | `/<lang>/` |

The languages are those of the ten countries with the most developers on
GitHub ([Octoverse 2026](https://github.blog/news-insights/octoverse/octoverse-commits-pushes-reach-new-highs-in-2026-as-developers-build-with-agents/#h-developers-are-building-from-more-places)).

## Usage

```sh
uv sync
uv run zensical serve   # write the English source in docs/
uv run i18n extract     # update po/<lang>/*.po from docs/ and zensical.toml
uv run i18n check       # validate translations
uv run i18n build       # build all languages into site/
```

The language selector links include the path of `site_url`
(`/zensical-i18n-demo/`), so preview the built site under the same path:

```sh
mkdir -p build/preview && ln -sfn ../../site build/preview/zensical-i18n-demo
python -m http.server -d build/preview   # http://localhost:8000/zensical-i18n-demo/
```

See [po/README.md](po/README.md) for the translation workflow and rules.
