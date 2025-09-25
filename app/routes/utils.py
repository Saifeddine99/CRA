from flask import Blueprint, jsonify
from app.models import ActivityType, InternalActivityType, AbsenceType, WorkLocation

utils_bp = Blueprint('utils', __name__)

@utils_bp.route('/api/enums', methods=['GET'])
def get_enums():
    """Get all available enum values for frontend"""
    return jsonify({
        'activity_types': [e.value for e in ActivityType],
        'internal_activity_types': [e.value for e in InternalActivityType],
        'absence_types': [e.value for e in AbsenceType],
        'work_locations': [e.value for e in WorkLocation]
    })