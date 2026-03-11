"""
V3.0 Job entity (Documento técnico §7.8).

Domain model: Job represents the business concept of a technical work item associated with an aisle.
For queue/worker implementation (enqueue, dequeue, run job), see src.jobs.
"""

from src.domain.jobs.entities import Job, JobStatus

__all__ = ["Job", "JobStatus"]
