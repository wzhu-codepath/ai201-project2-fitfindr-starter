import gradio as gr
from planning_loop import run_planning_loop
from utils.data_loader import get_example_wardrobe


class SessionState:
    """Manages multi-turn conversation state."""
    def __init__(self):
        self.wardrobe = get_example_wardrobe()
        self.session_state = None
        self.last_result = None

    def reset(self):
        self.session_state = None
        self.last_result = None


session = SessionState()


def format_hero_item(hero_item: dict) -> str:
    """Format hero item details for display."""
    if not hero_item:
        return ""
    lines = []
    if hero_item.get("title"):
        lines.append(f"**{hero_item['title']}**")
    if hero_item.get("price") is not None:
        lines.append(f"Price: ${hero_item['price']:.2f}")
    if hero_item.get("platform"):
        lines.append(f"Platform: {hero_item['platform']}")
    if hero_item.get("size"):
        lines.append(f"Size: {hero_item['size']}")
    if hero_item.get("condition"):
        lines.append(f"Condition: {hero_item['condition']}")
    return "\n".join(lines)


def format_alternatives(alternatives: list) -> str:
    """Format alternative listings for display."""
    if not alternatives:
        return ""

    lines = ["**Alternative options:**"]
    for i, item in enumerate(alternatives[:2], 1):
        lines.append(f"\n{i}. {item.get('title', 'Unnamed')} - ${item.get('price', 'N/A')}")
    return "\n".join(lines)


def format_warnings(warnings: list) -> str:
    """Format warnings from fit card."""
    if not warnings:
        return ""
    return "⚠️ " + " | ".join(warnings)


def handle_query(question: str) -> tuple[str, str, str, str]:
    """
    Process user query through the planning loop.

    Returns:
        (main_message, hero_item_display, style_recipe, refinement_options)
    """
    if not question.strip():
        return "Please enter a search query.", "", "", ""

    # Run planning loop with current session state
    result = run_planning_loop(
        original_query=question,
        wardrobe=session.wardrobe,
        session_state=session.session_state,
    )

    session.last_result = result
    status = result.get("status", "")
    path = result.get("path", "")

    # ============ NEEDS CLARIFICATION ============
    if status == "needs_clarification":
        missing_fields = result.get("missing_fields", [])
        question_text = result.get("question", "Could you provide more details?")

        session.session_state = result.get("state", {})

        return (
            f"**Need more info:** {question_text}\n\nMissing: {', '.join(missing_fields)}",
            "",
            "",
            ""
        )

    # ============ ERROR ============
    if status == "error":
        message = result.get("message", "An error occurred")
        return message, "", "", ""

    # ============ NO MATCH ============
    if path == "no_match":
        message = result.get("message", "No exact matches found.")
        refinement_options = result.get("refinement_options", [])

        session.session_state = result.get("state", {})

        refine_text = "\n".join([f"• {opt}" for opt in refinement_options])
        return (
            f"{message}\n\n**Try adjusting:**\n{refine_text}",
            "",
            "",
            ""
        )

    # ============ LISTING ONLY FALLBACK ============
    if path == "listing_only_fallback":
        listing = result.get("listing", {})
        message = result.get("message", "I found a listing, but couldn't build a full outfit.")

        state = result.get("state", {})
        session.session_state = state

        hero_display = format_hero_item(listing)
        alternatives = format_alternatives(result.get("alternatives", []))

        return (
            f"{message}\n\n{hero_display}\n\n{alternatives}",
            hero_display,
            "",
            ""
        )

    # ============ PLAIN TEXT FALLBACK ============
    if path == "plain_text_fallback":
        listing = result.get("listing", {})
        styling_notes = result.get("styling_notes", [])

        state = result.get("state", {})
        session.session_state = state

        hero_display = format_hero_item(listing)

        styling_text = "\n".join([f"• {note}" for note in styling_notes])
        style_recipe = f"**Styling ideas:**\n{styling_text}" if styling_text else ""

        alternatives = format_alternatives(result.get("alternatives", []))

        full_message = f"{hero_display}\n\n{style_recipe}\n\n{alternatives}"

        return (
            full_message,
            hero_display,
            style_recipe,
            ""
        )

    # ============ FIT CARD (SUCCESS PATH) ============
    if path == "fit_card":
        listing = result.get("listing", {})
        fit_card_data = result.get("fit_card", {})

        state = result.get("state", {})
        session.session_state = state

        hero_display = format_hero_item(fit_card_data.get("hero_item", {}))

        # Format style recipe
        style_recipe_lines = fit_card_data.get("style_recipe", [])
        style_recipe = "\n".join(style_recipe_lines) if style_recipe_lines else ""

        # Format wardrobe pairings
        pairings = fit_card_data.get("wardrobe_pairings", [])
        pairings_text = "\n".join([f"• {p}" for p in pairings]) if pairings else ""

        # Format warnings
        warnings = format_warnings(fit_card_data.get("warnings", []))

        # Assemble full fit card
        fit_title = fit_card_data.get("fit_title", "Fit Card")

        full_card = f"## {fit_title}\n\n{hero_display}"
        if style_recipe:
            full_card += f"\n\n**Style Recipe:**\n{style_recipe}"
        if pairings_text:
            full_card += f"\n\n**Wardrobe Pairings:**\n{pairings_text}"
        if warnings:
            full_card += f"\n\n{warnings}"

        alternatives = format_alternatives(result.get("alternatives", []))
        full_card += f"\n\n{alternatives}"

        return (
            full_card,
            hero_display,
            style_recipe,
            ""
        )

    # ============ UNKNOWN STATE ============
    return "Unexpected response format. Please try again.", "", "", ""


def reset_session():
    """Reset the conversation session."""
    session.reset()
    return "Session reset. Start a new search!", "", "", ""


# ============ GRADIO INTERFACE ============
with gr.Blocks(title="FitFindr Agent") as demo:
    gr.Markdown("""
    # FitFindr — AI Fashion Agent

    Find vintage listings that match your style, and get personalized outfit recommendations from your wardrobe.
    """)

    with gr.Row():
        with gr.Column(scale=3):
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g., 'vintage graphic tee under $30'",
                lines=2
            )
        with gr.Column(scale=1):
            search_btn = gr.Button("Search", variant="primary")
            reset_btn = gr.Button("Reset", variant="secondary")

    # Main output area
    main_output = gr.Markdown(label="Response")

    with gr.Row():
        hero_display = gr.Textbox(label="Item Details", lines=5, interactive=False)
        style_recipe = gr.Textbox(label="Styling Guide", lines=5, interactive=False)

    # Setup event handlers
    search_btn.click(
        handle_query,
        inputs=query_input,
        outputs=[main_output, hero_display, style_recipe, gr.State()]
    )

    query_input.submit(
        handle_query,
        inputs=query_input,
        outputs=[main_output, hero_display, style_recipe, gr.State()]
    )

    reset_btn.click(
        reset_session,
        outputs=[main_output, hero_display, style_recipe, gr.State()]
    )

    gr.Markdown("""
    ---
    **How it works:**
    1. Enter what you're looking for (description, budget, size)
    2. The agent searches through vintage listings
    3. If it needs clarification, it will ask
    4. Once it finds matches, it builds an outfit from your wardrobe
    5. You get a styled recommendation with alternatives
    """)


if __name__ == "__main__":
    demo.launch()
