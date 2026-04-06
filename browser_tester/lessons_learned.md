# Workspace Lessons Learned

## Agent Development & Testing

### 1. Strict Browser Verification
**Lesson**: When using the browser subagent for testing, **never** assume a step worked. Always include verification checks.
- **Bad Pattern**: Type "I want a phone" -> Wait -> (Assume list appeared) -> Select phone.
- **Good Pattern**: Type "I want a phone" -> Wait -> **CHECK** (Are phones listed? Is "No devices found" absent?) -> Select phone.
**Impact**: This practice caught a missing file bug (`devices.json`) that a "happy path" script missed.

### 1b. The "Clear Before Typing" Rule
**Lesson**: Frontend input fields may contain default text (e.g. `value="..."` instead of `placeholder`). The `browser_subagent` `browser_press_key` action will append to this text.
- **Problem**: Sending "I need a plan" into a field containing "e.g. I need a plan" results in "e.g. I need a planI need a plan", breaking the agent's parsing.
- **Action**: Always explicitly clear the input field before typing. Use `execute_browser_javascript` (`document.querySelector('input').value = ''`) or simulate "Select All -> Delete".

### 1c. Port Mismatch Triage
**Lesson**: Browser E2E timeouts and `ERR_CONNECTION_REFUSED` are primarily port configuration issues.
- **Action**: Always double-check standard port alignments before running browser tests:
  1. ADK Backend (`adk web`) usually runs on `8000` or `8080`.
  2. Frontend Vite Dev Server usually runs on `5173` or `5174`.
  3. Frontend Proxy (`vite.config.ts` or `a2a.ts`) MUST point to the correct Backend port.
  4. Playwright scripts (`e2e_test.cjs`) MUST point to the correct Frontend Dev Server port.

### 2. Dependency Management in Tool Migration
**Lesson**: When Porting tools from one agent to another, manually audit for external file dependencies.
- **Observation**: Python code imports often work (`import json`), but `open('data.json')` calls fail silently or effectively silently (returning empty lists) if the data file isn't copied.
- **Action**: Grep for `open(` or `read_file` in tool code when migrating.

### 3. A2UI Protocol Validation
**Lesson**: Validating JSON *schema* is required but insufficient. You must also verify *semantics*.
- **Semantics**: Does the "Order" button actually link to the correct URL? Is the "Discount" calculation mathematically correct in the UI text?
- **Tools**: Use `adk run` for schema checks, and `adk web` (browser subagent) for visual/semantic checks.

### 4. Workspace Organization
**Lesson**: Centralized references significantly speed up context recovery.
- **Practice**: Maintain a `GEMINI.md` index that links to all major reference docs and agent directories across the workspace.

### 5. Execution Directory for ADK Web
**Lesson**: Always run `adk web` from the parent workspace directory where all agents are located, NOT from within the agent's own subdirectory.
- **Reason**: The ADK CLI often relies on relative paths and finding the agent configuration from the root context.
- **Pattern**: `cd WorkspacePath && adk web <agent_name>` (Good) vs `cd WorkspacePath/agent_name && adk web .` (Bad/Risky).

### 6. ADK Web Selector
**Lesson**: To see the agent selector UI, run `adk web` without arguments.
- **Command**: `adk web` (in parent directory).
- **Behavior**: Opens the Dev UI where you can select from available agents.
- **Specific**: `adk web <agent_name>` skips the selector and loads that agent directly.

## Hybrid Chat & A2UI Design

### 7. The "Text First" Hybrid Pattern
**Lesson**: For the most natural user experience, always output conversational text **BEFORE** the A2UI JSON payload.
- **Why**: Text provides immediate context ("Here are the plans...") and maintains the conversational flow. If text comes after UI, it can get lost or feel disjointed.
- **Implementation**:
  - **Prompt Rule**: Explicitly instruct: "You MUST write your conversational text response FIRST, and THEN append the `---a2ui_JSON---` block."
  - **Example Consistency**: **Crucial**. Every single example in your few-shot prompt (`a2ui_examples.py`) MUST follow this pattern. If even one example is UI-only, the LLM may hallucinate that behavior.
  - **Correct**: `Sure, here is the data... ---a2ui_JSON--- { ... } ---a2ui_JSON---`
  - **Incorrect**: `---a2ui_JSON--- { ... } ---a2ui_JSON---`

### 8. Interactive Choices over Text Input
**Lesson**: Replace open-ended text questions with "App-like" interactive choices where possible.
- **Scenario**: Asking for "Data Usage" (Light, Medium, Heavy) or "Confirmation" (Yes/No).
- **Bad Pattern**: Text-only question: "How much data do you use?" (User must type "Medium").
- **Good Pattern**: Text question + `Row` of `Button` components.
- **Benefit**: Reduces user friction (one tap vs typing), prevents typos, and feels more premium.
- **Implementation**: Add a specific rule in the prompt: "When asking the user to select from valid options... you MUST generate a UI with `Button` components."

