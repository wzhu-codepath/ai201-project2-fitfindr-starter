"""Tests for planning_loop conditional branching and session state persistence."""

from __future__ import annotations

import planning_loop
from utils.data_loader import get_example_wardrobe


def test_needs_clarification_when_required_input_missing() -> None:
    result = planning_loop.run_planning_loop(original_query="help me find something")

    print("\n[DEBUG] clarification branch")
    print(f"[DEBUG] status={result.get('status')}")
    print(f"[DEBUG] missing_fields={result.get('missing_fields')}")
    print(f"[DEBUG] question={result.get('question')}")

    assert result["status"] == "needs_clarification"
    assert "missing_fields" in result
    assert "question" in result


def test_impossible_query_branches_no_match_and_skips_suggest(monkeypatch) -> None:
    suggest_called = {"value": False}

    def tracking_suggest_outfit(new_item: dict, wardrobe: dict) -> dict:
        suggest_called["value"] = True
        raise AssertionError("suggest_outfit should not run when search has zero matches")

    monkeypatch.setattr(planning_loop, "suggest_outfit", tracking_suggest_outfit)

    result = planning_loop.run_planning_loop(
        original_query="Find me an impossible item",
        description="neon holographic cyberpunk boots",
        size="W12",
        max_price=10.0,
        wardrobe=get_example_wardrobe(),
    )

    print("\n[DEBUG] no-match branch")
    print(f"[DEBUG] status={result.get('status')}, path={result.get('path')}")
    print(f"[DEBUG] suggest_called={suggest_called['value']}")
    print(f"[DEBUG] search_request={result.get('state', {}).get('search_request')}")

    assert result["status"] == "complete"
    assert result["path"] == "no_match"
    assert suggest_called["value"] is False


def test_returns_fit_card_when_ready(monkeypatch) -> None:
    def fake_search_listings(description: str, size: str, max_price: float) -> dict:
        return {
            "query_summary": {
                "description": description,
                "size": size,
                "max_price": max_price,
                "style_keywords": ["vintage"],
            },
            "matches": [
                {
                    "id": "lst_001",
                    "title": "Vintage Tee",
                    "description": "desc",
                    "category": "tops",
                    "style_tags": ["vintage"],
                    "size": "L",
                    "condition": "good",
                    "price": 25.0,
                    "colors": ["black"],
                    "brand": "brand",
                    "platform": "depop",
                    "match_score": 0.95,
                }
            ],
            "match_count": 1,
        }

    def fake_suggest_outfit(new_item: dict, wardrobe: dict) -> dict:
        return {
            "selected_new_item": new_item,
            "outfit": {
                "core_item": new_item,
                "paired_items": [],
                "missing_categories": ["shoes"],
                "styling_notes": ["Keep it simple."],
            },
            "confidence": 0.8,
        }

    def fake_create_fit_card(outfit: dict) -> dict:
        return {
            "fit_title": "Test Fit",
            "hero_item": {"id": "lst_001", "title": "Vintage Tee", "price": 25.0, "platform": "depop", "size": "L", "condition": "good"},
            "style_recipe": ["Step 1: Keep it simple."],
            "wardrobe_pairings": [],
            "warnings": [],
            "ready": True,
        }

    monkeypatch.setattr(planning_loop, "search_listings", fake_search_listings)
    monkeypatch.setattr(planning_loop, "suggest_outfit", fake_suggest_outfit)
    monkeypatch.setattr(planning_loop, "create_fit_card", fake_create_fit_card)

    result = planning_loop.run_planning_loop(
        original_query="vintage tee size L under $30",
        wardrobe=get_example_wardrobe(),
    )

    print("\n[DEBUG] happy path")
    print(f"[DEBUG] status={result.get('status')}, path={result.get('path')}")
    print(f"[DEBUG] listing_id={result.get('state', {}).get('listing', {}).get('id')}")
    print(f"[DEBUG] outfit_present={result.get('state', {}).get('outfit') is not None}")
    print(f"[DEBUG] fit_card_ready={result.get('state', {}).get('fit_card', {}).get('ready')}")

    assert result["status"] == "complete"
    assert result["path"] == "fit_card"

    state = result["state"]
    assert state["original_query"] == "vintage tee size L under $30"
    assert state["listing"] is not None
    assert state["outfit"] is not None
    assert state["fit_card"] is not None


def test_listing_only_fallback_when_outfit_fails(monkeypatch) -> None:
    def fake_suggest_outfit(new_item: dict, wardrobe: dict) -> dict:
        raise RuntimeError("outfit unavailable")

    monkeypatch.setattr(planning_loop, "suggest_outfit", fake_suggest_outfit)

    result = planning_loop.run_planning_loop(
        original_query="vintage tee size L under $30",
        wardrobe=get_example_wardrobe(),
    )

    print("\n[DEBUG] outfit failure branch")
    print(f"[DEBUG] status={result.get('status')}, path={result.get('path')}")
    print(f"[DEBUG] error_log={result.get('state', {}).get('error_log')}")

    assert result["status"] == "complete"
    assert result["path"] == "listing_only_fallback"


def test_plain_text_fallback_when_card_not_ready(monkeypatch) -> None:
    def fake_create_fit_card(outfit: dict) -> dict:
        return {
            "fit_title": "Not ready",
            "hero_item": {},
            "style_recipe": [],
            "wardrobe_pairings": [],
            "warnings": ["missing fields"],
            "ready": False,
        }

    monkeypatch.setattr(planning_loop, "create_fit_card", fake_create_fit_card)

    result = planning_loop.run_planning_loop(
        original_query="vintage tee size L under $30",
        wardrobe=get_example_wardrobe(),
    )

    print("\n[DEBUG] card-not-ready branch")
    print(f"[DEBUG] status={result.get('status')}, path={result.get('path')}")
    print(f"[DEBUG] styling_notes={result.get('styling_notes')}")

    assert result["status"] == "complete"
    assert result["path"] == "plain_text_fallback"
