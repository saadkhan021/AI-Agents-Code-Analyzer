from __future__ import annotations
from typing import List, Optional, TypedDict
from pydantic import BaseModel, Field


class Issue(BaseModel):
    line_number: int = Field(description="1-indexed line number in the ORIGINAL input code where the issue occurs")
    evidence: str = Field(description="The EXACT snippet copied verbatim from the input code that shows the issue. Never paraphrase this.")
    category: str = Field(description="One of: security, bug, performance, style, best_practice")
    severity: str = Field(description="One of: critical, high, medium, low")
    description: str = Field(description="Short, factual description of the problem. No speculation.")
    suggestion: str = Field(description="Concrete fix. No speculation.")


class AuditReport(BaseModel):
    issues: List[Issue] = Field(default_factory=list, description="Only include issues you can point to with exact evidence. If none found, return an empty list.")
    summary: str = Field(description="1-3 sentence factual summary of overall code health. No exaggeration.")


class RefactorResult(BaseModel):
    refactored_code: str = Field(description="The complete corrected code, PEP8-compliant. Must remain functionally equivalent unless fixing a reported bug.")
    changes_made: List[str] = Field(default_factory=list, description="Bullet list of concrete changes made, each tied to an issue_id or PEP8 rule. No invented improvements beyond scope.")
    issues_not_fixed: List[str] = Field(default_factory=list, description="Any reported issues intentionally left unfixed, with a one-line reason (e.g. needs human judgment).")


class DocumentationResult(BaseModel):
    readme_markdown: str = Field(description="Complete README.md content describing ONLY what the code actually does. No invented features.")
    docstring_annotated_code: str = Field(description="The refactored code with docstrings/comments added. Logic must be byte-for-byte identical to the input code aside from docstrings/comments.")


#  LangGraph shared state 

class PipelineState(TypedDict, total=False):
    # inputs
    raw_code: str
    language: str
    api_key: str  # per-session only, never written to os.environ

    # scanner stage
    audit_report: Optional[dict]

    # refactor stage
    refactored_code: Optional[str]
    changes_made: Optional[List[str]]
    issues_not_fixed: Optional[List[str]]

    # docs stage
    readme_markdown: Optional[str]
    docstring_annotated_code: Optional[str]

    # UI / tracking
    status_log: List[str]
    current_step: str
    error: Optional[str]