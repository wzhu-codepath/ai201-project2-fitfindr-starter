"""
suggest_outfit tool: Builds an outfit around one selected listing using
wardrobe items with category, color, and style compatibility.
"""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from groq import Groq


NEUTRAL_COLORS = {
    "black",
    "white",
    "gray",
    "grey",
    "beige",
    "tan",
    "cream",
    "brown",
    "navy",
    "denim",
    "olive",
}


def _normalize_tokens(values: list[str] | None) -> set[str]:
    if not values:
        return set()
    return {str(v).strip().lower() for v in values if str(v).strip()}


def _required_categories(core_category: str) -> list[str]:
    category = (core_category or "").strip().lower()
    mapping = {
        "tops": ["bottoms", "shoes", "outerwear", "accessories"],
        "bottoms": ["tops", "shoes", "outerwear", "accessories"],
        "outerwear": ["tops", "bottoms", "shoes", "accessories"],
        "shoes": ["tops", "bottoms", "outerwear", "accessories"],
        "accessories": ["tops", "bottoms", "shoes", "outerwear"],
    }
    return mapping.get(category, ["tops", "bottoms", "shoes", "outerwear", "accessories"])


def _color_harmony_score(new_colors: set[str], wardrobe_colors: set[str]) -> float:
    if not new_colors or not wardrobe_colors:
        return 0.25

    if new_colors & wardrobe_colors:
        return 1.0

    if (new_colors & NEUTRAL_COLORS) or (wardrobe_colors & NEUTRAL_COLORS):
        return 0.6

    return 0.0


def _style_overlap_score(new_styles: set[str], wardrobe_styles: set[str]) -> float:
    if not new_styles or not wardrobe_styles:
        return 0.2

    overlap = new_styles & wardrobe_styles
    union = new_styles | wardrobe_styles
    if not union:
        return 0.0
    return len(overlap) / len(union)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return None


