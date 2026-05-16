from __future__ import annotations

from app.db.models import Job, JobLifecycle, Region, Source
from app.pipeline.dedupe import job_fingerprint
from app.schemas.job import RawJob


def new_job_from_raw(
    raw: RawJob,
    *,
    company_id: int,
    normalized_country: str | None,
    region: Region = Region.INTERNATIONAL,
) -> Job:
    return Job(
        company_id=company_id,
        fingerprint=job_fingerprint(raw),
        source=Source(raw.source),
        external_id=raw.external_id,
        title=raw.title,
        location=raw.location,
        country=normalized_country,
        remote=raw.remote,
        employment_type=raw.employment_type,
        department=raw.department,
        team=raw.team,
        description_html=raw.description_html,
        description_text=raw.description_text,
        apply_url=raw.apply_url,
        region=region,
        posted_at=raw.posted_at,
        updated_at_source=raw.updated_at_source,
        lifecycle=JobLifecycle.ACTIVE,
        raw_payload=raw.raw_payload,
    )


def apply_updates(existing: Job, raw: RawJob, *, normalized_country: str | None) -> bool:
    """Mutate `existing` with fresh fields from `raw`. Returns True if anything changed.

    Only updates volatile fields — never touches user-controlled fields
    (favorite, notes, application_status, applied_at) or AI fields.
    """
    changed = False

    def upd(attr: str, new_val) -> None:
        nonlocal changed
        if new_val is None:
            return
        if getattr(existing, attr) != new_val:
            setattr(existing, attr, new_val)
            changed = True

    upd("title", raw.title)
    upd("location", raw.location)
    upd("country", normalized_country)
    upd("remote", raw.remote)
    upd("employment_type", raw.employment_type)
    upd("department", raw.department)
    upd("team", raw.team)
    upd("description_html", raw.description_html)
    upd("description_text", raw.description_text)
    upd("apply_url", raw.apply_url)
    upd("updated_at_source", raw.updated_at_source)

    # Reactivate a previously closed job that reappeared
    if existing.lifecycle == JobLifecycle.CLOSED:
        existing.lifecycle = JobLifecycle.ACTIVE
        existing.closed_at = None
        changed = True

    return changed
