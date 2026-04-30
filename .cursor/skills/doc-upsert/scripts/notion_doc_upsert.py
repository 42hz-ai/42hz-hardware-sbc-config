#!/usr/bin/env python3
"""Upsert a local markdown doc into a Notion database (Doc ID = filename stem)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click
import yaml

from notion_client import Client
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Markdown create/update requires this version (see Notion "Working with markdown content").
NOTION_API_VERSION = "2026-03-11"

DEFAULT_DATABASE_ID = "32aeef158f0e8027a879c35c8fd65fe2"

FILENAME_RE = re.compile(
    r"^(?P<repo>[A-Z0-9]{4,5})-(?P<prefix>INFRA|CODE)-(?P<num>\d{4})-(?P<slug>.+)\.md$",
    re.IGNORECASE,
)

# Inline markdown links: ](destination) — destination may include optional "title".
MD_LINK_RE = re.compile(r"\]\(([^)]+)\)")


class NotionDocSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    notion_token: str = Field(validation_alias="NOTION_TOKEN")
    notion_database_id: str = Field(
        default=DEFAULT_DATABASE_ID, validation_alias="NOTION_DATABASE_ID"
    )
    notion_project: str | None = Field(default=None, validation_alias="NOTION_PROJECT")
    notion_doc_link_base: str | None = Field(
        default=None,
        validation_alias="NOTION_DOC_LINK_BASE",
        description=(
            "Optional URL prefix for repo-relative links in markdown (e.g. "
            "https://github.com/org/repo/blob/main). When set, relative links "
            "are rewritten to absolute URLs for Notion."
        ),
    )
    notion_upload_missing: bool = Field(
        default=False,
        validation_alias="NOTION_UPLOAD_MISSING",
        description="If true, same as --upload-missing unless overridden by CLI.",
    )
    notion_link_target_strict: bool = Field(
        default=False,
        validation_alias="NOTION_LINK_TARGET_STRICT",
        description="If true, same as --strict-links unless overridden by CLI.",
    )

    prop_name: str = Field(default="Name", validation_alias="NOTION_PROP_NAME")
    prop_doc_id: str = Field(default="Doc ID", validation_alias="NOTION_PROP_DOC_ID")
    prop_repo_id: str = Field(default="REPO_ID", validation_alias="NOTION_PROP_REPO_ID")
    prop_prefix: str = Field(default="PREFIX", validation_alias="NOTION_PROP_PREFIX")
    prop_doc_number: str = Field(
        default="Doc Number", validation_alias="NOTION_PROP_DOC_NUMBER"
    )
    prop_project: str = Field(default="Project", validation_alias="NOTION_PROP_PROJECT")
    prop_local_path: str = Field(
        default="Local Path", validation_alias="NOTION_PROP_LOCAL_PATH"
    )
    prop_content_sha: str = Field(
        default="Content SHA", validation_alias="NOTION_PROP_CONTENT_SHA"
    )


def make_client(settings: NotionDocSettings) -> Client:
    return Client(auth=settings.notion_token, notion_version=NOTION_API_VERSION)


def find_repo_root(start: Path) -> Path:
    resolved = start.resolve()
    for p in [resolved, *list(resolved.parents)]:
        if (p / "pyproject.toml").exists() or (p / ".copier-answers.yml").exists():
            return p
    return start.resolve().parent


def read_repository_slug(repo_root: Path) -> str | None:
    answers = repo_root / ".copier-answers.yml"
    if not answers.is_file():
        return None
    data = yaml.safe_load(answers.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    val = data.get("repository_slug")
    return str(val) if val else None


def parse_filename(stem: str) -> tuple[str, str, str, str]:
    m = FILENAME_RE.match(f"{stem}.md")
    if not m:
        msg = (
            f"Filename stem {stem!r} does not match "
            "{{REPO_ID}}-{INFRA|CODE}-{NNNN}-{kebab-slug}.md"
        )
        raise ValueError(msg)
    repo = m.group("repo").upper()
    prefix = m.group("prefix").upper()
    num = m.group("num")
    return repo, prefix, num, m.group("slug")


def first_heading_title(markdown: str) -> str | None:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or None
    return None


def sha256_hex_of_utf8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_sha_value(hex_digest: str) -> str:
    return f"sha256:{hex_digest}"


def fingerprint_for_sync(body: str, link_base: str | None, link_state_part: str) -> str:
    """Sync fingerprint: file text, optional link base, and link-resolution state."""
    parts = [body, f"LINK_STATE={link_state_part}"]
    if link_base:
        parts.append(f"NOTION_DOC_LINK_BASE={link_base}")
    return "\x00".join(parts)


def notion_public_page_url(page_id: str) -> str:
    """Public Notion URL for a page UUID (hyphens stripped)."""
    raw = page_id.replace("-", "")
    return f"https://www.notion.so/{raw}"


def is_non_repo_href(href: str) -> bool:
    h = href.strip()
    if not h or h.startswith("#"):
        return True
    low = h.lower()
    return low.startswith(
        (
            "http://",
            "https://",
            "mailto:",
            "tel:",
            "data:",
            "notion://",
            "ftp://",
            "//",
        ),
    )


def split_link_inner(inner: str) -> tuple[str, str]:
    """Split ](inner) into path/fragment part and optional ` "title"` suffix."""
    s = inner.strip()
    if m := re.match(r"^(.*?)(\s+\"[^\"]*\")$", s):
        return m.group(1).strip(), m.group(2)
    return s, ""


def join_doc_link_base(base: str, rel_under_root: Path) -> str:
    b = base.rstrip("/")
    return f"{b}/{rel_under_root.as_posix()}"


def candidate_md_path_for_href(  # noqa: PLR0911
    head: str,
    *,
    md_path: Path,
    repo_root: Path,
) -> tuple[Path, str] | None:
    """If href points at a file under repo_root, return (absolute path, fragment suffix)."""
    head = head.strip()
    if not head:
        return None
    if head.startswith("<") and head.endswith(">"):
        head = head[1:-1].strip()
    if is_non_repo_href(head):
        return None
    path_part = head
    if "#" in path_part:
        path_only, frag = path_part.split("#", 1)
        frag = "#" + frag
    else:
        path_only, frag = path_part, ""
    if "?" in path_only:
        path_only = path_only.split("?", maxsplit=1)[0]
    path_only = path_only.strip()
    if not path_only:
        return None
    root = repo_root.resolve()
    if path_only.startswith("/"):
        candidate = (root / path_only.lstrip("/")).resolve()
    else:
        candidate = (md_path.parent / path_only).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    if candidate.suffix.lower() != ".md":
        return None
    return candidate, frag


def try_rewrite_href_head(
    head: str,
    *,
    md_path: Path,
    repo_root: Path,
    link_base: str,
) -> str | None:
    """If head is repo-relative and resolves to a file under repo_root, return absolute URL."""
    got = candidate_md_path_for_href(head, md_path=md_path, repo_root=repo_root)
    if got is None:
        return None
    candidate, frag = got
    rel = candidate.resolve().relative_to(repo_root.resolve())
    return join_doc_link_base(link_base, rel) + frag


def rewrite_markdown_repo_links(
    markdown: str,
    *,
    md_path: Path,
    repo_root: Path,
    link_base: str,
) -> str:
    """Rewrite ](relative) targets that point at files under repo_root to link_base URLs."""

    def repl(m: re.Match[str]) -> str:
        inner = m.group(1)
        head, title_suffix = split_link_inner(inner)
        new_head = try_rewrite_href_head(
            head,
            md_path=md_path,
            repo_root=repo_root,
            link_base=link_base,
        )
        if new_head is None:
            return m.group(0)
        return f"]({new_head}{title_suffix})"

    return MD_LINK_RE.sub(repl, markdown)


@dataclass
class LinkResolution:
    """Result of rewriting inline links for one markdown file."""

    markdown: str
    link_state_part: str
    missing_relpaths: list[str] = field(default_factory=list)
    resolved_notion: list[str] = field(default_factory=list)
    resolved_github: list[str] = field(default_factory=list)


def query_page_id_for_target(
    client: Client,
    data_source_id: str,
    schema: dict[str, str],
    settings: NotionDocSettings,
    target_rel: Path,
    cache: dict[str, str | None],
) -> str | None:
    """Return Notion page id for a repo-relative markdown path, or None."""
    key = target_rel.as_posix()
    if key in cache:
        return cache[key]
    stem = target_rel.stem
    local_path = str(target_rel).replace("\\", "/")
    flt = upsert_filter(
        settings,
        schema,
        stem=stem,
        local_path=local_path,
    )
    resp = client.data_sources.query(
        data_source_id=data_source_id,
        filter=flt,
        page_size=1,
    )
    results = resp.get("results") or []
    if not results:
        cache[key] = None
        return None
    pid = str(results[0]["id"])
    cache[key] = pid
    return pid


def build_link_state_part(entries: list[tuple[str, str, str]]) -> str:
    """Stable hash from sorted (relpath, kind, detail) tuples."""
    payload = json.dumps(sorted(entries), sort_keys=True, separators=(",", ":"))
    return sha256_hex_of_utf8(payload)


def rewrite_markdown_with_cross_links(
    body_raw: str,
    *,
    md_path: Path,
    repo_root: Path,
    client: Client,
    data_source_id: str,
    schema: dict[str, str],
    settings: NotionDocSettings,
    link_base: str | None,
    cache: dict[str, str | None],
) -> LinkResolution:
    """Prefer Notion page URLs, then GitHub, else leave relative and record missing."""
    missing: list[str] = []
    notion_paths: list[str] = []
    gh_paths: list[str] = []
    state_entries: list[tuple[str, str, str]] = []

    def repl(m: re.Match[str]) -> str:
        inner = m.group(1)
        head, title_suffix = split_link_inner(inner)
        got = candidate_md_path_for_href(head, md_path=md_path, repo_root=repo_root)
        if got is None:
            return m.group(0)
        candidate, frag = got
        rel = candidate.resolve().relative_to(repo_root.resolve())
        rel_pos = rel.as_posix()

        page_id = query_page_id_for_target(
            client,
            data_source_id,
            schema,
            settings,
            rel,
            cache,
        )
        if page_id:
            nu = notion_public_page_url(page_id) + frag
            notion_paths.append(rel_pos)
            state_entries.append((rel_pos, "notion", page_id.replace("-", "")))
            return f"]({nu}{title_suffix})"

        if link_base:
            gh = join_doc_link_base(link_base, rel) + frag
            gh_paths.append(rel_pos)
            state_entries.append((rel_pos, "github", link_base))
            return f"]({gh}{title_suffix})"

        missing.append(rel_pos)
        state_entries.append((rel_pos, "missing", ""))
        return m.group(0)

    out = MD_LINK_RE.sub(repl, body_raw)
    link_state_part = build_link_state_part(state_entries)
    return LinkResolution(
        markdown=out,
        link_state_part=link_state_part,
        missing_relpaths=sorted(set(missing)),
        resolved_notion=sorted(set(notion_paths)),
        resolved_github=sorted(set(gh_paths)),
    )


def rich_text_property_plain(prop: dict[str, Any] | None) -> str:
    if not prop or prop.get("type") != "rich_text":
        return ""
    parts: list[str] = []
    for seg in prop.get("rich_text") or []:
        if seg.get("type") == "text":
            parts.append(seg.get("text", {}).get("content") or "")
    return "".join(parts).strip()


def stored_content_sha(page: dict[str, Any], prop_name: str) -> str | None:
    props = page.get("properties") or {}
    raw = props.get(prop_name)
    if not isinstance(raw, dict):
        return None
    s = rich_text_property_plain(raw)
    return s if s else None


def content_sha_matches(stored: str | None, file_sha: str) -> bool:
    if stored is None:
        return False
    return stored.strip().lower() == file_sha.strip().lower()


def rich_text_prop(text: str) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]}


def title_prop(text: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": text[:2000]}}]}


def select_prop(name: str | None) -> dict[str, Any]:
    if name:
        return {"select": {"name": name}}
    return {"select": None}


def load_data_source_schema(client: Client, data_source_id: str) -> dict[str, str]:
    """Property name -> Notion type (title, rich_text, select, ...)."""
    ds = client.data_sources.retrieve(data_source_id=data_source_id)
    props = ds.get("properties") or {}
    return {str(n): (meta.get("type") or "") for n, meta in props.items()}


def build_properties(
    settings: NotionDocSettings,
    schema: dict[str, str],
    *,
    title: str,
    doc_id_stem: str,
    repo_id: str,
    prefix: str,
    doc_number: str,
    project: str | None,
    local_path: str,
    content_sha: str | None = None,
) -> dict[str, Any]:
    """Only set properties that exist on the data source (names + types must match)."""
    props: dict[str, Any] = {}

    pn = settings.prop_name
    if pn in schema and schema[pn] == "title":
        props[pn] = title_prop(title)

    pid = settings.prop_doc_id
    if pid in schema and schema[pid] == "rich_text":
        props[pid] = rich_text_prop(doc_id_stem)

    pr = settings.prop_repo_id
    if pr in schema and schema[pr] == "rich_text":
        props[pr] = rich_text_prop(repo_id)

    pp = settings.prop_prefix
    if pp in schema and schema[pp] == "select":
        props[pp] = select_prop(prefix)

    pnum = settings.prop_doc_number
    if pnum in schema and schema[pnum] == "rich_text":
        props[pnum] = rich_text_prop(doc_number)

    pl = settings.prop_local_path
    if pl in schema and schema[pl] == "rich_text":
        props[pl] = rich_text_prop(local_path)

    pj = settings.prop_project
    if pj in schema:
        if schema[pj] == "select":
            props[pj] = select_prop(project)
        elif schema[pj] == "rich_text":
            props[pj] = rich_text_prop(project or "")

    pcs = settings.prop_content_sha
    if content_sha is not None and pcs in schema and schema[pcs] == "rich_text":
        props[pcs] = rich_text_prop(content_sha)

    return props


def upsert_filter(
    settings: NotionDocSettings,
    schema: dict[str, str],
    *,
    stem: str,
    local_path: str,
) -> dict[str, Any]:
    """Prefer Doc ID match; fall back to Local Path when Doc ID column is absent."""
    doc_id_name = settings.prop_doc_id
    if doc_id_name in schema and schema[doc_id_name] == "rich_text":
        return {"property": doc_id_name, "rich_text": {"equals": stem}}
    local_name = settings.prop_local_path
    if local_name in schema and schema[local_name] == "rich_text":
        return {"property": local_name, "rich_text": {"equals": local_path}}
    msg = (
        "Need a rich-text upsert column: add 'Doc ID' or ensure 'Local Path' exists "
        "in the Notion database."
    )
    raise click.ClickException(msg)


def replace_page_markdown(client: Client, page_id: str, new_str: str) -> None:
    """Replace full page body via Notion enhanced markdown API (no block fallback)."""
    client.request(
        path=f"pages/{page_id}/markdown",
        method="PATCH",
        body={
            "type": "replace_content",
            "replace_content": {"new_str": new_str},
        },
    )


def create_page_with_markdown(
    client: Client,
    *,
    data_source_id: str,
    properties: dict[str, Any],
    markdown: str,
) -> dict[str, Any]:
    """Create a database row with properties and body in one request (`markdown` + parent)."""
    return client.request(
        path="pages",
        method="POST",
        body={
            "parent": {"data_source_id": data_source_id},
            "properties": properties,
            "markdown": markdown,
        },
    )


def resolve_data_source_id(client: Client, database_id: str) -> str:
    """Retrieve database and return its primary data source id (Notion API v2025 / notion-client 3.x)."""
    db_id = database_id.replace("-", "")
    db = client.databases.retrieve(database_id=db_id)
    sources = db.get("data_sources") or []
    if not sources:
        msg = f"Database {db_id!r} has no data_sources; connect the integration."
        raise RuntimeError(msg)
    first = sources[0]
    if not isinstance(first, dict) or "id" not in first:
        msg = f"Unexpected data_sources entry: {first!r}"
        raise RuntimeError(msg)
    return str(first["id"]).replace("-", "")


def run_ensure_schema() -> None:
    """Add Doc ID, REPO_ID, PREFIX, and Content SHA to the Notion data source when missing."""
    os.chdir(find_repo_root(Path.cwd()))
    settings = NotionDocSettings()
    client = make_client(settings)
    db_id = settings.notion_database_id.replace("-", "")
    data_source_id = resolve_data_source_id(client, db_id)
    schema = load_data_source_schema(client, data_source_id)

    to_add: dict[str, Any] = {}
    pid = settings.prop_doc_id
    if pid not in schema:
        to_add[pid] = {"rich_text": {}}

    pr = settings.prop_repo_id
    if pr not in schema:
        to_add[pr] = {"rich_text": {}}

    pp = settings.prop_prefix
    if pp not in schema:
        to_add[pp] = {
            "select": {
                "options": [
                    {"name": "INFRA", "color": "blue"},
                    {"name": "CODE", "color": "purple"},
                ],
            },
        }

    pcs = settings.prop_content_sha
    if pcs not in schema:
        to_add[pcs] = {"rich_text": {}}

    if not to_add:
        click.echo(
            "Notion data source already has Doc ID, REPO_ID, PREFIX, and Content SHA.",
        )
        return

    client.data_sources.update(data_source_id=data_source_id, properties=to_add)
    click.echo(f"Added properties: {', '.join(sorted(to_add.keys()))}")


def not_in_notion_relpaths(lr: LinkResolution) -> list[str]:
    """Paths that point at an on-disk .md with no Notion row yet (GitHub fallback or relative)."""
    return sorted(set(lr.missing_relpaths) | set(lr.resolved_github))


def print_link_resolution_report(
    lr: LinkResolution,
    *,
    verbose: bool,
) -> None:
    click.echo("")
    click.echo("Link resolution:")
    click.echo(f"  Resolved to Notion: {len(lr.resolved_notion)}")
    if verbose and lr.resolved_notion:
        for p in lr.resolved_notion:
            click.echo(f"    - {p}")
    click.echo(
        f"  Not in Notion yet (NOTION_DOC_LINK_BASE / GitHub fallback): "
        f"{len(lr.resolved_github)}",
    )
    if verbose and lr.resolved_github:
        for p in lr.resolved_github:
            click.echo(f"    - {p}")
    click.echo("  Left relative (no GitHub base; not in Notion):")
    if lr.missing_relpaths:
        for p in lr.missing_relpaths:
            click.echo(f"    - {p}")
    else:
        click.echo("    - (none)")
    pending = not_in_notion_relpaths(lr)
    click.echo("Targets not in Notion yet (pass --upload-missing to upsert):")
    if pending:
        for p in pending:
            click.echo(f"  {p}")
    else:
        click.echo("  (none)")


def sync_one_markdown_file(
    md_path: Path,
    *,
    repo_root: Path,
    settings: NotionDocSettings,
    client: Client,
    data_source_id: str,
    schema: dict[str, str],
    query_cache: dict[str, str | None],
    force: bool,
    skip_link_report: bool,
    verbose: bool,
) -> tuple[str, LinkResolution]:
    """Upsert one file; return (one-line result message, link resolution)."""
    rel = md_path.resolve().relative_to(repo_root.resolve())
    stem = md_path.stem

    repo_id, prefix, doc_number, _slug = parse_filename(stem)

    project = settings.notion_project or read_repository_slug(repo_root)
    body_raw = md_path.read_text(encoding="utf-8")
    title = first_heading_title(body_raw) or stem.replace("-", " ")

    local_path_str = str(rel).replace("\\", "/")
    link_base = settings.notion_doc_link_base

    lr = rewrite_markdown_with_cross_links(
        body_raw,
        md_path=md_path,
        repo_root=repo_root,
        client=client,
        data_source_id=data_source_id,
        schema=schema,
        settings=settings,
        link_base=link_base,
        cache=query_cache,
    )
    body_for_notion = lr.markdown

    file_sha = content_sha_value(
        sha256_hex_of_utf8(
            fingerprint_for_sync(body_raw, link_base, lr.link_state_part),
        ),
    )

    flt = upsert_filter(
        settings,
        schema,
        stem=stem,
        local_path=local_path_str,
    )

    query = client.data_sources.query(
        data_source_id=data_source_id,
        filter=flt,
    )
    results = query.get("results", [])

    line = ""
    if results:
        page_id = results[0]["id"]
        stored = stored_content_sha(results[0], settings.prop_content_sha)
        props = build_properties(
            settings,
            schema,
            title=title,
            doc_id_stem=stem,
            repo_id=repo_id,
            prefix=prefix,
            doc_number=doc_number,
            project=project,
            local_path=local_path_str,
            content_sha=file_sha,
        )
        if content_sha_matches(stored, file_sha) and not force:
            client.pages.update(page_id=page_id, properties=props)
            fv = flt.get("rich_text", {}).get("equals", "")
            line = (
                f"Skipped markdown (Content SHA matches); updated properties: {page_id} "
                f"({flt['property']}={fv!r})"
            )
        else:
            replace_page_markdown(client, page_id, body_for_notion)
            client.pages.update(page_id=page_id, properties=props)
            fv = flt.get("rich_text", {}).get("equals", "")
            line = f"Updated Notion page {page_id} ({flt['property']}={fv!r})"
    else:
        props = build_properties(
            settings,
            schema,
            title=title,
            doc_id_stem=stem,
            repo_id=repo_id,
            prefix=prefix,
            doc_number=doc_number,
            project=project,
            local_path=local_path_str,
            content_sha=file_sha,
        )
        page = create_page_with_markdown(
            client,
            data_source_id=data_source_id,
            properties=props,
            markdown=body_for_notion,
        )
        page_id = page["id"]
        fv = flt.get("rich_text", {}).get("equals", "")
        line = f"Created Notion page {page_id} ({flt['property']}={fv!r})"

    click.echo(line)
    if not skip_link_report:
        print_link_resolution_report(lr, verbose=verbose)

    return line, lr


@click.command()
@click.argument(
    "markdown_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
    default=None,
)
@click.option(
    "--ensure-schema",
    is_flag=True,
    help="Add Doc ID, REPO_ID, PREFIX, and Content SHA columns if missing.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Push body and refresh Content SHA even when the file hash matches Notion.",
)
@click.option(
    "--upload-missing",
    is_flag=True,
    help="After the primary file, upsert each linked .md that exists on disk but not in Notion.",
)
@click.option(
    "--no-upload-missing",
    is_flag=True,
    help="Never upload missing linked files (overrides NOTION_UPLOAD_MISSING=1).",
)
@click.option(
    "--closure",
    is_flag=True,
    help="After --upload-missing upserts at least one linked file, re-sync the primary page.",
)
@click.option(
    "--strict-links",
    is_flag=True,
    help="Exit with code 1 if any in-repo .md link target is missing in Notion (after primary sync).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="List each path resolved to Notion or GitHub under Link resolution.",
)
def main(
    markdown_path: Path | None,
    ensure_schema: bool,
    force: bool,
    upload_missing: bool,
    no_upload_missing: bool,
    closure: bool,
    strict_links: bool,
    verbose: bool,
) -> None:
    if ensure_schema:
        if markdown_path is not None:
            raise click.UsageError("Do not pass a markdown path with --ensure-schema.")
        run_ensure_schema()
        return
    if markdown_path is None:
        raise click.UsageError("Pass a markdown file or use --ensure-schema.")

    md_path = markdown_path.resolve()
    repo_root = find_repo_root(md_path.parent)
    os.chdir(repo_root)
    settings = NotionDocSettings()

    do_upload_missing = (
        settings.notion_upload_missing or upload_missing
    ) and not no_upload_missing
    do_strict = settings.notion_link_target_strict or strict_links

    if closure and not do_upload_missing:
        raise click.UsageError(
            "--closure requires uploading missing (use --upload-missing or NOTION_UPLOAD_MISSING=1).",
        )

    client = make_client(settings)
    db_id = settings.notion_database_id.replace("-", "")
    data_source_id = resolve_data_source_id(client, db_id)
    schema = load_data_source_schema(client, data_source_id)
    query_cache: dict[str, str | None] = {}

    _, lr_primary = sync_one_markdown_file(
        md_path,
        repo_root=repo_root,
        settings=settings,
        client=client,
        data_source_id=data_source_id,
        schema=schema,
        query_cache=query_cache,
        force=force,
        skip_link_report=False,
        verbose=verbose,
    )

    if do_strict and not_in_notion_relpaths(lr_primary):
        click.echo(
            "strict-links: one or more link targets are not in Notion (see above).",
            err=True,
        )
        sys.exit(1)

    uploaded_a_linked_file = False
    if do_upload_missing and not_in_notion_relpaths(lr_primary):
        for rel_s in not_in_notion_relpaths(lr_primary):
            dep = (repo_root / rel_s).resolve()
            if not dep.is_file():
                continue
            click.echo("")
            click.echo(f"--- Uploading missing linked file: {rel_s} ---")
            try:
                sync_one_markdown_file(
                    dep,
                    repo_root=repo_root,
                    settings=settings,
                    client=client,
                    data_source_id=data_source_id,
                    schema=schema,
                    query_cache=query_cache,
                    force=False,
                    skip_link_report=True,
                    verbose=verbose,
                )
            except ValueError as exc:
                click.echo(
                    f"Skipped (filename must match doc-create pattern): {exc}",
                    err=True,
                )
            else:
                query_cache.pop(rel_s, None)
                uploaded_a_linked_file = True

    if closure and do_upload_missing:
        if uploaded_a_linked_file:
            query_cache.clear()
            click.echo("")
            click.echo(
                "--- Closure: re-syncing primary file for Notion-internal links ---"
            )
            sync_one_markdown_file(
                md_path,
                repo_root=repo_root,
                settings=settings,
                client=client,
                data_source_id=data_source_id,
                schema=schema,
                query_cache=query_cache,
                force=True,
                skip_link_report=False,
                verbose=verbose,
            )
        else:
            click.echo("")
            click.echo(
                "Closure skipped (no linked files were uploaded this run; "
                "primary links already resolve in Notion).",
            )


if __name__ == "__main__":
    main()
