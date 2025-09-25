from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Consultant, ProjectAssignment, Project

consultants_bp = Blueprint('consultants', __name__)

@consultants_bp.route('/api/consultants', methods=['POST'])
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

@consultants_bp.route('/api/consultants', methods=['GET'])
def get_consultants():
    """Get all consultants"""
    consultants = Consultant.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'email': c.email,
        'created_at': c.created_at.isoformat()
    } for c in consultants])

@consultants_bp.route('/api/consultants/<int:consultant_id>/projects', methods=['GET'])
def get_consultant_projects(consultant_id):
    """Get all active projects assigned to a consultant"""
    consultant = Consultant.query.get_or_404(consultant_id)
    
    assignments = db.session.query(ProjectAssignment, Project).join(Project).filter(
        ProjectAssignment.consultant_id == consultant_id,
        ProjectAssignment.is_active == True,
        Project.is_active == True
    ).all()
    
    return jsonify([{
        'assignment_id': assignment.id,
        'project_id': project.id,
        'project_name': project.name,
        'client_company': project.client_company,
        'consultant_position': assignment.position,
        'represented_by': project.represented_by,
        'supervisor_email': project.supervisor_email
    } for assignment, project in assignments])