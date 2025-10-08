from datetime import datetime
import uuid
from app.extensions import db
from app.models.enums import (
    ActivityType,
    InternalActivityType, 
    AstreinteLocation, 
    AstreinteType,
    AbsenceRequestType,
    ProjectActivityType,
    TimesheetStatus
)

class MonthlyTimesheet(db.Model):
    """Represents a consultant's timesheet for a specific month"""
    id = db.Column(db.Integer, primary_key=True)
    timesheet_reference = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    consultant_id = db.Column(db.Integer, db.ForeignKey('consultant.id'), nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1 to 12
    year = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.Enum(TimesheetStatus), default=TimesheetStatus.SAVED, nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.String(120), nullable=True)  # HR or Manager email
    manager_comments = db.Column(db.Text, nullable=True)

    # Relationships
    #consultant = db.relationship('Consultant', backref=db.backref('monthly_timesheets', lazy=True))
    daily_entries = db.relationship('DailyTimesheetEntry', backref='monthly_timesheet', lazy=True, cascade='all, delete-orphan')

    # Ensure one monthly timesheet per consultant per month-year
    __table_args__ = (
        db.UniqueConstraint('consultant_id', 'month', 'year', name='unique_monthly_timesheet'),
    )


class DailyTimesheetEntry(db.Model):
    """Represents a single workday entry within a monthly timesheet"""
    id = db.Column(db.Integer, primary_key=True)
    work_date = db.Column(db.Date, nullable=False)
    activity_type = db.Column(db.Enum(ActivityType), nullable=False)
    number_of_hours = db.Column(db.Float, nullable=False)  # Number of hours worked
    description = db.Column(db.Text)
    status = db.Column(db.Enum(TimesheetStatus), default=TimesheetStatus.SAVED, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Foreign keys
    monthly_timesheet_id = db.Column(db.Integer, db.ForeignKey('monthly_timesheet.id'), nullable=False)
    consultant_id = db.Column(db.Integer, db.ForeignKey('consultant.id'), nullable=False)

    mission_id = db.Column(db.Integer, db.ForeignKey('ProjectAssignment.id'), nullable=True)
    absence_request_id = db.Column(db.Integer, db.ForeignKey('absence_request.id'), nullable=True)

    # Enums for specific contexts
    mission_activity_type = db.Column(db.Enum(ProjectActivityType), nullable=True)
    internal_activity_type = db.Column(db.Enum(InternalActivityType), nullable=True)
    absence_type = db.Column(db.Enum(AbsenceRequestType), nullable=True)

    # 🟦 New fields for Astreinte
    astreinte_location = db.Column(db.Enum(AstreinteLocation), nullable=True)
    astreinte_type = db.Column(db.Enum(AstreinteType), nullable=True)

    # Unique constraint to prevent duplicate entries per date per consultant
    __table_args__ = (
        db.UniqueConstraint('consultant_id', 'work_date', name='unique_daily_timesheet_entry'),
    )