def _select_diverse_candidates(candidates: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_categories: set[str] = set()

    for candidate in candidates:
        category = str(candidate.get("category", "")).strip().lower()
        if category and category in used_categories:
            continue
        selected.append(candidate)
        if category:
            used_categories.add(category)
        if len(selected) >= limit:
            return selected

    if len(selected) < limit:
        for candidate in candidates:
            if candidate in selected:
                continue
            selected.append(candidate)
            if len(selected) >= limit:
                break

    return selected


def _build_compatibility_pool(new_item: dict[str, Any], wardrobe_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required = _required_categories(str(new_item.get("category", "")))
    new_styles = _normalize_tokens(new_item.get("style_tags"))
    new_colors = _normalize_tokens(new_item.get("colors"))

    scored: list[dict[str, Any]] = []
    for item in wardrobe_items:
        item_category = str(item.get("category", "")).strip().lower()
        if item_category not in required:
            continue

        style_score = _style_overlap_score(new_styles, _normalize_tokens(item.get("style_tags")))
        color_score = _color_harmony_score(new_colors, _normalize_tokens(item.get("colors")))

        # Category gets a baseline weight because all candidates must fill a needed slot.
        score = (0.45 * 1.0) + (0.35 * style_score) + (0.20 * color_score)
        if score >= 0.52:
            enriched = dict(item)
            enriched["_compatibility_score"] = round(score, 3)
            scored.append(enriched)

    scored.sort(key=lambda x: x.get("_compatibility_score", 0.0), reverse=True)
    return scored


def _missing_categories(new_item: dict[str, Any], wardrobe_items: list[dict[str, Any]]) -> list[str]:
    required = _required_categories(str(new_item.get("category", "")))
    existing = {str(item.get("category", "")).strip().lower() for item in wardrobe_items}
    return [cat for cat in required if cat not in existing]


def _fallback_styling_notes(new_item: dict[str, Any], missing_categories: list[str], has_wardrobe_items: bool) -> list[str]:
    title = str(new_item.get("title", "This item")).strip() or "This item"
    if not has_wardrobe_items:
        return [
            f"Start with {title} as the focal piece and keep the rest of the fit simple.",
            "Anchor the outfit with neutral bottoms and comfortable shoes for easy repeat wear.",
            "Add one texture layer (denim, knit, or leather) to create depth without clashing.",
        ]

    notes = [
        f"Use {title} as the visual anchor and keep supporting pieces clean and minimal.",
        "Balance silhouette by pairing one relaxed piece with one more structured piece.",
    ]
    if missing_categories:
        notes.append(
            "To improve personalization, add staples in these categories: "
            + ", ".join(missing_categories)
            + "."
        )
    return notes


def _deterministic_notes(new_item: dict[str, Any], paired_items: list[dict[str, Any]]) -> list[str]:
    title = str(new_item.get("title", "this piece")).strip() or "this piece"
    notes = [f"Center the look around {title} and keep the remaining pieces cohesive."]

    for item in paired_items[:2]:
        item_name = str(item.get("name", "wardrobe piece")).strip() or "wardrobe piece"
        category = str(item.get("category", "item")).strip().lower() or "item"
        notes.append(f"Use {item_name} as your {category} layer to support the same style direction.")

    if not paired_items:
        notes.append("Build from neutral staples first, then add one accent accessory.")

    return notes[:4]


def _llm_pairing_plan(new_item: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[suggest_outfit] ❌ No GROQ_API_KEY found - skipping LLM")
        return None

    model = "llama-3.3-70b-versatile"

    compact_candidates = []
    for candidate in candidates[:12]:
        compact_candidates.append(
            {
                "id": candidate.get("id"),
                "name": candidate.get("name"),
                "category": candidate.get("category"),
                "colors": candidate.get("colors", []),
                "style_tags": candidate.get("style_tags", []),
                "notes": candidate.get("notes", ""),
                "compatibility_score": candidate.get("_compatibility_score", 0.0),
            }
        )

    system_prompt = (
        "You are a precise fashion stylist assistant. Choose wardrobe items that best complement "
        "the new listing by style overlap, color harmony, and category balance. "
        "Return strict JSON only with keys: paired_item_ids (list of item ids), "
        "styling_notes (3-4 short concrete bullets), confidence (float 0.0-1.0)."
    )
    user_prompt = json.dumps(
        {
            "new_item": {
                "id": new_item.get("id"),
                "title": new_item.get("title"),
                "category": new_item.get("category"),
                "style_tags": new_item.get("style_tags", []),
                "colors": new_item.get("colors", []),
            },
            "candidate_wardrobe_items": compact_candidates,
            "constraints": {
                "max_items": 4,
                "prefer_distinct_categories": True,
                "no_explanatory_text_outside_json": True,
            },
        }
    )

    try:
        print("[suggest_outfit] 🤖 Calling LLM to pair outfit...")
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        content = response.choices[0].message.content if response.choices else ""
        print(f"[suggest_outfit] 📝 LLM raw response: {content[:150]}...")
        parsed = _extract_json_object(content)
        if not isinstance(parsed, dict):
            print("[suggest_outfit] ❌ LLM response was not valid JSON - falling back to deterministic")
            return None
        print("[suggest_outfit] ✅ LLM response parsed successfully")
        print(f"[suggest_outfit] 📋 LLM picked item IDs: {parsed.get('paired_item_ids')}")
        return parsed
    except Exception as e:
        print(f"[suggest_outfit] ❌ LLM request failed: {str(e)}")
        return None


def suggest_outfit(new_item: dict, wardrobe: dict) -> dict:
    """
    Build an outfit around one selected listing using compatible wardrobe items.

    Args:
        new_item: Single listing dictionary from search_listings output.
        wardrobe: Wardrobe dictionary with an "items" list.

    Returns:
        Dictionary with selected_new_item, outfit, and confidence.
    """
    if not isinstance(new_item, dict):
        raise ValueError("new_item must be a dictionary")
    if not isinstance(wardrobe, dict):
        raise ValueError("wardrobe must be a dictionary")

    wardrobe_items = wardrobe.get("items", [])
    if not isinstance(wardrobe_items, list):
        wardrobe_items = []

    missing_categories = _missing_categories(new_item, wardrobe_items)

    if not wardrobe_items:
        return {
            "selected_new_item": new_item,
            "outfit": {
                "core_item": new_item,
                "paired_items": [],
                "missing_categories": missing_categories,
                "styling_notes": _fallback_styling_notes(new_item, missing_categories, has_wardrobe_items=False),
            },
            "confidence": 0.28,
        }

    compatibility_pool = _build_compatibility_pool(new_item, wardrobe_items)
    if not compatibility_pool:
        return {
            "selected_new_item": new_item,
            "outfit": {
                "core_item": new_item,
                "paired_items": [],
                "missing_categories": missing_categories,
                "styling_notes": _fallback_styling_notes(new_item, missing_categories, has_wardrobe_items=True),
            },
            "confidence": 0.35,
        }

    id_to_item = {str(item.get("id")): item for item in compatibility_pool if item.get("id") is not None}

    llm_output = _llm_pairing_plan(new_item, compatibility_pool)
    paired_items: list[dict[str, Any]] = []
    styling_notes: list[str] = []
    confidence: float | None = None
    used_llm = False

    if isinstance(llm_output, dict):
        print("[suggest_outfit] 🎨 Using LLM-selected items")
        used_llm = True
        raw_ids = llm_output.get("paired_item_ids", [])
        if isinstance(raw_ids, list):
            for item_id in raw_ids:
                item = id_to_item.get(str(item_id))
                if item and item not in paired_items:
                    paired_items.append(item)
                if len(paired_items) >= 4:
                    break

        raw_notes = llm_output.get("styling_notes", [])
        if isinstance(raw_notes, list):
            styling_notes = [str(note).strip() for note in raw_notes if str(note).strip()][:4]

        raw_confidence = llm_output.get("confidence")
        if isinstance(raw_confidence, (int, float)):
            confidence = float(raw_confidence)

    if not paired_items:
        print("[suggest_outfit] 🔄 No valid LLM items - using deterministic algorithm")
        used_llm = False
        paired_items = _select_diverse_candidates(compatibility_pool, limit=4)

    if not styling_notes:
        if not used_llm:
            print("[suggest_outfit] 📝 Using deterministic styling notes")
        styling_notes = _deterministic_notes(new_item, paired_items)

    if confidence is None:
        avg_score = sum(item.get("_compatibility_score", 0.0) for item in paired_items) / max(len(paired_items), 1)
        coverage_boost = min(len({str(i.get("category", "")).lower() for i in paired_items}) * 0.05, 0.15)
        confidence = min(0.55 + (avg_score * 0.35) + coverage_boost, 0.95)

    print(f"[suggest_outfit] ✅ Final outfit confidence: {confidence:.2f} ({'LLM' if used_llm else 'deterministic'})")

    clean_paired_items = []
    for item in paired_items:
        clean_item = dict(item)
        clean_item.pop("_compatibility_score", None)
        clean_paired_items.append(clean_item)

    return {
        "selected_new_item": new_item,
        "outfit": {
            "core_item": new_item,
            "paired_items": clean_paired_items,
            "missing_categories": missing_categories,
            "styling_notes": styling_notes,
        },
        "confidence": round(max(0.0, min(float(confidence), 1.0)), 3),
    }
