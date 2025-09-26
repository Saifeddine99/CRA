from datetime import datetime
from app.extensions import db
from app.models.enums import ActivityType, InternalActivityType, AbsenceType, ProjectActivityType

class TimesheetEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_date = db.Column(db.Date, nullable=False)
    activity_type = db.Column(db.Enum(ActivityType), nullable=False)
    time_fraction = db.Column(db.Float, nullable=False)  # Must be between 0 and 1
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    consultant_id = db.Column(db.Integer, db.ForeignKey('consultant.id'), nullable=False)
    
    # Project-specific fields (only for PROJECT activity type)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    project_activity_type = db.Column(db.Enum(ProjectActivityType), nullable=True)
    
    # Internal activity fields (only for INTERNAL activity type)
    internal_activity_type = db.Column(db.Enum(InternalActivityType), nullable=True)
    
    # Absence fields (only for ABSENCE activity type)
    absence_type = db.Column(db.Enum(AbsenceType), nullable=True)