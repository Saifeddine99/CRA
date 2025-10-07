from datetime import datetime
import uuid
from app.extensions import db
from app.models.enums import AbsenceRequestType, AbsenceRequestStatus

class AbsenceRequest(db.Model):
    """Main absence request containing multiple days"""
    id = db.Column(db.Integer, primary_key=True)
    request_reference = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    consultant_id = db.Column(db.Integer, db.ForeignKey('consultant.id'), nullable=False)
    absence_type = db.Column(db.Enum(AbsenceRequestType), nullable=False)
    commentary = db.Column(db.Text, nullable=True)
    justification = db.Column(db.Text, nullable=True)
    status = db.Column(db.Enum(AbsenceRequestStatus), default=AbsenceRequestStatus.PENDING, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.String(120), nullable=True)  # HR person email
    hr_comments = db.Column(db.Text, nullable=True)

    # 🔹 New field: link to a specific project assignment if the absence is related to one
    assigned_project_id = db.Column(db.Integer, db.ForeignKey('project_assignment.id'), nullable=True)

    # Relationships
    consultant = db.relationship('Consultant', backref=db.backref('absence_requests', lazy=True))
    assigned_project = db.relationship('ProjectAssignment', backref=db.backref('absence_requests', lazy=True))
    absence_days = db.relationship('AbsenceRequestDay', backref='absence_request', lazy=True, cascade='all, delete-orphan')
    timesheet_entries = db.relationship('TimesheetEntry', backref='related_absence_request', lazy=True, cascade='all, delete-orphan')


class AbsenceRequestDay(db.Model):
    """Individual days within an absence request"""
    id = db.Column(db.Integer, primary_key=True)
    absence_request_id = db.Column(db.Integer, db.ForeignKey('absence_request.id'), nullable=False)
    absence_date = db.Column(db.Date, nullable=False)
    number_of_hours = db.Column(db.Float, nullable=False)  # Number of hours of the absence
    status = db.Column(db.Enum(AbsenceRequestStatus), default=AbsenceRequestStatus.PENDING, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint to prevent duplicate absence requests for the same day
    __table_args__ = (
        db.UniqueConstraint('absence_request_id', 'absence_date', name='unique_absence_day'),
        db.Index('idx_consultant_date', 'absence_date')
    )
