"""State-driven planning loop for FitFindr."""

from __future__ import annotations

import re
from typing import Any

from tools.create_fit_card import create_fit_card
from tools.search_listings import search_listings
from tools.suggest_outfit import suggest_outfit
from utils.data_loader import get_empty_wardrobe

REQUIRED_FIELDS = ("description", "size", "max_price")


def _default_state() -> dict[str, Any]:
    return {
        "original_query": "",
        "search_request": {"description": None, "size": None, "max_price": None},
        "search_results": None,
        "listing": None,
        "alternatives": [],
        "outfit": None,
        "fit_card": None,
        "wardrobe": get_empty_wardrobe(),
        "status": "initialized",
        "error_log": [],
    }


def initialize_state(
    original_query: str,
    wardrobe: dict[str, Any] | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or merge a session state object for one interaction."""
    state = _default_state()
    if isinstance(session_state, dict):
        state.update(session_state)

    state["original_query"] = original_query or state.get("original_query", "")

    if isinstance(wardrobe, dict):
        state["wardrobe"] = wardrobe
    elif not isinstance(state.get("wardrobe"), dict):
        state["wardrobe"] = get_empty_wardrobe()

    if not isinstance(state.get("error_log"), list):
        state["error_log"] = []

    if not isinstance(state.get("search_request"), dict):
        state["search_request"] = {"description": None, "size": None, "max_price": None}

    for field in REQUIRED_FIELDS:
        state["search_request"].setdefault(field, None)

    return state


def _extract_budget(query: str) -> float | None:
    if not query:
        return None
    dollar_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", query)
    if dollar_match:
        return float(dollar_match.group(1))

    under_match = re.search(r"\b(?:under|below|max)\s*(\d+(?:\.\d+)?)\b", query.lower())
    if under_match:
        return float(under_match.group(1))

    return None


def _extract_size(query: str) -> str | None:
    if not query:
        return None

    size_match = re.search(r"\b(?:xxs|xs|s|m|l|xl|xxl|xxxl|s/m|m/l|l/xl|w\d{2}(?:\s*l\d{2})?)\b", query.lower())
    if size_match:
        return size_match.group(0).upper()

    explicit_match = re.search(r"\bsize\s*(xxs|xs|s|m|l|xl|xxl|xxxl|\d{1,2})\b", query.lower())
    if explicit_match:
        return explicit_match.group(1).upper()

    return None


def _extract_description(query: str) -> str | None:
    if not query:
        return None

    text = query.strip()
    text = re.sub(r"\$\s*\d+(?:\.\d+)?", "", text)
    text = re.sub(r"\b(?:under|below|max)\s*\d+(?:\.\d+)?\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsize\s*(?:xxs|xs|s|m|l|xl|xxl|xxxl|\d{1,2})\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ,.-")
    return text or None


def _set_search_request(
    state: dict[str, Any],
    description: str | None,
    size: str | None,
    max_price: float | int | None,
) -> None:
    if description and not state["search_request"].get("description"):
        state["search_request"]["description"] = description
    if size and not state["search_request"].get("size"):
        state["search_request"]["size"] = size
    if max_price is not None and state["search_request"].get("max_price") is None:
        state["search_request"]["max_price"] = float(max_price)


def _missing_fields(search_request: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        value = search_request.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


def _record_error(state: dict[str, Any], stage: str, error: Exception) -> None:
    state["error_log"].append({"stage": stage, "message": str(error)})


def _plain_text_fallback(state: dict[str, Any]) -> dict[str, Any]:
    styling_notes: list[str] = []
    if isinstance(state.get("outfit"), dict):
        raw_notes = state["outfit"].get("styling_notes", [])
        if isinstance(raw_notes, list):
            styling_notes = [str(note) for note in raw_notes if str(note).strip()][:3]

    return {
        "status": "complete",
        "path": "plain_text_fallback",
        "listing": state.get("listing"),
        "alternatives": state.get("alternatives", []),
        "styling_notes": styling_notes,
        "state": state,
    }


def run_planning_loop(
    *,
    original_query: str,
    wardrobe: dict[str, Any] | None = None,
    description: str | None = None,
    size: str | None = None,
    max_price: float | int | None = None,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute the planning loop with conditional branching based on session state.

    Required persisted fields in state:
    - original_query
    - listing (selected result from search_listings)
    - outfit (outfit payload from suggest_outfit)
    - fit_card (final result from create_fit_card)
    """
    state = initialize_state(
        original_query=original_query,
        wardrobe=wardrobe,
        session_state=session_state,
    )

    inferred_description = description if description is not None else _extract_description(original_query)
    inferred_size = size if size is not None else _extract_size(original_query)
    inferred_budget = max_price if max_price is not None else _extract_budget(original_query)

    _set_search_request(
        state=state,
        description=inferred_description,
        size=inferred_size,
        max_price=inferred_budget,
    )

    while True:
        missing = _missing_fields(state["search_request"])
        if missing:
            state["status"] = "needs_clarification"
            question_by_field = {
                "description": "What item description should I search for?",
                "size": "What size should I use?",
                "max_price": "What is your max budget in USD?",
            }
            return {
                "status": "needs_clarification",
                "missing_fields": missing,
                "question": question_by_field[missing[0]],
                "state": state,
            }

        if state.get("search_results") is None:
            req = state["search_request"]
            try:
                state["search_results"] = search_listings(
                    description=str(req["description"]),
                    size=str(req["size"]),
                    max_price=float(req["max_price"]),
                )
            except Exception as exc:
                state["status"] = "search_error"
                _record_error(state, "search_listings", exc)
                return {
                    "status": "error",
                    "path": "search_error",
                    "message": "Search failed. Please retry with adjusted criteria.",
                    "state": state,
                }
            state["status"] = "searched"
            continue

        search_results = state["search_results"]
        matches = search_results.get("matches", []) if isinstance(search_results, dict) else []
        if not matches:
            state["status"] = "no_match"
            return {
                "status": "complete",
                "path": "no_match",
                "message": "No exact matches found. Which should we relax: budget, size, or style terms?",
                "refinement_options": ["raise budget", "broaden size", "adjust style terms"],
                "state": state,
            }

        if state.get("listing") is None:
            state["listing"] = matches[0]
            state["alternatives"] = matches[1:3]
            state["status"] = "listing_selected"
            continue

        if state.get("outfit") is None:
            try:
                outfit_result = suggest_outfit(new_item=state["listing"], wardrobe=state["wardrobe"])
            except Exception as exc:
                state["status"] = "outfit_error"
                _record_error(state, "suggest_outfit", exc)
                return {
                    "status": "complete",
                    "path": "listing_only_fallback",
                    "message": "I found a listing, but outfit generation was unavailable.",
                    "listing": state.get("listing"),
                    "alternatives": state.get("alternatives", []),
                    "state": state,
                }

            state["outfit"] = outfit_result.get("outfit") if isinstance(outfit_result, dict) else None
            state["status"] = "outfit_ready"
            continue

        if state.get("fit_card") is None:
            try:
                state["fit_card"] = create_fit_card(state["outfit"])
            except Exception as exc:
                state["status"] = "fit_card_error"
                _record_error(state, "create_fit_card", exc)
                return {
                    "status": "complete",
                    "path": "listing_only_fallback",
                    "message": "I found a listing, but card creation failed.",
                    "listing": state.get("listing"),
                    "alternatives": state.get("alternatives", []),
                    "state": state,
                }
            state["status"] = "fit_card_created"
            continue

        is_ready = bool(state["fit_card"].get("ready")) if isinstance(state.get("fit_card"), dict) else False
        state["status"] = "complete"

        if is_ready:
            return {
                "status": "complete",
                "path": "fit_card",
                "fit_card": state["fit_card"],
                "listing": state.get("listing"),
                "alternatives": state.get("alternatives", []),
                "state": state,
            }

        return _plain_text_fallback(state)
