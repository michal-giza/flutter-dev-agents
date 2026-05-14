"""`.mcpignore` reader + default credential exclusions in `index_project`.

Closes a real security risk: agents indexing a Flutter project would
otherwise vacuum up .env / firebase-adminsdk*.json / *.keystore
files into the RAG index, where any later `recall` could surface
them.
"""

from __future__ import annotations

from pathlib import Path

from mcp_phone_controll.domain.usecases.recall import (
    IndexProjectParams,
    _read_mcpignore,
    _walk,
)


def test_mcpignore_reader_strips_comments_and_blanks(tmp_path: Path):
    (tmp_path / ".mcpignore").write_text(
        "# this is a comment\n"
        "\n"
        "*.secret\n"
        "internal/**\n"
        "  trim-me  \n"
    )
    patterns = _read_mcpignore(tmp_path)
    assert "**/*.secret" in patterns
    assert "**/internal/**" in patterns
    assert "**/trim-me" in patterns


def test_mcpignore_missing_file_returns_empty(tmp_path: Path):
    assert _read_mcpignore(tmp_path) == ()


def test_default_excludes_block_credential_files(tmp_path: Path):
    """The default exclude_globs in IndexProjectParams must catch the
    obvious credential filenames so an agent can't index them."""
    project = tmp_path
    (project / ".env").write_text("API_KEY=secret")
    (project / ".env.production").write_text("PROD=secret")
    (project / "service-account.json").write_text('{"private_key": "x"}')
    (project / "firebase-adminsdk-abcde.json").write_text('{"x": 1}')
    (project / "google-services.json").write_text("{}")
    (project / "release.keystore").write_text("BINARY")
    # Plus a real Markdown that SHOULD be indexed.
    (project / "README.md").write_text("# project")

    defaults = IndexProjectParams(project_path=project)
    paths = list(
        _walk(project, defaults.include_globs, defaults.exclude_globs)
    )
    names = {p.name for p in paths}
    assert "README.md" in names
    # No credential file may slip through.
    for forbidden in (
        ".env", ".env.production", "service-account.json",
        "firebase-adminsdk-abcde.json", "google-services.json",
        "release.keystore",
    ):
        assert forbidden not in names, f"{forbidden} leaked into index"


def test_mcpignore_extends_defaults(tmp_path: Path):
    """User-provided `.mcpignore` patterns are added on top of defaults."""
    project = tmp_path
    (project / "TODO.md").write_text("# todo")
    (project / "scratch.md").write_text("# scratch")
    (project / ".mcpignore").write_text("scratch.md\n")
    extra = _read_mcpignore(project)
    defaults = IndexProjectParams(project_path=project)
    paths = list(_walk(project, defaults.include_globs, defaults.exclude_globs + extra))
    names = {p.name for p in paths}
    assert "TODO.md" in names
    assert "scratch.md" not in names
