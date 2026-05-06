"""LanguageAwareChunker — pure unit tests."""

from __future__ import annotations

from pathlib import Path

from mcp_phone_controll.data.chunker import LanguageAwareChunker, language_for


def test_language_detection():
    assert language_for(Path("a.dart")) == "dart"
    assert language_for(Path("b.py")) == "python"
    assert language_for(Path("c.md")) == "markdown"
    assert language_for(Path("d.unknown")) == "text"


def test_markdown_splits_on_headings(tmp_path: Path):
    md = (
        "# Top\n"
        "intro paragraph that is reasonably long, more than the floor.\n"
        "another line so the chunk passes the min-size filter.\n\n"
        "# Section A\n"
        "body of section A which is also long enough to clear the threshold.\n"
        "again, padding the body to ensure the chunker keeps it.\n\n"
        "# Section B\n"
        "body B with similar generous length so we hit the min-chunk size.\n"
        "more padding for the section so the chunk is kept by the filter.\n"
    )
    chunks = LanguageAwareChunker().chunk(md, Path("doc.md"))
    assert len(chunks) >= 2
    # Heading should appear at the top of each chunk after the first.
    assert any("Section A" in c.text for c in chunks)
    assert any("Section B" in c.text for c in chunks)


def test_dart_splits_on_class_boundaries():
    dart = """
import 'package:flutter/material.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(body: const Center(child: Text('home')));
  }
}

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}
"""
    chunks = LanguageAwareChunker().chunk(dart, Path("page.dart"))
    assert any("HomePage" in c.text for c in chunks)
    assert any("SettingsPage" in c.text for c in chunks)


def test_python_splits_on_def_class():
    # Each block must clear the 80-char minimum chunk size; bulk them up.
    py = """
def alpha():
    # alpha-implementation that is long enough to clear the chunker floor
    # so the assertion below can locate it after splitting.
    value = 1
    return value

def beta(x):
    # do work that requires a sufficient body length so the chunk
    # passes the minimum-size filter applied by the chunker.
    return x * 2

class Gamma:
    def method(self):
        # gamma method body that is long enough to clear the floor and
        # produce a separate chunk anchored on the class definition.
        return "gamma"
"""
    chunks = LanguageAwareChunker().chunk(py, Path("m.py"))
    assert any("alpha" in c.text for c in chunks)
    assert any("Gamma" in c.text for c in chunks)


def test_unknown_language_falls_back_to_fixed_window():
    text = "x" * 2000
    chunks = LanguageAwareChunker(chunk_chars=600, overlap=100).chunk(
        text, Path("blob.bin")
    )
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c.text) <= 600
