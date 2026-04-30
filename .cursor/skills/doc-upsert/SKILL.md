---
name: doc-upsert
description: Pushes a local markdown doc to a Notion database (create or update by Doc ID). Resolves inline cross-links via Notion query with GitHub fallback. After upsert, if targets are not in Notion yet, the agent should ask the user before running --upload-missing. Reads NOTION_TOKEN from .env. Use when syncing docs to Notion, Notion upsert, Research Docs, or pushing IDCTR-/INFRA-/CODE- prefixed documentation.
---

# Doc upsert (Notion)

Sync a **`docs/{REPO_ID}-{PREFIX}-{NNNN}-{slug}.md`** file into the 42hz.ai **Research Docs** Notion database. **Local markdown is authoritative** — each run replaces the page body in Notion to match the file.

Pair with **[`doc-create`](../doc-create/SKILL.md)** for naming rules.

## Prerequisites

1. **Notion integration** (e.g. “Cursor Sync”) with **Read**, **Insert content**, and **Update content** on the target database (required for `POST /v1/pages` with `markdown` and `PATCH /v1/pages/{id}/markdown`).
2. **Connect the integration** to the database (Share → invite the integration).
3. **Database columns** — run once from the repo root to add the standard fields Notion needs (rich text **Doc ID**, **REPO_ID**, rich text **Content SHA**, and select **PREFIX** with `INFRA` / `CODE`):

   ```bash
   uv sync --group notion
   uv run python .cursor/skills/doc-upsert/scripts/notion_doc_upsert.py --ensure-schema
   ```

   Skip this if those properties already exist. The script still works with fewer columns (it falls back to **Local Path** for upsert), but **Doc ID** is the intended stable key.

## Environment (`.env` at repo root)

| Variable                    | Required | Description                                                                                                                                                                                                          |
| --------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NOTION_TOKEN`              | Yes      | Internal integration secret (`secret_…`).                                                                                                                                                                            |
| `NOTION_DATABASE_ID`        | No       | Defaults to the shared Research Docs database if unset.                                                                                                                                                              |
| `NOTION_PROJECT`            | No       | Overrides **Project** when set; otherwise uses `repository_slug` from `.copier-answers.yml` if present.                                                                                                              |
| `NOTION_DOC_LINK_BASE`      | No       | Prefix URL for **GitHub fallback** when a linked `.md` is not yet in Notion (no trailing slash), e.g. `https://github.com/org/repo/blob/main`. Changing this value changes **Content SHA** so the next run re-syncs. |
| `NOTION_UPLOAD_MISSING`     | No       | If `1` / `true`, same as **`--upload-missing`** (overridden by **`--no-upload-missing`**).                                                                                                                           |
| `NOTION_LINK_TARGET_STRICT` | No       | If `1` / `true`, same as **`--strict-links`**.                                                                                                                                                                       |

Never commit `.env`.

## Notion properties (expected names)

| Notion property | Type                | Set by script                                                                                                                                                              |
| --------------- | ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Name**        | Title               | First `#` heading in the file, else derived from filename.                                                                                                                 |
| **Doc ID**      | Rich text           | Upsert key: filename stem (no `.md`).                                                                                                                                      |
| **REPO_ID**     | Rich text           | From filename.                                                                                                                                                             |
| **PREFIX**      | Select              | `INFRA` or `CODE`.                                                                                                                                                         |
| **Doc Number**  | Rich text           | Four digits (`0001`).                                                                                                                                                      |
| **Project**     | Select or rich text | Repo slug (`repository_slug` or `NOTION_PROJECT`); select options must exist if the column is a select.                                                                    |
| **Local Path**  | Rich text           | Path relative to repo root.                                                                                                                                                |
| **Content SHA** | Rich text           | `sha256:` + hex digest of a **sync fingerprint** (file text, optional link base, and **link-resolution state** so Notion/GitHub link targets refresh when the DB changes). |

Rename columns in Notion to match exactly, or override names via env vars prefixed with `NOTION_PROP_` (see script help).

## Run

From the **repository root** (where `.copier-answers.yml` and `pyproject.toml` live):

```bash
uv sync --group notion
uv run python .cursor/skills/doc-upsert/scripts/notion_doc_upsert.py docs/IDCTR-INFRA-0001-aws-identity-center.md
```

Add **`--force`** to push the body and refresh **Content SHA** even when the stored hash already matches the file (e.g. after manual edits in Notion).

**Link / batch flags**

