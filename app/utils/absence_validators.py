from datetime import datetime
from app.models import AbsenceRequestType, AbsenceRequestStatus

def validate_absence_request_type(absence_type_str):
    """Validate absence request type enum"""
    try:
        absence_type = AbsenceRequestType(absence_type_str)
        return True, absence_type
    except ValueError:
        return False, "Invalid absence request type"

def validate_absence_request_status(status_str):
    """Validate absence request status enum"""
    try:
        status = AbsenceRequestStatus(status_str)
        return True, status
    except ValueError:
        return False, "Invalid absence request status"

def validate_time_fraction_absence(time_fraction):
    """Validate time fraction for absence (0.5 or 1.0)"""
    if time_fraction not in [0.5, 1.0]:
        return False, "time_fraction must be 0.5 or 1.0 for absence requests"
    return True, ""

def validate_absence_days_data(days_data):
    """Validate the structure and content of absence days data"""
    if not days_data or not isinstance(days_data, list):
        return False, "days must be a non-empty list"
    
    parsed_days = []
    for i, day_data in enumerate(days_data):
        if not isinstance(day_data, dict):
            return False, f"Day {i+1} must be an object"
        
        if 'date' not in day_data or 'time_fraction' not in day_data:
            return False, f"Day {i+1} must have date and time_fraction"
        
        try:
            absence_date = datetime.strptime(day_data['date'], '%Y-%m-%d').date()
        except ValueError:
            return False, f"Day {i+1}: Invalid date format. Use YYYY-MM-DD"
        
        is_valid, error = validate_time_fraction_absence(day_data['time_fraction'])
        if not is_valid:
            return False, f"Day {i+1}: {error}"
        
        parsed_days.append({
            'date': absence_date,
            'time_fraction': day_data['time_fraction']
        })
    
    return True, parsed_days

def validate_annual_absence_limit(consultant_id, absence_type, requested_days, current_year=None):
    """Validate that the absence request doesn't exceed annual limit"""
    from app.extensions import db
    from app.models import AbsenceRequest, AbsenceRequestDay
    
    if current_year is None:
        current_year = datetime.now().year
    
    # Skip validation for Congés Sans Solde
    if absence_type == AbsenceRequestType.CONGES_SANS_SOLDE:
        return True, ""
    
    total_days_requested = sum(day['time_fraction'] for day in requested_days)
    
    # Get existing accepted/pending days for the year (excluding Congés Sans Solde)
    existing_days = db.session.query(db.func.sum(AbsenceRequestDay.time_fraction)).join(AbsenceRequest).filter(
        AbsenceRequest.consultant_id == consultant_id,
        AbsenceRequest.absence_type != AbsenceRequestType.CONGES_SANS_SOLDE,
        AbsenceRequestDay.status.in_([AbsenceRequestStatus.ACCEPTED, AbsenceRequestStatus.PENDING]),
        db.func.strftime('%Y', AbsenceRequestDay.absence_date) == str(current_year)
    ).scalar() or 0
    
    if existing_days + total_days_requested > 25:
        return False, f'Annual absence limit exceeded. Current: {existing_days} days, requesting: {total_days_requested} days. Maximum: 25 days per year (excluding Congés Sans Solde)'
    
    return True, ""

def validate_no_absence_conflicts(consultant_id, requested_days):
    """Check for conflicts with existing absence requests"""
    from app.extensions import db
    from app.models import AbsenceRequest, AbsenceRequestDay
    
    existing_conflicts = []
    for day in requested_days:
        # Check for existing absence requests on the same day
        existing_absence = db.session.query(AbsenceRequestDay).join(AbsenceRequest).filter(
            AbsenceRequest.consultant_id == consultant_id,
            AbsenceRequestDay.absence_date == day['date'],
            AbsenceRequestDay.status.in_([AbsenceRequestStatus.PENDING, AbsenceRequestStatus.ACCEPTED])
        ).first()
        
        if existing_absence:
            existing_conflicts.append(day['date'].isoformat())
    
    if existing_conflicts:
        return False, f'Consultant already has absence requests for these dates: {", ".join(existing_conflicts)}'
    
    return True, ""

def validate_review_decisions(day_decisions, absence_request):
    """Validate HR review decisions for absence request days"""
    if not isinstance(day_decisions, list):
        return False, "day_decisions must be a list"
    
    # Get all day IDs for this request
    request_day_ids = {day.id for day in absence_request.absence_days}
    decision_day_ids = set()
    
    for i, decision in enumerate(day_decisions):
        if not isinstance(decision, dict):
            return False, f"Decision {i+1} must be an object"
        
        if 'day_id' not in decision or 'status' not in decision:
            return False, f"Decision {i+1} must have day_id and status"
        
        day_id = decision['day_id']
        if day_id not in request_day_ids:
            return False, f"Day {day_id} not found in this absence request"
        
        if day_id in decision_day_ids:
            return False, f"Duplicate decision for day {day_id}"
        
        decision_day_ids.add(day_id)
        
        try:
            status = AbsenceRequestStatus(decision['status'])
        except ValueError:
            return False, f"Decision {i+1}: Invalid status"
        
        if status not in [AbsenceRequestStatus.ACCEPTED, AbsenceRequestStatus.REFUSED]:
            return False, f"Decision {i+1}: Status must be 'accepted' or 'refused'"
    
    # Check that all days have decisions
    if decision_day_ids != request_day_ids:
        missing_days = request_day_ids - decision_day_ids
        return False, f"Missing decisions for days: {', '.join(map(str, missing_days))}"
    
    return True, ""