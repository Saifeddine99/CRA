from flask import Blueprint, request, jsonify
from datetime import datetime
from app.extensions import db
from app.models import Consultant, Project, ProjectAssignment

project_assignments_bp = Blueprint('project_assignments', __name__)

@project_assignments_bp.route('/api/project-assignments', methods=['POST'])
def assign_consultant_to_project():
    """Assign a consultant to a project"""
    data = request.get_json()
    
    required_fields = ['consultant_id', 'project_id', 'position', 'starts_at', 'ends_at']
    for field in required_fields:
        if not data or field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    # Validate consultant and project exist
    consultant = Consultant.query.get_or_404(data['consultant_id'])
    project = Project.query.get_or_404(data['project_id'])

    # Validate starts_at and ends_at
    try:
        starts_at = datetime.strptime(data['starts_at'], '%Y-%m-%d').date()
        ends_at = datetime.strptime(data['ends_at'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # Check if starts_at is after project starts_at
    if starts_at < project.starts_at:
        return jsonify({'error': 'Start date cannot be before project start date'}), 400

    # Check if ends_at is before project ends_at
    if ends_at > project.ends_at:
        return jsonify({'error': 'End date cannot be after project end date'}), 400
    
    # Check if assignment already exists
    existing = ProjectAssignment.query.filter_by(
        consultant_id=data['consultant_id'],
        project_id=data['project_id']
    ).first()
    
    if existing:
        if existing.is_active:
            return jsonify({'error': 'Consultant is already assigned to this project'}), 400
        else:
            # Reactivate existing assignment
            existing.is_active = True
            existing.position = data['position']
            existing.assigned_at = datetime.utcnow()
            assignment = existing
    else:
        assignment = ProjectAssignment(
            consultant_id=data['consultant_id'],
            project_id=data['project_id'],
            position=data['position'],
            starts_at=starts_at,
            ends_at=ends_at
        )
        db.session.add(assignment)
    
    try:
        db.session.commit()
        return jsonify({
            'id': assignment.id,
            'consultant_name': consultant.name,
            'project_name': project.name,
            'position': assignment.position,
            'assigned_at': assignment.assigned_at.isoformat(),
            'starts_at': assignment.starts_at.isoformat(),
            'ends_at': assignment.ends_at.isoformat()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create assignment'}), 500