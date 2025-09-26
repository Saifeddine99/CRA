from flask import Blueprint, jsonify
from app.models import ActivityType, InternalActivityType, AbsenceType, ProjectActivityType

utils_bp = Blueprint('utils', __name__)

@utils_bp.route('/api/enums', methods=['GET'])
def get_enums():
    """Get all available enum values for frontend"""
    return jsonify({
        'activity_types': [e.value for e in ActivityType],
        'internal_activity_types': [e.value for e in InternalActivityType],
        'absence_types': [e.value for e in AbsenceType],
        'project_activity_types': [e.value for e in ProjectActivityType]
    })