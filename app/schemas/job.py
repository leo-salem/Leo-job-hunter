from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RawJob(BaseModel):
    """A scraper's normalized output before persistence."""

    model_config = ConfigDict(extra="allow")

    source: str
    external_id: str
    title: str
    apply_url: str
    location: Optional[str] = None
    country: Optional[str] = None
    remote: bool = False
    employment_type: Optional[str] = None
    department: Optional[str] = None
    team: Optional[str] = None
    description_html: Optional[str] = None
    description_text: Optional[str] = None
    posted_at: Optional[datetime] = None
    updated_at_source: Optional[datetime] = None
    raw_payload: dict = Field(default_factory=dict)


class CompanySeed(BaseModel):
    slug: str
    name: str
    source: str
    external_id: str
    careers_url: Optional[str] = None
    config: dict = Field(default_factory=dict)