### 9. Relaxed Server-Side Validation
**Lesson**: Your agent code must support *pure text* responses for generic queries.
- **Problem**: Strict validation that raises an error if `---a2ui_JSON---` is missing will break "Hello" or "Help" queries.
- **Fix**: In `agent.py` (stream method), check for the delimiter. If missing, treat the response as valid text-only output. Only attempt to parse/validate JSON if the delimiter is present.

## A2UI Component Usage Guide

This section outlines **generic rules** for choosing the right UI component. Use this as a decision matrix when designing agent responses.

### Content Components
These display static information.

| Component | Use When... | Do Not Use When... |
| :--- | :--- | :--- |
| **Text** | Displaying headings, paragraphs, labels, or prices. Key for conveying information. | You need interactivity (use Button) or structured grouping (use Row/Column). |
| **Image** | Visual impact is needed (product photos, avatars, icons). Enhances engagement. | The image is purely decorative and distracting, or if you don't have a valid high-quality URL. |

### Layout Components
These organize content components.

| Component | Use When... | Do Not Use When... |
| :--- | :--- | :--- |
| **Row** | Arranging items horizontally (e.g., a "Yes/No" button pair, or "Image + Text" side-by-side). | You have a long list of items that might wrap awkwardly on small screens (use List or Column). |
| **Column** | Arranging items vertically (e.g., Title above Price above Description). The default for most content stacks. | You need to save vertical space or link items closely together horizontally. |
| **List** | Displaying a collection of similar items (e.g., a list of devices, plans, or messages). Supports scrolling. | You only have 1 or 2 items (Row/Column is simpler). |
| **Card** | Grouping related content into a distinct visual unit (e.g., a "Plan Card" with title, price, and details). | You are nesting too deeply; Cards inside Cards can look cluttered. |

### Interaction Components
These allow the user to take action.

| Component | Use When... | Do Not Use When... |
| :--- | :--- | :--- |
| **Button** | The user needs to make a selection, confirm an action, or navigate to a link. **Critical for "Choices".** | You just want to display text (use Text). |

### Common Patterns & Recipes

#### 1. The "Choice" Recipe
**Goal**: Ask user to pick from a set of options (e.g., size, color, yes/no).
- **Correct**: `Text` (Question) + `Row` (containing `Button`s).
- **Why**: Buttons are easier to tap than typing; clear visual affordance.

#### 2. The "Product" Recipe
**Goal**: Show a product (phone, plan) with details.
- **Correct**: `Card` -> `Row` (Image + `Column` (Title, Price, Details)).
- **Why**: Card provides a boundary; Row/Column organizes the internal layout.

#### 3. The "Carousel" Recipe
**Goal**: Show multiple products side-by-side.
- **Correct**: `Row` (with `distribution: start` and `explicitList` of Cards).
- **Why**: Allows scanning multiple options horizontally.

## Frontend Renderer Development (Generic Client)
**Context**: Building a generic A2UI client by refactoring sample clients into reusable shells.

### Critical Implementation Details
1.  **Hybrid Chat Pattern**:
    -   **Text First**: Ensure the client handles `text` parts *before* `data` parts in the stream. Refactor `client.ts` to yield `ClientResponsePart[]` so the UI can render text bubbles immediately while waiting for the JSON payload.
    -   **Interleaved Streaming**: The client must separate the `---a2ui_JSON---` delimiter cleanly. If the stream typically sends text then JSON, simple string splitting works, but robust parsing should handle chunks.

2.  **A2UI Rendering Integration**:
    -   **Event Listening**: The `A2UISurface` component needs to listen for BOTH `surfaceUpdate` (standard) and `beginRendering` (initial) events.
    -   **Container Logic**: When rendering A2UI within a chat bubble, ensure the container (`<div>` or similar) has a defined width/height context, or the Lit renderer might collapse.

3.  **Build & Dependencies**:
    -   **@a2ui/lit Path**: When moving the sample code, update `package.json` and `tsconfig.json` to point to the correct *relative path* of the renderer (e.g., `../../reference_repos/a2ui/renderers/lit`) or a built artifact.
    -   **Wireit**: This tool is used for build scripts in the reference repo. Ensure it is installed (`npm install wireit --save-dev`) or available in the path if `npm run build` relies on it.
    -   **Vite Config**: Ensure `vite.config.ts` correctly proxies requests to the ADK server (default port 8000) to avoid CORS issues during local dev.

4.  **Python 3.13 Stability**:
    -   **Pydantic Compat**: The ADK server (via `mcp` and `fastapi`) may crash on Python 3.13 due to Pydantic schema generation issues with `ClientSession` or `GenericAlias`.
    -   **Fix**: Apply strict monkey-patches to `pydantic._internal._generate_schema` to fallback to `any_schema` for unknown types. This is critical for keeping the dev server alive.
