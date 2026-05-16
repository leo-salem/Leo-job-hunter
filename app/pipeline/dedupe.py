from __future__ import annotations

from app.schemas.job import RawJob
from app.utils.hashing import fingerprint


def job_fingerprint(job: RawJob) -> str:
    """Stable fingerprint for a job.

    Primary key: (source, external_id). Fallback to apply_url if external_id missing.
    """
    return fingerprint(job.source, job.external_id or job.apply_url)
