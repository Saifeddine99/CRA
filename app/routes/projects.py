from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import Project

projects_bp = Blueprint('projects', __name__)

@projects_bp.route('/api/projects', methods=['POST'])
def create_project():
    """Create a new project"""
    data = request.get_json()
    
    required_fields = ['name', 'client_company', 'represented_by', 'supervisor_email']
    for field in required_fields:
        if not data or not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    project = Project(
        name=data['name'],
        client_company=data['client_company'],
        represented_by=data['represented_by'],
        supervisor_email=data['supervisor_email']
    )
    
    try:
        db.session.add(project)
        db.session.commit()
        return jsonify({
            'id': project.id,
            'name': project.name,
            'client_company': project.client_company,
            'represented_by': project.represented_by,
            'supervisor_email': project.supervisor_email,
            'is_active': project.is_active
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create project'}), 500

@projects_bp.route('/api/projects', methods=['GET'])
def get_projects():
    """Get all active projects"""
    projects = Project.query.filter_by(is_active=True).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'client_company': p.client_company,
        'represented_by': p.represented_by,
        'supervisor_email': p.supervisor_email,
        'created_at': p.created_at.isoformat()
    } for p in projects])