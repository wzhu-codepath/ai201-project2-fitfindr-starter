# FitFindr — Starter Kit

This starter kit contains everything you need to begin Project 2.

## What's Included

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # Helper functions for loading the data
├── planning.md                # Your planning template — fill this out first
└── requirements.txt           # Python dependencies
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops, bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore, streetwear, and more).

Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`.

Load it with:
```python
from utils.data_loader import load_listings
listings = load_listings()
```

## The Wardrobe Schema

`data/wardrobe_schema.json` defines the format your agent uses to represent a user's existing wardrobe. It includes:

- `schema`: field definitions for a wardrobe item
- `example_wardrobe`: a sample wardrobe with 10 items you can use for testing
- `empty_wardrobe`: a starting template for a new user

Load an example wardrobe with:
```python
from utils.data_loader import get_example_wardrobe
wardrobe = get_example_wardrobe()
```

## Where to Start

1. **Read `planning.md` and fill it out before writing any code.**
2. Verify the data loads correctly by running `python utils/data_loader.py`.
3. Build and test each tool individually before connecting them through your planning loop.

Your implementation files go in this same directory. There's no required file structure for your agent code — organize it however makes sense for your design.

---

## Tool Inventory

The FitFindr agent uses three core tools:

### 1. search_listings()
- **Purpose:** Find secondhand items matching user description from the listings dataset
- **Inputs:**
  - `description` (str): User's search query (e.g., "blue vintage jeans")
  - `category_filter` (str, optional): Limit to specific category (tops, bottoms, outerwear, shoes, accessories)
  - `style_filter` (str, optional): Match by style tags (vintage, y2k, grunge, etc.)
- **Outputs:**
  - `results` (list): Ranked listings scored by keyword overlap, sorted by relevance
  - `search_completed` (bool): Indicates whether search ran without error
- **Error Handling:** Returns empty results list if no matches; reports query parse errors in status

### 2. suggest_outfit()
- **Purpose:** Build a complementary outfit by pairing the found listing with wardrobe items
- **Inputs:**
  - `listing` (dict): The hero item (from search_listings)
  - `wardrobe` (dict): User's existing wardrobe items
- **Outputs:**
  - `outfit` (dict): Contains paired_item_ids, styling_notes, confidence score
  - Falls back to deterministic selection if LLM unavailable
- **Error Handling:** If LLM fails or returns invalid JSON, selects diverse candidates algorithmically (see "Error Handling" section); enforces category diversity override

### 3. create_fit_card()
- **Purpose:** Format the outfit into a shareable fit card with copy and styling instructions
- **Inputs:**
  - `listing` (dict): Hero item
  - `outfit` (dict): Paired items and styling notes from suggest_outfit
  - `user_preferences` (dict): Optional style guidance
- **Outputs:**
  - `fit_card` (dict): Contains fit_title, style_recipe, wardrobe_pairings, warnings
  - User-facing markdown-formatted text
- **Error Handling:** Validates all fields; falls back to deterministic defaults if LLM fails (see "Error Handling" section)

---

## Planning Loop Explanation

The agent implements a **state-driven conversation loop** with six possible response paths:

```
user_query → run_planning_loop() → six possible outcomes:

1. "clarification" — Missing required fields (description, size, or price range)
   └─> Ask user for missing info; preserve session state for next turn

2. "error" — Search failed (query parse error, API error)
   └─> Display error message; suggest rephrasing query

3. "no_match" — Zero listings found matching criteria
   └─> Show refinement options; suggest category or style adjustments

4. "listing_only_fallback" — Search succeeded, but outfit pairing failed
   └─> Show the found listing without outfit suggestions

5. "plain_text_fallback" — Outfit created but fit card generation failed
   └─> Show listing + outfit as plain text (no formatted copy)

6. "fit_card" (success) — All steps completed successfully
   └─> Display full formatted fit card with hero item + styled recipe
```

Each path is determined by `run_planning_loop()` in `planning_loop.py`, which checks return states from each tool and routes conditionally.

---

## State Management

The agent maintains **session state across multiple turns** using a `SessionState` class (in `app.py`):

```python
class SessionState:
    def __init__(self):
        self.session_state = {
            "history": [],           # Multi-turn conversation history
            "wardrobe": None,        # User's wardrobe (loaded once)
            "last_listing": None,    # Last found item (for context)
            "clarifications_pending": {}  # Partial queries awaiting user input
        }