| Flag                  | Purpose                                                                                                                                                                                                                                                                 |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--upload-missing`    | After the primary file, upsert each linked `.md` that exists on disk but has **no** Notion row yet (doc-create filename pattern required).                                                                                                                              |
| `--no-upload-missing` | Never upload missing deps (overrides `NOTION_UPLOAD_MISSING=1`).                                                                                                                                                                                                        |
| `--closure`           | After **`--upload-missing`** actually upserts **at least one** linked file, **re-sync the primary file** with `--force` so inline links can switch from GitHub fallback to **Notion** URLs. If nothing needed uploading, closure does nothing (avoids a duplicate run). |
| `--strict-links`      | Exit with code **1** if any in-repo `.md` link target is still missing in Notion **after** the primary sync (use in CI when every link must resolve).                                                                                                                   |
| `-v` / `--verbose`    | Under **Link resolution:**, list each path resolved to Notion or GitHub.                                                                                                                                                                                                |

(Copier template projects use `uv sync --extra notion` instead of `--group notion`.)

Use a path relative to repo root or absolute.

## Behavior

1. Parses the filename with the doc-create pattern.
2. Queries Notion for **Doc ID** = stem when that column exists; otherwise **Local Path** = relative path.
3. **Update**: patches properties, then **`PATCH /v1/pages/{page_id}/markdown`** with `replace_content` so the full file replaces the page body (Notion enhanced markdown — same rendering as the app’s markdown importer).
4. **Create**: **`POST /v1/pages`** with `parent.data_source_id`, `properties`, and **`markdown`** (single request; no block append).
5. **Content SHA**: If that column exists and its value matches the **sync fingerprint**, the run **skips** the markdown `PATCH` (unless **`--force`**), but still **`pages.update`**s metadata. The fingerprint includes the file text, optional **`NOTION_DOC_LINK_BASE`**, and a **link-resolution hash** (which targets resolved to a Notion page id vs GitHub vs missing) so when another doc appears in Notion, the next run can refresh links without a manual `--force` in many cases.
6. **Cross-links (inline `](...)` only):** For each repo-relative `.md` link, the script **queries** the same database (Doc ID, else Local Path). **Found** → substitute **`https://www.notion.so/{pageId}`** (no hyphens). **Not found** and **`NOTION_DOC_LINK_BASE`** set → GitHub URL for that path. **Not found** and no base → link stays relative; path is listed under **Missing in Notion (not uploaded):**. Non-`.md` or non-file hrefs are unchanged; `http(s):`, `mailto:`, etc. are unchanged. Reference-style links (`[ref]: url`) are not rewritten.
7. **Stdout:** After each primary or closure sync, the script prints **`Link resolution:`** (counts; optional paths with **`-v`**), **`Left relative`** (only when **`NOTION_DOC_LINK_BASE`** is unset), and **`Targets not in Notion yet (pass --upload-missing to upsert):`** — the union of GitHub-fallback and relative targets that still need a Notion row. With **`NOTION_DOC_LINK_BASE`**, another doc may show as GitHub fallback rather than “missing”; it still appears in **Targets not in Notion yet** so **`--upload-missing`** can create it. The **script** does not prompt on stdin; flags are for automation. When using this skill **interactively**, follow **Agent workflow** below.

Uses API version **`2026-03-11`**. There is no block-builder fallback — if the markdown endpoints fail, fix capabilities or errors from the API instead.

## Agent workflow (interactive)

When you run an upsert for the user and the output shows **`Targets not in Notion yet`** with one or more paths (not **`(none)`**):

1. **Do not** stop after only pasting the command they could run.
2. **Ask** whether they want to upload those linked files to Notion now and re-sync the primary doc so links use Notion URLs (e.g. “Upload these linked docs and refresh this page? Yes / No”).
3. If **yes**, run the **same** markdown path again with **`--upload-missing --closure`** from the repo root:

   ```bash
   uv run python .cursor/skills/doc-upsert/scripts/notion_doc_upsert.py <same-path.md> --upload-missing --closure
   ```

4. If **no**, briefly note that links may stay on GitHub fallback until they run that later or upload those files manually.

If **`Targets not in Notion yet`** is **`(none)`**, no upload question is needed.

## Automation (CI / non-interactive)

- Use **`--upload-missing`** and **`--closure`** directly in scripts or jobs when you want batch behavior without a human confirmation.
- Use **`NOTION_UPLOAD_MISSING=1`** (or **`NOTION_LINK_TARGET_STRICT`**) when appropriate; **`--no-upload-missing`** overrides env batch upload.
- Use **`--strict-links`** when a missing Notion row should **fail** the job (after the primary file still syncs).

## Security

The integration token grants access to every database you connect it to. Rotate the secret if it leaks.
