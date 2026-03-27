# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Searches the listings dataset for items that match the user's natural-language description, target size, and max budget.
It scores and ranks matches so the planning loop can pick a best candidate and keep alternatives.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `description` (str): Free-text shopping intent (for example: "vintage graphic tee") used to match title, description, style_tags, and category hints.
- `size` (str): User's requested size string used for exact or partial comparison to listing size (for example: "L", "S/M", "W30").
- `max_price` (float): Upper budget cap in USD. Any listing with price greater than this value is excluded.

**What it returns:**
<!-- Describe the return value — what fields does a result contain? -->
Returns a dictionary with:
- `query_summary` (dict):
     - `description` (str)
     - `size` (str)
     - `max_price` (float)
     - `style_keywords` (list[str]) extracted from description
- `matches` (list[dict]) sorted by best match first; each match contains:
     - `id` (str)
     - `title` (str)
     - `description` (str)
     - `category` (str)
     - `style_tags` (list[str])
     - `size` (str)
     - `condition` (str)
     - `price` (float)
     - `colors` (list[str])
     - `brand` (str or null)
     - `platform` (str)
     - `match_score` (float)
- `match_count` (int)

**What happens if it fails or returns nothing:**
<!-- What should the agent do if no listings match? -->
If `match_count` is 0, the agent does not call downstream tools in the same turn. It responds with a no-match message and asks for one targeted adjustment (raise budget, broaden size, or relax style terms).
If the tool throws an error (data read issue, malformed input), the agent returns a short actionable error and ends the turn without calling other tools.

---

### Tool 2: suggest_outfit

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Builds an outfit around one selected listing (`new_item`) using wardrobe items that are compatible by category, color harmony, and style overlap.
It also explains why the pairing works so create_fit_card can present a clear recommendation.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `new_item` (dict): A single listing selected from `search_listings` output. Contains listing fields such as id/title/category/style_tags/price/colors/size.
- `wardrobe` (dict): User wardrobe object in schema format with `items` list. Each wardrobe item includes id/name/category/colors/style_tags/notes.

**What it returns:**
<!-- Describe the return value -->
Returns a dictionary with:
- `selected_new_item` (dict): Echo of the input listing.
- `outfit` (dict):
     - `core_item` (dict): the new item being styled.
     - `paired_items` (list[dict]): chosen wardrobe items to wear with it.
     - `missing_categories` (list[str]): required categories unavailable in wardrobe (for example: shoes).
     - `styling_notes` (list[str]): short, concrete styling reasons.
- `confidence` (float): 0.0 to 1.0.

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the wardrobe is empty or no outfit can be suggested? -->
If `wardrobe["items"]` is empty, return a fallback outfit object with no paired items and practical generic styling notes.
If no compatible items are found, return `paired_items = []` and populate `missing_categories`; the agent asks for a few closet staples to improve personalization.
If the tool errors, the agent continues with listing-only guidance and skips style-specific claims.

---

### Tool 3: create_fit_card

**What it does:**
<!-- Describe what this tool does in 1–2 sentences -->
Transforms the selected item plus outfit plan into a structured, user-facing fit card.
Formats key purchase details and styling steps into a final response payload for display.

**Input parameters:**
<!-- List each parameter, its type, and what it represents -->
- `outfit` (...): Outfit dictionary from `suggest_outfit` containing `core_item`, `paired_items`, `missing_categories`, and `styling_notes`.

**What it returns:**
<!-- Describe the return value -->
Returns a dictionary with:
- `fit_title` (str)
- `hero_item` (dict): id/title/price/platform/size/condition
- `style_recipe` (list[str]): step-by-step styling instructions
- `wardrobe_pairings` (list[str]): readable lines from paired_items
- `warnings` (list[str]): missing fields or missing categories
- `ready` (bool): whether card is valid for rendering

**What happens if it fails or returns nothing:**
<!-- What should the agent do if the outfit data is incomplete? -->
If required outfit keys are missing, return `ready = false` and warning messages. The planning loop falls back to plain text summary instead of a card.
If the tool raises an exception, agent still returns useful output: selected listing details + short styling bullets from current state.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
<!-- Describe the logic your planning loop uses. What does it look at? What conditions change its behavior? How does it know when it's done? -->
The loop uses a session state object with status markers and conditional branches.

1. Parse user query into required inputs: `description`, `size`, `max_price`.
2. If any required input is missing, ask one clarification question and pause.
3. Call `search_listings(description, size, max_price)`.
4. If search errors: return actionable error and end turn.
5. If search returns zero matches: return no-match guidance + ask which constraint to relax, then end turn.
6. If search returns matches: store full list, select top match as `new_item`, keep next 1-2 as alternatives.
7. Call `suggest_outfit(new_item, wardrobe)`.
8. If suggest_outfit fails: proceed with listing-only response path.
9. Otherwise call `create_fit_card(outfit)`.
10. If fit card is ready: return fit card + alternatives.
11. If fit card is not ready: return fallback plain-text recommendation.

