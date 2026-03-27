"""
create_fit_card tool: Formats outfit output into a user-facing fit card payload.
"""

from __future__ import annotations

import json
import os
import random
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv() -> None:
        return None


try:
    from groq import Groq
except Exception:  # pragma: no cover
    Groq = None


REQUIRED_OUTFIT_KEYS = {"core_item", "paired_items", "missing_categories", "styling_notes"}
HERO_ITEM_KEYS = ("id", "title", "price", "platform", "size", "condition")
CREATIVE_DIRECTIONS = [
    "clean_street",
    "retro_energy",
    "soft_minimal",
    "edgy_layered",
    "weekend_confident",
]


def _safe_str(value: Any, fallback: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _build_fit_title(core_item: dict[str, Any]) -> str:
    title = _safe_str(core_item.get("title"), fallback="Styled Fit")
    return f"{title} Fit Card"


def _build_hero_item(core_item: dict[str, Any]) -> dict[str, Any]:
    hero_item: dict[str, Any] = {}
    for key in HERO_ITEM_KEYS:
        if key == "price":
            hero_item[key] = core_item.get(key)
        else:
            hero_item[key] = core_item.get(key)
    return hero_item


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


def _build_style_recipe(core_item: dict[str, Any], paired_items: list[dict[str, Any]], styling_notes: list[str]) -> list[str]:
    recipe: list[str] = []

    for note in styling_notes:
        clean_note = _safe_str(note)
        if clean_note:
            recipe.append(clean_note)

    if not recipe:
        core_title = _safe_str(core_item.get("title"), fallback="this item")
        recipe.append(f"Start with {core_title} as the focal piece.")

        if paired_items:
            first_pair = _safe_str(paired_items[0].get("name"), fallback="a wardrobe staple")
            recipe.append(f"Add {first_pair} to anchor the silhouette.")

        recipe.append("Finish with one simple accessory to keep the look cohesive.")

    # Convert to explicit step-by-step lines.
    return [f"Step {idx}: {line}" for idx, line in enumerate(recipe, start=1)]


def _build_wardrobe_pairings(paired_items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in paired_items:
        name = _safe_str(item.get("name"), fallback="Unnamed item")
        category = _safe_str(item.get("category"), fallback="item")
        colors = item.get("colors", [])
        color_text = ", ".join(_safe_str(c) for c in colors if _safe_str(c)) if isinstance(colors, list) else ""

        if color_text:
            lines.append(f"{name} ({category}) - colors: {color_text}")
        else:
            lines.append(f"{name} ({category})")

    return lines


def _normalize_style_recipe(recipe: list[str]) -> list[str]:
    clean_lines = [_safe_str(line) for line in recipe if _safe_str(line)]
    return [f"Step {idx}: {line}" for idx, line in enumerate(clean_lines, start=1)]


def _llm_fit_copy(
    core_item: dict[str, Any],
    paired_items: list[dict[str, Any]],
    styling_notes: list[str],
    missing_categories: list[str],
) -> tuple[dict[str, Any] | None, str | None]:
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None, "LLM styling unavailable: GROQ_API_KEY is not set. Using deterministic fit-card copy."

    if Groq is None:
        return None, "LLM styling unavailable: Groq client is not installed. Using deterministic fit-card copy."

    creative_direction = random.choice(CREATIVE_DIRECTIONS)
    variation_seed = random.randint(1000, 999999)
    compact_pairs = [
        {
            "name": item.get("name"),
            "category": item.get("category"),
            "colors": item.get("colors", []),
            "style_tags": item.get("style_tags", []),
        }
        for item in paired_items[:4]
    ]

    system_prompt = (
        "You are FitFindr's stylist copywriter. Write fit-card copy that sounds shareable and personal, "
        "not like a product listing. Return JSON only with key 'cards', where cards is a list of exactly 3 objects. "
        "Each object must contain fit_title, style_recipe, wardrobe_pairings. "
        "Each card must have a clearly different voice and wording from the others (not minor rephrases). "
        "fit_title: catchy and under 8 words. style_recipe: 3-5 actionable lines. "
        "wardrobe_pairings: 1-4 short readable pairing lines."
    )

    user_prompt = json.dumps(
        {
            "creative_direction": creative_direction,
            "variation_seed": variation_seed,
            "core_item": {
                "title": core_item.get("title"),
                "category": core_item.get("category"),
                "colors": core_item.get("colors", []),
                "style_tags": core_item.get("style_tags", []),
            },
            "paired_items": compact_pairs,
            "styling_notes": styling_notes[:4],
            "missing_categories": missing_categories,
            "voice_constraints": {
                "avoid": [
                    "SKU language",
                    "generic e-commerce phrasing",
                    "overly technical fashion jargon",
                ],
                "prefer": [
                    "vivid but concise language",
                    "confidence-forward tone",
                    "concrete wear instructions",
                ],
            },
            "diversity_constraints": {
                "cards_must_feel_distinct": True,
                "vary_sentence_rhythm": True,
                "vary_word_choice": True,
                "avoid_repeating_opening_phrases": True,
            },
        }
    )

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=1.15,
            top_p=0.95,
            max_tokens=500,
        )
        content = response.choices[0].message.content if response.choices else ""
        parsed = _extract_json_object(content)
        if not isinstance(parsed, dict):
            return None, "LLM response could not be parsed. Using deterministic fit-card copy."

        cards = parsed.get("cards", [])
        if not isinstance(cards, list):
            return None, "LLM response format was incomplete. Using deterministic fit-card copy."

        normalized_cards = [card for card in cards if isinstance(card, dict)]
        if not normalized_cards:
            return None, "LLM response had no valid card options. Using deterministic fit-card copy."

        return random.choice(normalized_cards), None
    except Exception:
        return None, "LLM request failed. Using deterministic fit-card copy."


def _collect_warnings(
    missing_outfit_keys: list[str],
    missing_hero_fields: list[str],
    missing_categories: list[str],
) -> list[str]:
    warnings: list[str] = []

    if missing_outfit_keys:
        warnings.append("Missing required outfit keys: " + ", ".join(missing_outfit_keys))

    if missing_hero_fields:
        warnings.append("Hero item is missing fields: " + ", ".join(missing_hero_fields))

    if missing_categories:
        warnings.append("Missing wardrobe categories: " + ", ".join(missing_categories))

    return warnings


def create_fit_card(outfit: dict) -> dict:
    """
    Transform an outfit dictionary into a structured fit card payload.

    Args:
        outfit: Dictionary from suggest_outfit containing core_item, paired_items,
            missing_categories, and styling_notes.

    Returns:
        Dictionary with:
        - fit_title (str)
        - hero_item (dict): id/title/price/platform/size/condition
        - style_recipe (list[str])
        - wardrobe_pairings (list[str])
        - warnings (list[str])
        - ready (bool)
    """
    try:
        if not isinstance(outfit, dict):
            return {
                "fit_title": "Fit Recommendation",
                "hero_item": {},
                "style_recipe": [],
                "wardrobe_pairings": [],
                "warnings": ["Invalid outfit payload: expected a dictionary."],
                "ready": False,
            }

        missing_outfit_keys = sorted(REQUIRED_OUTFIT_KEYS - set(outfit.keys()))
        core_item = outfit.get("core_item", {})
        paired_items = outfit.get("paired_items", [])
        missing_categories = outfit.get("missing_categories", [])
        styling_notes = outfit.get("styling_notes", [])

        if not isinstance(core_item, dict):
            core_item = {}
        if not isinstance(paired_items, list):
            paired_items = []
        if not isinstance(missing_categories, list):
            missing_categories = []
        if not isinstance(styling_notes, list):
            styling_notes = []

        hero_item = _build_hero_item(core_item)
        missing_hero_fields = [
            key
            for key in HERO_ITEM_KEYS
            if hero_item.get(key) in (None, "", [])
        ]

        warnings = _collect_warnings(
            missing_outfit_keys=missing_outfit_keys,
            missing_hero_fields=missing_hero_fields,
            missing_categories=[_safe_str(c) for c in missing_categories if _safe_str(c)],
        )

        ready = len(missing_outfit_keys) == 0

        default_title = _build_fit_title(core_item)
        default_recipe = _build_style_recipe(core_item, paired_items, styling_notes)
        default_pairings = _build_wardrobe_pairings(paired_items)

        llm_payload, llm_warning = _llm_fit_copy(
            core_item=core_item,
            paired_items=paired_items,
            styling_notes=styling_notes,
            missing_categories=[_safe_str(c) for c in missing_categories if _safe_str(c)],
        )

        if llm_warning and llm_warning not in warnings:
            warnings.append(llm_warning)

        fit_title = default_title
        style_recipe = default_recipe
        wardrobe_pairings = default_pairings

        if isinstance(llm_payload, dict):
            raw_title = _safe_str(llm_payload.get("fit_title"))
            raw_recipe = llm_payload.get("style_recipe", [])
            raw_pairings = llm_payload.get("wardrobe_pairings", [])

            if raw_title:
                fit_title = raw_title

            if isinstance(raw_recipe, list):
                normalized_recipe = _normalize_style_recipe([_safe_str(line) for line in raw_recipe if _safe_str(line)])
                if normalized_recipe:
                    style_recipe = normalized_recipe

            if isinstance(raw_pairings, list):
                normalized_pairings = [_safe_str(line) for line in raw_pairings if _safe_str(line)]
                if normalized_pairings:
                    wardrobe_pairings = normalized_pairings

        return {
            "fit_title": fit_title,
            "hero_item": hero_item,
            "style_recipe": style_recipe,
            "wardrobe_pairings": wardrobe_pairings,
            "warnings": warnings,
            "ready": ready,
        }
    except Exception:
        # Keep output useful even if formatting fails.
        core_item = outfit.get("core_item", {}) if isinstance(outfit, dict) else {}
        fallback_title = _safe_str(core_item.get("title"), fallback="Fit Recommendation")
        fallback_notes: list[str] = []

        if isinstance(outfit, dict):
            raw_notes = outfit.get("styling_notes", [])
            if isinstance(raw_notes, list):
                fallback_notes = [
                    f"Step {idx}: {_safe_str(note)}"
                    for idx, note in enumerate(raw_notes, start=1)
                    if _safe_str(note)
                ][:3]

        return {
            "fit_title": f"{fallback_title} Fit Card",
            "hero_item": _build_hero_item(core_item if isinstance(core_item, dict) else {}),
            "style_recipe": fallback_notes,
            "wardrobe_pairings": [],
            "warnings": ["create_fit_card formatting fallback used due to an unexpected issue."],
            "ready": False,
        }