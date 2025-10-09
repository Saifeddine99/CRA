from flask import Blueprint, jsonify
from app.models import (ActivityType, InternalActivityType, ProjectActivityType,
                       AbsenceRequestType, AbsenceRequestStatus, TimesheetStatus, AstreinteType, AstreinteLocation)

utils_bp = Blueprint('utils', __name__)

@utils_bp.route('/api/enums', methods=['GET'])
def get_enums():
    """Get all available enum values for frontend"""
    return jsonify({
        'activity_types': [e.value for e in ActivityType],
        'internal_activity_types': [e.value for e in InternalActivityType],
        'project_activity_types': [e.value for e in ProjectActivityType],
        'absence_request_types': [e.value for e in AbsenceRequestType],
        'absence_request_statuses': [e.value for e in AbsenceRequestStatus],
        'timesheet_statuses': [e.value for e in TimesheetStatus],
        'astreinte_locations': [e.value for e in AstreinteLocation],
        'astreinte_types': [e.value for e in AstreinteType]
    })