from . import db
import enum

class JobStatus(enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"

class Job(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    status = db.Column(db.Enum(JobStatus), default=JobStatus.QUEUED)
    progress = db.Column(db.Integer, default=0)
    step = db.Column(db.String(50))
    error = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    input = db.Column(db.JSON)
    result = db.Column(db.JSON)

    def __repr__(self):
        return f"<Job {self.id}>"
