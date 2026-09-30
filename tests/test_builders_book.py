"""
AL-BURAQ — The Builders Book Integration & Verification Test Suite
==================================================================
Tests ingestion, prompt injection, parameter aliasing, chapter lookups,
and search capabilities for The Builders Book (Ahmad Odeh & Qadir).
"""
import json
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import server
from server import app
from builders_book import BuildersBook
from agent_loop import AgentLoop
from memory import MemoryStore


def test_builders_book_structure_and_chapters():
    book = BuildersBook()
    chapters = book.list_chapters()
    assert len(chapters) == 11

    # Verify Chapter 1: Law of the Probe
    ch1 = book.get_chapter(1)
    assert ch1 is not None
    assert "Law of the Probe" in ch1["title"]
    assert any("Nothing is true until a probe says so" in r for r in ch1["rules"])

    # Verify Chapter 10: Working with Claude
    ch10 = book.get_chapter(10)
    assert ch10 is not None
    assert any("Smallest change that turns the probe green" in r for r in ch10["rules"])

    # Verify Chapter 11: Meta-Patterns
    ch11 = book.get_chapter(11)
    assert ch11 is not None
    assert any("Receipts culture" in r for r in ch11["rules"])


def test_builders_book_search():
    book = BuildersBook()

    # Search for "probe"
    probe_results = book.search("probe")
    assert len(probe_results) >= 3

    # Search for "vram"
    vram_results = book.search("VRAM")
    assert len(vram_results) >= 1
    assert any(m["chapter"] == 2 for m in vram_results)

    # Search for "receipt"
    receipt_results = book.search("receipt")
    assert len(receipt_results) >= 2


def test_builders_book_memory_ingestion(tmp_path):
    mem = MemoryStore(tmp_path)
    book = BuildersBook(tmp_path)
    count = book.ingest_into_memory(mem)
    assert count == 12  # 11 chapters in L4 + 1 axioms entry in L3

    # Verify L4 Vault entries
    l4_entries = mem.list_layer("L4")
    assert len(l4_entries) == 11
    assert any("Law of the Probe" in e["title"] for e in l4_entries)

    # Verify L3 Axioms entry
    l3_axioms = mem.get_by_key("core_builders_axioms", layer="L3")
    assert l3_axioms is not None
    assert "THE LAW OF THE PROBE" in l3_axioms["content"]


def test_agent_loop_builders_book_tool_and_learned_md(tmp_path):
    loop = AgentLoop(tmp_path)

    # Query Builders Book via agent tool
    res = loop.run("Look up Chapter 1 of the Builders Book", session_id="book_test_1")
    assert res["ok"] is True
    assert "Law of the Probe" in res["reply"] or "probe" in res["reply"].lower()

    # Verify LEARNED.md was updated on turn completion
    learned_file = tmp_path / "LEARNED.md"
    assert learned_file.exists()
    assert "book_test_1" in learned_file.read_text()


def test_builders_book_api_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA", tmp_path / "data")
    monkeypatch.setattr(server, "SIGNAL_PATH", tmp_path / "data" / "logs" / "signal.jsonl")
    (tmp_path / "data" / "logs").mkdir(parents=True, exist_ok=True)

    with TestClient(app) as c:
        # Chapters
        r_ch = c.get("/api/builders-book/chapters")
        assert r_ch.status_code == 200
        assert len(r_ch.json()["chapters"]) == 11

        # Specific chapter
        r_ch3 = c.get("/api/builders-book/chapter/3")
        assert r_ch3.status_code == 200
        assert "Building Agents That Actually Execute" in r_ch3.json()["chapter"]["title"]

        # Search
        r_srch = c.get("/api/builders-book/search?q=probe")
        assert r_srch.status_code == 200
        assert r_srch.json()["count"] >= 3

        # Axioms
        r_ax = c.get("/api/builders-book/axioms")
        assert r_ax.status_code == 200
        assert "LAW OF THE PROBE" in r_ax.json()["axioms"]

        # Boot report contains builders book status
        r_boot = c.get("/api/boot/report")
        assert r_boot.status_code == 200
        assert r_boot.json()["builders_book"]["status"] == "ingrained"
