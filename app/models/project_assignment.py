from datetime import datetime
from app.extensions import db

class ProjectAssignment(db.Model):
    """Many-to-many relationship between consultants and projects"""
    id = db.Column(db.Integer, primary_key=True)
    consultant_id = db.Column(db.Integer, db.ForeignKey('consultant.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    position = db.Column(db.String(100), nullable=False)  # Consultant's position on this project
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    starts_at = db.Column(db.DateTime, nullable=False) # Date of the start of the assignment
    ends_at = db.Column(db.DateTime, nullable=False) # Date of the end of the assignment
    is_active = db.Column(db.Boolean, default=True)
    
    # Unique constraint to prevent duplicate assignments
    __table_args__ = (db.UniqueConstraint('consultant_id', 'project_id', name='unique_assignment'),)