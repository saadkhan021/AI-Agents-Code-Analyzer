# AI Code Review Pipeline
 
A sequential multi-agent pipeline that scans, refactors, and documents raw code —
built with **LangGraph**, **LangChain**, **Google Gemini (1.5 Flash)**, and **Streamlit**.
 
```
Scanner Agent  ──▶  Refactor Agent  ──▶  Docs Agent
(Audit Report)      (Clean Code)         (README + Docstrings)
```
 
## Why a pipeline instead of one big prompt?
 
A single "do everything" prompt tends to blend detection, fixing, and writing into one
pass, which is exactly where models start guessing. Splitting the job into three narrow
agents, each with its own schema-constrained output and a fresh minimal context, keeps
every step auditable and cheap.
 
## Accuracy & anti-hallucination design
 
- **Structured output only.** Every agent call uses `with_structured_output(PydanticModel)`,
  so Gemini must return schema-valid JSON — no free-form rambling to hide invented issues in.
- **Evidence-grounded findings.** Every reported `Issue` must include an `evidence` field
  quoted verbatim from the input code. If the model can't cite real code, it has nowhere
  to put a fabricated issue.
- **Scoped edits.** The Refactor Agent is instructed to fix *only* what the Scanner reported
  plus mechanical PEP8 formatting — not to redesign the code.
- **Deterministic decoding.** `temperature=0` on every call.
- **Retry-on-validation-failure.** If structured parsing fails, the call retries once before
  surfacing an error, instead of silently accepting a malformed/guessed result.
 
## Token optimization
 
- Uses `gemini-2.5-flash`, the cheapest capable Gemini tier.
- Each agent receives **only the state it needs** (e.g. Docs Agent never sees the raw audit
  JSON, only the final code + a short change summary) — no growing conversation history is
  replayed on every call.
- Prompts are short and directive; correctness is enforced by schema, not by prompt length.
- `max_output_tokens` is capped per call.
 
## Project structure
 
```
code_review_pipeline/
├── app.py            # Streamlit UI with live per-agent status
├── graph.py           # LangGraph StateGraph wiring (Scanner → Refactor → Docs)
├── agents.py           # The 3 node functions (LLM calls)
├── schemas.py          # Pydantic output schemas + shared TypedDict state
├── prompts.py           # Short, directive prompts per agent
├── requirements.txt
└── .env.example
```
 
## Setup
 
1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
 
2. **Add your Gemini API key**
   ```bash
   cp .env.example .env
   # edit .env and set GOOGLE_API_KEY=your_key_here
   ```
   Get a key at https://aistudio.google.com/app/apikey
 
3. **Run the app**
   ```bash
   streamlit run app.py
   ```
 
4. Paste code into the text box, pick a language, and click **Run Pipeline**. You'll see
   each agent's status update live, then three tabs: Audit Report, Refactored Code, and
   Documentation.
 
## Using it without the UI
 
```python
from graph import build_pipeline, initial_state
 
pipeline = build_pipeline()
result = pipeline.invoke(initial_state(open("my_script.py").read()))
 
print(result["audit_report"])
print(result["refactored_code"])
print(result["readme_markdown"])
```
 
## Notes / limitations
 
- This is a review *assistant*, not a guarantee — always have a human check
  security-critical changes before merging.
- Very large files may need chunking before the Scanner Agent (not implemented here) since
  the whole file is sent in one call.
- Swap `gemini-1.5-flash` for `gemini-1.5-pro` in `agents.py` if you want higher accuracy
  at higher cost/latency for complex codebases.