```

**State Persistence Across Turns:**
- **History:** Each user message and agent response stored; preserved until reset
- **Wardrobe:** Loaded once at startup from `get_example_wardrobe()`; reused across all user queries
- **Pending Clarifications:** If a user provides description but omits price, the state remembers pending fields; next turn can fulfill them incrementally
- **Reset Button:** Clears all state; initializes fresh wardrobe

This allows users to have natural multi-turn conversations: *"Find me blue jeans" → "Oh, under $50"* without re-stating the color.

---

## Error Handling

### Tool-Level Error Handling

#### 1. search_listings() errors
**Issue:** User query may be too vague or contain unsupported filters

**Concrete Example:**
```python
# In search_listings(), if query is empty:
if not description or not description.strip():
    return {"results": [], "search_completed": False, status: "describe_what_you_want"}

# If no matches found after keyword scoring:
if not results:
    return {"results": [], "search_completed": True, status: "no_matches"}
```
**Behavior:** Empty results; system routes to "no_match" path and suggests refinements.

#### 2. suggest_outfit() errors
**Issue:** LLM may return malformed JSON, missing fields, or invalid item IDs

**Concrete Example:**
```python
# Lines 73-92: Robust JSON extraction
def _extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)  # Try full parse first
    except json.JSONDecodeError:
        # Search for {...} pattern within response
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)
        if match:
            return json.loads(match.group())
        return None  # Graceful failure

# If LLM returns no valid pairings:
if not paired_items:
    paired_items = _select_diverse_candidates(compatibility_pool, limit=4)  # Fallback
```
**Behavior:** If JSON is invalid, use deterministic algorithm instead; user sees outfit regardless.

#### 3. create_fit_card() errors
**Issue:** LLM may fail to return 3 cards or include incomplete fields

**Concrete Example:**
```python
# Lines 311-313: Fallback to deterministic defaults
if llm_payload is None:
    fit_title = f"{listing['title']} Fit Card"
    style_recipe = ["Layer with pieces from your wardrobe.", "Balance the look."]
    wardrobe_pairings = ["Pair with basic pieces."]

# Lines 315-331: Validate each field
if isinstance(llm_payload, dict):
    raw_title = _safe_str(llm_payload.get("fit_title"))
    if raw_title:
        fit_title = raw_title
    # ... similar validation for other fields
```
**Behavior:** LLM is optional; deterministic fallback ensures user always sees a formatted fit card.

### Planning Loop Error Routing

The `run_planning_loop()` function catches exceptions and routes them:

```python
try:
    result = search_listings(description, user_filters)
    if not result["search_completed"]:
        return {"status": "error", "message": result["status"]}
except Exception as e:
    return {"status": "error", "message": f"Search failed: {str(e)}"}

try:
    outfit = suggest_outfit(listing, wardrobe)
except Exception as e:
    return {"status": "listing_only_fallback", "listing": listing}  # Show item solo
```

---

## AI Tool Usage

1. I had directed the agent to help me write test cases, but some of the test cases were wrong and resulting in failed test cases, in which it was revised.
2. I had the AI tool help me create the 3 tools.

---

## Spec Reflection

**What was planned vs. what was built:**

The implementation successfully fulfills all planning.md requirements:

✅ **Tool Design:** All three core tools (search_listings, suggest_outfit, create_fit_card) implemented with clear inputs/outputs and error handling

✅ **Planning Loop:** Six-path conditional routing (clarification, error, no_match, listing_only_fallback, plain_text_fallback, fit_card) matches the designed flow

✅ **State Management:** Multi-turn SessionState preserves wardrobe and conversation history; supports incremental clarifications

✅ **LLM Integration:** Groq Llama 3.3 70B integrated for outfit pairing and fit card copywriting; all LLM outputs include fallbacks to deterministic generation

✅ **UI Integration:** Gradio interface displays all tool outputs with proper formatting (hero items, styling guides, alternatives, warnings)

**Key Deviations & Refinements:**

1. **Confidence Scoring:** Initially planned as simple boolean; refined to 0.0-1.0 scale with hybrid LLM + deterministic calculation for consistency

2. **Fallback Strategy:** Enhanced beyond simple error display—when LLM fails, system automatically falls back to deterministic generation (not just showing "error occurred")

3. **Category Diversity:** Added hard constraint on outfit suggestions to prevent all-same-category pairings, overriding LLM if needed

4. **Multi-turn Clarifications:** Extended initial design to support incremental field filling (e.g., provide description first, price on next turn)

---

## Running the App

```bash
python app.py
```

The Gradio interface provides multi-turn conversation support with display sections for item details, styling guides, and alternatives.
