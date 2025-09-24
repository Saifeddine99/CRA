from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date
import calendar
import os

app = Flask(__name__)
CORS(app)  # allow all domains for all routes
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///timesheet.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

with app.app_context():
    db.create_all()

# Models
class Consultant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    projects = db.relationship('Project', backref='consultant', lazy=True)
    timesheet_entries = db.relationship('TimesheetEntry', backref='consultant', lazy=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    client_company = db.Column(db.String(100), nullable=False)
    consultant_position = db.Column(db.String(100), nullable=False)
    represented_by = db.Column(db.String(100), nullable=False)
    supervisor_email = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Foreign Keys
    consultant_id = db.Column(db.Integer, db.ForeignKey('consultant.id'), nullable=False)
    
    # Relationships
    timesheet_entries = db.relationship('TimesheetEntry', backref='project', lazy=True)

class TimesheetEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_date = db.Column(db.Date, nullable=False)
    hours_worked = db.Column(db.Float, nullable=False, default=0.0)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    consultant_id = db.Column(db.Integer, db.ForeignKey('consultant.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    
    # Constraints
    __table_args__ = (db.UniqueConstraint('consultant_id', 'project_id', 'work_date', name='unique_daily_entry'),)

# API Routes
@app.route('/api/consultants', methods=['POST'])
def create_consultant():
    """Create a new consultant"""
    data = request.get_json()
    
    if not data or not data.get('name') or not data.get('email'):
        return jsonify({'error': 'Name and email are required'}), 400
    
    # Check if consultant already exists
    existing = Consultant.query.filter_by(email=data['email']).first()
    if existing:
        return jsonify({'error': 'Consultant with this email already exists'}), 400
    
    consultant = Consultant(
        name=data['name'],
        email=data['email']
    )
    
    try:
        db.session.add(consultant)
        db.session.commit()
        return jsonify({
            'id': consultant.id,
            'name': consultant.name,
            'email': consultant.email
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create consultant'}), 500

@app.route('/api/consultants', methods=['GET'])
def get_consultants():
    """Get all consultants"""
    consultants = Consultant.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'email': c.email,
        'created_at': c.created_at.isoformat()
    } for c in consultants])

@app.route('/api/consultants/<int:consultant_id>/projects', methods=['POST'])
def create_project(consultant_id):
    """Create a new project for a consultant"""
    data = request.get_json()
    
    # Validate consultant exists
    consultant = Consultant.query.get_or_404(consultant_id)
    
    required_fields = ['name', 'client_company', 'consultant_position', 'represented_by', 'supervisor_email']
    for field in required_fields:
        if not data or not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    project = Project(
        name=data['name'],
        client_company=data['client_company'],
        consultant_position=data['consultant_position'],
        represented_by=data['represented_by'],
        supervisor_email=data['supervisor_email'],
        consultant_id=consultant_id
    )
    
    try:
        db.session.add(project)
        db.session.commit()
        return jsonify({
            'id': project.id,
            'name': project.name,
            'client_company': project.client_company,
            'consultant_position': project.consultant_position,
            'represented_by': project.represented_by,
            'supervisor_email': project.supervisor_email,
            'is_active': project.is_active
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create project'}), 500

@app.route('/api/consultants/<int:consultant_id>/projects', methods=['GET'])
def get_consultant_projects(consultant_id):
    """Get all projects for a consultant"""
    consultant = Consultant.query.get_or_404(consultant_id)
    projects = Project.query.filter_by(consultant_id=consultant_id, is_active=True).all()
    
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'client_company': p.client_company,
        'consultant_position': p.consultant_position,
        'represented_by': p.represented_by,
        'supervisor_email': p.supervisor_email,
        'created_at': p.created_at.isoformat()
    } for p in projects])

@app.route('/api/timesheet-entries', methods=['POST'])
def create_timesheet_entry():
    """Create or update a timesheet entry"""
    data = request.get_json()
    
    required_fields = ['consultant_id', 'project_id', 'work_date', 'hours_worked']
    for field in required_fields:
        if not data or field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    # Validate consultant and project exist
    consultant = Consultant.query.get_or_404(data['consultant_id'])
    project = Project.query.get_or_404(data['project_id'])
    
    # Validate project belongs to consultant
    if project.consultant_id != data['consultant_id']:
        return jsonify({'error': 'Project does not belong to this consultant'}), 400
    
    # Parse date
    try:
        work_date = datetime.strptime(data['work_date'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    
    # Check if entry already exists
    existing_entry = TimesheetEntry.query.filter_by(
        consultant_id=data['consultant_id'],
        project_id=data['project_id'],
        work_date=work_date
    ).first()
    
    if existing_entry:
        # Update existing entry
        existing_entry.hours_worked = data['hours_worked']
        existing_entry.description = data.get('description', '')
        existing_entry.updated_at = datetime.utcnow()
        entry = existing_entry
    else:
        # Create new entry
        entry = TimesheetEntry(
            consultant_id=data['consultant_id'],
            project_id=data['project_id'],
            work_date=work_date,
            hours_worked=data['hours_worked'],
            description=data.get('description', '')
        )
        db.session.add(entry)
    
    try:
        db.session.commit()
        return jsonify({
            'id': entry.id,
            'work_date': entry.work_date.isoformat(),
            'hours_worked': entry.hours_worked,
            'description': entry.description,
            'project_name': project.name,
            'client_company': project.client_company
        }), 200 if existing_entry else 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to save timesheet entry'}), 500

@app.route('/api/consultants/<int:consultant_id>/timesheet/<int:year>/<int:month>', methods=['GET'])
def get_monthly_timesheet(consultant_id, year, month):
    """Get monthly timesheet for a consultant"""
    consultant = Consultant.query.get_or_404(consultant_id)
    
    # Validate month and year
    if not (1 <= month <= 12) or year < 2020 or year > 2030:
        return jsonify({'error': 'Invalid month or year'}), 400
    
    # Get first and last day of month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    
    # Query timesheet entries for the month
    entries = db.session.query(TimesheetEntry, Project).join(Project).filter(
        TimesheetEntry.consultant_id == consultant_id,
        TimesheetEntry.work_date >= first_day,
        TimesheetEntry.work_date <= last_day
    ).order_by(TimesheetEntry.work_date, Project.name).all()
    
    # Group by project
    projects_data = {}
    total_hours = 0
    
    for entry, project in entries:
        if project.id not in projects_data:
            projects_data[project.id] = {
                'project_id': project.id,
                'project_name': project.name,
                'client_company': project.client_company,
                'consultant_position': project.consultant_position,
                'represented_by': project.represented_by,
                'supervisor_email': project.supervisor_email,
                'entries': [],
                'total_hours': 0
            }
        
        projects_data[project.id]['entries'].append({
            'date': entry.work_date.isoformat(),
            'hours': entry.hours_worked,
            'description': entry.description
        })
        projects_data[project.id]['total_hours'] += entry.hours_worked
        total_hours += entry.hours_worked
    
    return jsonify({
        'consultant': {
            'id': consultant.id,
            'name': consultant.name,
            'email': consultant.email
        },
        'period': {
            'year': year,
            'month': month,
            'month_name': calendar.month_name[month]
        },
        'projects': list(projects_data.values()),
        'total_hours': total_hours,
        'total_days_worked': len(set(entry.work_date for entry, _ in entries))
    })

@app.route('/api/consultants/<int:consultant_id>/timesheet/<int:year>/<int:month>/summary', methods=['GET'])
def get_monthly_summary(consultant_id, year, month):
    """Get monthly summary for invoice generation"""
    consultant = Consultant.query.get_or_404(consultant_id)
    
    # Get the monthly timesheet data
    timesheet_response = get_monthly_timesheet(consultant_id, year, month)
    timesheet_data = timesheet_response.get_json()
    
    if not timesheet_data['projects']:
        return jsonify({'message': 'No timesheet entries found for this period'}), 404
    
    # Calculate summary by project
    summary = {
        'consultant': timesheet_data['consultant'],
        'period': timesheet_data['period'],
        'projects_summary': [],
        'total_hours': timesheet_data['total_hours'],
        'total_days_worked': timesheet_data['total_days_worked']
    }
    
    for project in timesheet_data['projects']:
        summary['projects_summary'].append({
            'project_name': project['project_name'],
            'client_company': project['client_company'],
            'consultant_position': project['consultant_position'],
            'represented_by': project['represented_by'],
            'supervisor_email': project['supervisor_email'],
            'total_hours': project['total_hours'],
            'days_worked': len(project['entries'])
        })
    
    return jsonify(summary)

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Create database tables
    with app.app_context():
        db.create_all()
    
    app.run(debug=True, port=5000)