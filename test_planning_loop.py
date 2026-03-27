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


def test_empty_wardrobe_provides_generic_styling_guidance(monkeypatch) -> None:
    """Test that empty wardrobe doesn't crash and provides useful generic styling notes."""
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

    monkeypatch.setattr(planning_loop, "search_listings", fake_search_listings)

    from utils.data_loader import get_empty_wardrobe
    result = planning_loop.run_planning_loop(
        original_query="vintage tee size L under $30",
        wardrobe=get_empty_wardrobe(),
    )

    print("\n[DEBUG] empty-wardrobe branch")
    print(f"[DEBUG] status={result.get('status')}, path={result.get('path')}")
    print(f"[DEBUG] outfit={result.get('state', {}).get('outfit')}")
    print(f"[DEBUG] styling_notes={result.get('styling_notes')}")
    print(f"[DEBUG] confidence={result.get('state', {}).get('outfit', {}).get('_outfit_confidence')}")

    assert result["status"] == "complete"
    # Should complete even with empty wardrobe (may return fit_card with generic guidance)
    assert result["path"] in ["fit_card", "plain_text_fallback", "listing_only_fallback"]

    # Verify outfit exists and has useful styling notes
    outfit = result.get("state", {}).get("outfit", {})
    assert outfit is not None
    assert "styling_notes" in outfit
    styling_notes = outfit.get("styling_notes", [])
    assert isinstance(styling_notes, list)
    assert len(styling_notes) > 0

    # Verify styling notes are helpful (mention starting, anchoring, building, etc.)
    notes_text = " ".join(styling_notes).lower()
    assert any(keyword in notes_text for keyword in ["start", "anchor", "build", "focal", "simple"])

    # Verify paired_items is empty since wardrobe is empty
    assert "paired_items" in outfit
    assert outfit["paired_items"] == []

    # Verify missing_categories indicates what's needed (shows user what to add)
    assert "missing_categories" in outfit
    missing = outfit.get("missing_categories", [])
    assert isinstance(missing, list)
    assert len(missing) > 0  # Should identify that categories are missing


def test_incomplete_outfit_data_handled_gracefully(monkeypatch) -> None:
    """Test that create_fit_card handles incomplete/minimal outfit data without crashing."""
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

    def fake_create_fit_card(outfit: dict) -> dict:
        """Pass incomplete outfit: missing 'styling_notes' and 'missing_categories'."""
        from tools.create_fit_card import create_fit_card as real_create_fit_card
        # Call the real create_fit_card with incomplete data
        incomplete_outfit = {
            "core_item": outfit.get("core_item", {}),
            "paired_items": outfit.get("paired_items", []),
            # Intentionally missing: styling_notes, missing_categories
        }
        return real_create_fit_card(incomplete_outfit)

    monkeypatch.setattr(planning_loop, "search_listings", fake_search_listings)
    monkeypatch.setattr(planning_loop, "create_fit_card", fake_create_fit_card)

    result = planning_loop.run_planning_loop(
        original_query="vintage tee size L under $30",
        wardrobe=get_example_wardrobe(),
    )

    print("\n[DEBUG] incomplete-outfit branch")
    print(f"[DEBUG] status={result.get('status')}, path={result.get('path')}")
    fit_card = result.get("state", {}).get("fit_card", {})
    print(f"[DEBUG] fit_card={fit_card}")
    print(f"[DEBUG] warnings={fit_card.get('warnings')}")
    print(f"[DEBUG] ready={fit_card.get('ready')}")
    print(f"[DEBUG] styling_notes={result.get('styling_notes')}")

    assert result["status"] == "complete"
    # Incomplete outfit should cause fallback (plain_text_fallback) since fit_card.ready=False
    assert result["path"] == "plain_text_fallback"

    # Verify fit_card was created but marked as not ready
    assert isinstance(fit_card, dict)
    assert "warnings" in fit_card
    assert len(fit_card.get("warnings", [])) > 0

    # Verify warnings explain what's missing
    warnings_text = " ".join(fit_card.get("warnings", [])).lower()
    assert "missing" in warnings_text

    # Verify ready is False since required keys were missing
    assert fit_card.get("ready") is False

    # Verify it still has fallback content (not empty)
    assert fit_card.get("fit_title") is not None
    assert len(fit_card.get("fit_title", "")) > 0
    assert "hero_item" in fit_card
    assert "style_recipe" in fit_card

    # Verify plain text fallback provides styling notes from outfit
    assert "styling_notes" in result
    assert isinstance(result.get("styling_notes"), list)


def test_zero_results_provides_actionable_guidance(monkeypatch) -> None:
    """Test that impossible queries return specific refinement options, not generic failures."""
    def fake_search_listings(description: str, size: str, max_price: float) -> dict:
        """Simulate search with zero matches."""
        return {
            "query_summary": {
                "description": description,
                "size": size,
                "max_price": max_price,
                "style_keywords": [],
            },
            "matches": [],
            "match_count": 0,
        }

    monkeypatch.setattr(planning_loop, "search_listings", fake_search_listings)

    result = planning_loop.run_planning_loop(
        original_query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )

    print("\n[DEBUG] zero-results branch")
    print(f"[DEBUG] status={result.get('status')}, path={result.get('path')}")
    print(f"[DEBUG] message={result.get('message')}")
    print(f"[DEBUG] refinement_options={result.get('refinement_options')}")
    print(f"[DEBUG] search_request={result.get('state', {}).get('search_request')}")

    assert result["status"] == "complete"
    assert result["path"] == "no_match"

    # Verify specific, actionable response (not generic "no results" message)
    assert "message" in result
    assert result["message"] is not None
    assert len(result["message"]) > 0
    assert "exact matches" in result["message"].lower()

    # Verify refinement options are provided
    assert "refinement_options" in result
    refinement_options = result["refinement_options"]
    assert isinstance(refinement_options, list)
    assert len(refinement_options) > 0

    # Should suggest specific actions (budget, size, or style terms)
    options_text = " ".join(refinement_options).lower()
    assert any(keyword in options_text for keyword in ["budget", "size", "style"])

    # Verify search request was properly parsed
    search_req = result["state"]["search_request"]
    assert "designer ballgown" in search_req["description"].lower()
    assert search_req["size"] == "XXS"
    assert search_req["max_price"] == 5.0
