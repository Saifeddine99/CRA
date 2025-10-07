from datetime import datetime
from app.extensions import db

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    client_company = db.Column(db.String(100), nullable=False)
    represented_by = db.Column(db.String(100), nullable=False)
    supervisor_email = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    starts_at = db.Column(db.DateTime, nullable=False) # Date of the start of the project
    ends_at = db.Column(db.DateTime, nullable=False) # Date of the end of the project
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    daily_timesheet_entries = db.relationship('DailyTimesheetEntry', backref='project', lazy=True)
    project_assignments = db.relationship('ProjectAssignment', backref='project', lazy=True, cascade='all, delete-orphan')