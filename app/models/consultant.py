from datetime import datetime
from app.extensions import db

class Consultant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    timesheet_entries = db.relationship('TimesheetEntry', backref='consultant', lazy=True)
    project_assignments = db.relationship('ProjectAssignment', backref='consultant', lazy=True)