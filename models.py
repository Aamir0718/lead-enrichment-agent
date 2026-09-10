"""Pydantic schemas shared across the pipeline."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TeamMember(BaseModel):
    """A leadership / team member discovered on the site."""

    name: str
    role: Optional[str] = Field(default=None, description="Title or role, e.g. 'CEO & Co-founder'")
    linkedin_url: Optional[str] = Field(default=None, description="LinkedIn profile URL if present")


class ExtractionResult(BaseModel):
    """Raw structured output requested from the LLM (Extractor Agent)."""

    company_overview: str = Field(description="Concise 2-sentence summary of what the company does")
    target_audience: str = Field(description="Who the product/service is built for (the ICP)")
    contact_emails: List[str] = Field(default_factory=list)
    leadership: List[TeamMember] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0, description="LLM's own estimate of data completeness/quality")


class CompanyIntel(BaseModel):
    """Final per-domain record written to output.json."""

    domain: str
    status: str = "success"  # success | partial | failed
    error: Optional[str] = None

    company_overview: Optional[str] = None
    target_audience: Optional[str] = None
    contact_emails: List[str] = Field(default_factory=list)
    leadership: List[TeamMember] = Field(default_factory=list)

    confidence_score: float = 0.0
    critique_notes: List[str] = Field(default_factory=list)

    pages_scraped: List[str] = Field(default_factory=list)
    llm_calls_used: int = 0

    source_text: str = Field(
        default="",
        description=(
            "The cleaned, scraped text actually sent to the LLM for extraction -- kept "
            "as evidence so every field above can be checked against its source instead "
            "of taken on faith."
        ),
    )
