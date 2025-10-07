from datetime import datetime
from app.extensions import db

class Consultant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    monthly_timesheets = db.relationship('MonthlyTimesheet', backref='consultant', lazy=True, cascade='all, delete-orphan')
    daily_timesheet_entries = db.relationship('DailyTimesheetEntry', backref='consultant', lazy=True, cascade='all, delete-orphan')
    
    absence_requests = db.relationship('AbsenceRequest', backref='consultant', lazy=True, cascade='all, delete-orphan')
    daily_absence_requests = db.relationship('AbsenceRequestDay', backref='consultant', lazy=True, cascade='all, delete-orphan')

    project_assignments = db.relationship('ProjectAssignment', backref='consultant', lazy=True, cascade='all, delete-orphan')