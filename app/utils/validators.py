from datetime import datetime
from app.models import ActivityType, InternalActivityType, AbsenceRequestType, ProjectActivityType

def validate_required_fields(data, required_fields):
    """Validate that required fields are present in data"""
    if not data:
        return False, "No data provided"
    
    for field in required_fields:
        if field not in data or not data.get(field):
            return False, f"{field} is required"
    
    return True, ""

def validate_time_fraction(time_fraction):
    """Validate time fraction is between 0 and 1"""
    if not isinstance(time_fraction, (int, float)):
        return False, "time_fraction must be a number"
    
    if time_fraction <= 0 or time_fraction > 1:
        return False, "time_fraction must be between 0 and 1"
    
    return True, ""

def validate_date_format(date_string):
    """Validate date string is in YYYY-MM-DD format"""
    try:
        parsed_date = datetime.strptime(date_string, '%Y-%m-%d').date()
        return True, parsed_date
    except ValueError:
        return False, "Invalid date format. Use YYYY-MM-DD"

def validate_activity_type(activity_type_str):
    """Validate activity type enum"""
    try:
        activity_type = ActivityType(activity_type_str)
        return True, activity_type
    except ValueError:
        return False, "Invalid activity type"

def validate_internal_activity_type(internal_type_str):
    """Validate internal activity type enum"""
    try:
        internal_type = InternalActivityType(internal_type_str)
        return True, internal_type
    except ValueError:
        return False, "Invalid internal activity type"

def validate_absence_type(absence_type_str):
    """Validate absence type enum"""
    try:
        absence_type = AbsenceRequestType(absence_type_str)
        return True, absence_type
    except ValueError:
        return False, "Invalid absence type"

def validate_project_activity_type(project_activity_type_str):
    """Validate project activity type enum"""
    try:
        project_activity_type = ProjectActivityType(project_activity_type_str)
        return True, project_activity_type
    except ValueError:
        return False, "Invalid project activity type"

def validate_year_month(year, month):
    """Validate year and month are within reasonable ranges"""
    if not (1 <= month <= 12):
        return False, "Month must be between 1 and 12"
    
    if year < 2020 or year > 2030:
        return False, "Year must be between 2020 and 2030"
    
    return True, ""

def validate_email_format(email):
    """Basic email format validation"""
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(email_pattern, email):
        return True, ""
    return False, "Invalid email format"