Interaction is complete when the agent returns either a successful fit card, a fallback recommendation, or a blocking clarification question.

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->
State tracked per interaction/session:
- `original_query` (str)
- `search_request` (dict): description/size/max_price
- `search_results` (dict): full output of search_listings
- `selected_listing` (dict or null)
- `wardrobe` (dict)
- `outfit_result` (dict or null)
- `fit_card` (dict or null)
- `status` (str)
- `error_log` (list[dict])

Data handoff:
- `search_results["matches"][0]` becomes `new_item` for suggest_outfit.
- `outfit_result["outfit"]` becomes `outfit` input for create_fit_card.
- Any warning or missing categories are stored and included in the final user output.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Return "no exact matches" with up to 2 near-miss listings (closest style or price), then ask user to pick one refinement: raise budget, broaden size, or adjust style term. Stop downstream calls this turn. |
| suggest_outfit | Wardrobe is empty | Build a starter fallback outfit (generic bottoms/shoes/outerwear guidance), mark missing categories, and continue to create_fit_card so user still gets a complete recommendation response. |
| create_fit_card | Outfit input is missing or incomplete | Validate outfit fields before rendering. If invalid, skip card format and return a structured plain-text response with item details, 2-3 styling bullets, and explicit missing-field note. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

![alt text](<Architecture Diagram.png>)
---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

AI tool: GitHub Copilot.

Input I will provide:
- This `## Tools` section (exact parameter names/types/return structures).
- `## Error Handling` table.
- Data schema references from `utils/data_loader.py`, `data/listings.json`, and `data/wardrobe_schema.json`.

Expected output:
- Implementations for `search_listings`, `suggest_outfit`, and `create_fit_card` that keep these parameter names and return keys.

How I will verify:
- Run at least 3 test cases per tool (success, empty/no-result, bad input).
- Confirm outputs match the specified keys and types.
- Confirm failure paths return structured fallbacks (not crashes).

**Milestone 4 — Planning loop and state management:**

AI tool: Claude for logic review + GitHub Copilot for coding (or either one for both steps).

Input I will provide:
- `## Planning Loop` logic steps.
- `## State Management` tracked fields.
- `## Architecture` Mermaid diagram.
- `## A Complete Interaction` walkthrough trace.

Expected output:
- A planning loop that conditionally routes through all three tools and handles each branch exactly as specified.

How I will verify:
- Replay the walkthrough query end-to-end and check exact tool order and payload handoff.
- Simulate one failure in each tool and confirm the loop chooses the correct fallback branch.
- Verify completion condition is met only when final response or clarification is sent.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
<!-- What does the agent do first? Which tool is called? With what input? -->
Agent parses the query and extracts:
- `description = "vintage graphic tee"`
- `size = "L"` (if unavailable, agent asks a clarification first)
- `max_price = 30.0`

First tool call:
`search_listings(description="vintage graphic tee", size="L", max_price=30.0)`

Example return:
- `match_count = 2`
- top matches include `lst_006` ($24, size L) and `lst_015` ($26, size L)

**Step 2:**
<!-- What happens next? What was returned from step 1? What tool is called now? -->
Agent stores search output in session state, selects top result (`lst_006`) as `new_item`, and keeps `lst_015` as alternative.

Second tool call:
`suggest_outfit(new_item=<lst_006 dict>, wardrobe=<user wardrobe dict>)`

Example return:
- `paired_items`: baggy jeans, chunky sneakers, black denim jacket
- `missing_categories = []`
- `styling_notes`: 3 concise reasons
- `confidence = 0.86`

**Step 3:**
<!-- Continue until the full interaction is complete -->
Agent sends outfit payload to formatter.

Third tool call:
`create_fit_card(outfit=<outfit dict>)`

Example return:
- `fit_title = "Vintage Graphic Tee Streetwear Fit"`
- `hero_item`: core listing details (id/title/price/platform/size/condition)
- `style_recipe`: ordered styling steps
- `warnings = []`
- `ready = true`

Agent marks interaction complete and prepares final response with card + one alternative listing.

**Final output to user:**
<!-- What does the user actually see at the end? -->
The user sees a complete recommendation package:
- A fit card for the selected tee with platform and price details.
- Personalized styling using wardrobe items (baggy jeans + chunky sneakers direction).
- One alternative listing under the same budget.
- Any warning/missing-category notes if fallback logic was used.
