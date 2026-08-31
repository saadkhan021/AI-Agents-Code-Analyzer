import time
from langchain_google_genai import ChatGoogleGenerativeAI

from schemas import AuditReport, RefactorResult, DocumentationResult, PipelineState
from prompts import (
    SCANNER_SYSTEM_PROMPT, SCANNER_USER_TEMPLATE,
    REFACTOR_SYSTEM_PROMPT, REFACTOR_USER_TEMPLATE,
    DOCS_SYSTEM_PROMPT, DOCS_USER_TEMPLATE,
    number_lines,
)

# "gemini-3.6-flash" is not a real Gemini model id and every call would fail on it.
# Current stable fast tier as of this writing is gemini-2.0-flash — check
# https://ai.google.dev/gemini-api/docs/models for whatever is current if you hit
# "model not found" errors.
MODEL_NAME = "gemini-3.5-flash"
TEMPERATURE = 0.0
SEED = 42  # fixes the RNG so repeated calls on the same input are far more reproducible
# 4096 is too low: the refactor/docs agents must return the ENTIRE file inside the JSON
# schema, so anything but a tiny snippet gets truncated mid-JSON, fails validation, and
# silently retries — sampling a DIFFERENT result each time. That's why the same pasted
# code could show 3 errors once and 12 the next time.
MAX_OUTPUT_TOKENS = 16000
MAX_RETRIES = 2


def _get_llm(api_key: str):
    """api_key is passed explicitly per call — never read from a global/env var, so one
    user's key can never leak into another user's session on a shared server process."""
    if not api_key:
        raise RuntimeError("No Gemini API key configured for this session.")
    return ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        google_api_key=api_key,
        seed=SEED,
    )


def _invoke_structured(api_key: str, schema_cls, system_prompt: str, user_prompt: str):
    llm = _get_llm(api_key).with_structured_output(schema_cls)
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = llm.invoke([
                ("system", system_prompt),
                ("human", user_prompt),
            ])
            return result
        except Exception as e:  # validation or transient API errors
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(
        f"Structured LLM call failed after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_err}"
    )


#  Node 1: Scanner

def scanner_node(state: PipelineState) -> dict:
    numbered = number_lines(state["raw_code"])
    user_prompt = SCANNER_USER_TEMPLATE.format(
        language=state.get("language", "python"),
        numbered_code=numbered,
    )
    result: AuditReport = _invoke_structured(state["api_key"], AuditReport, SCANNER_SYSTEM_PROMPT, user_prompt)

    log = state.get("status_log", [])
    log.append(f"Scanner Agent: found {len(result.issues)} issue(s).")

    return {
        "audit_report": result.model_dump(),
        "status_log": log,
        "current_step": "scanner_done",
    }


# Node 2: Refactor 

def refactor_node(state: PipelineState) -> dict:
    audit_report = state.get("audit_report") or {"issues": [], "summary": ""}
    user_prompt = REFACTOR_USER_TEMPLATE.format(
        language=state.get("language", "python"),
        raw_code=state["raw_code"],
        audit_report_json=audit_report,
    )
    result: RefactorResult = _invoke_structured(state["api_key"], RefactorResult, REFACTOR_SYSTEM_PROMPT, user_prompt)

    log = state.get("status_log", [])
    log.append(f"Refactor Agent: applied {len(result.changes_made)} change(s), "
               f"{len(result.issues_not_fixed)} left for manual review.")

    return {
        "refactored_code": result.refactored_code,
        "changes_made": result.changes_made,
        "issues_not_fixed": result.issues_not_fixed,
        "status_log": log,
        "current_step": "refactor_done",
    }


#  Node 3: Docs 

def docs_node(state: PipelineState) -> dict:
    user_prompt = DOCS_USER_TEMPLATE.format(
        language=state.get("language", "python"),
        refactored_code=state["refactored_code"],
        changes_made="\n".join(f"- {c}" for c in (state.get("changes_made") or [])),
    )
    result: DocumentationResult = _invoke_structured(state["api_key"], DocumentationResult, DOCS_SYSTEM_PROMPT, user_prompt)

    log = state.get("status_log", [])
    log.append("Docs Agent: generated README and docstring-annotated code.")

    return {
        "readme_markdown": result.readme_markdown,
        "docstring_annotated_code": result.docstring_annotated_code,
        "status_log": log,
        "current_step": "docs_done",
    }