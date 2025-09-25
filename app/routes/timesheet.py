from flask import Blueprint, request, jsonify
from datetime import datetime, date
import calendar
from app.extensions import db
from app.models import (Consultant, Project, ProjectAssignment, TimesheetEntry,
                       ActivityType, InternalActivityType, AbsenceType, WorkLocation)

timesheet_bp = Blueprint('timesheet', __name__)

@timesheet_bp.route('/api/timesheet-entries', methods=['POST'])
def create_timesheet_entry():
    """Create a timesheet entry"""
    data = request.get_json()
    
    required_fields = ['consultant_id', 'work_date', 'activity_type', 'time_fraction']
    for field in required_fields:
        if not data or field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    # Validate consultant exists
    consultant = Consultant.query.get_or_404(data['consultant_id'])
    
    # Validate activity type
    try:
        activity_type = ActivityType(data['activity_type'])
    except ValueError:
        return jsonify({'error': 'Invalid activity type'}), 400
    
    # Validate time fraction
    time_fraction = data['time_fraction']
    if not isinstance(time_fraction, (int, float)) or time_fraction <= 0 or time_fraction > 1:
        return jsonify({'error': 'time_fraction must be between 0 and 1'}), 400
    
    # Parse date
    try:
        work_date = datetime.strptime(data['work_date'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    
    # Check daily time fraction limit
    existing_entries = TimesheetEntry.query.filter_by(
        consultant_id=data['consultant_id'],
        work_date=work_date
    ).all()
    
    current_total = sum(entry.time_fraction for entry in existing_entries)
    if current_total + time_fraction > 1.0001:  # Small tolerance for floating point
        return jsonify({
            'error': f'Daily time fraction limit exceeded. Current total: {current_total:.2f}, trying to add: {time_fraction:.2f}'
        }), 400
    
    # Validate activity-specific fields
    entry_data = {
        'consultant_id': data['consultant_id'],
        'work_date': work_date,
        'activity_type': activity_type,
        'time_fraction': time_fraction,
        'description': data.get('description', '')
    }
    
    if activity_type == ActivityType.PROJECT:
        if not data.get('project_id') or not data.get('work_location'):
            return jsonify({'error': 'project_id and work_location are required for project activities'}), 400
        
        # Validate project exists and consultant is assigned
        project = Project.query.get_or_404(data['project_id'])
        assignment = ProjectAssignment.query.filter_by(
            consultant_id=data['consultant_id'],
            project_id=data['project_id'],
            is_active=True
        ).first()
        
        if not assignment:
            return jsonify({'error': 'Consultant is not assigned to this project'}), 400
        
        try:
            work_location = WorkLocation(data['work_location'])
        except ValueError:
            return jsonify({'error': 'Invalid work location'}), 400
        
        entry_data['project_id'] = data['project_id']
        entry_data['work_location'] = work_location
    
    elif activity_type == ActivityType.INTERNAL:
        if not data.get('internal_activity_type'):
            return jsonify({'error': 'internal_activity_type is required for internal activities'}), 400
        
        try:
            internal_type = InternalActivityType(data['internal_activity_type'])
        except ValueError:
            return jsonify({'error': 'Invalid internal activity type'}), 400
        
        entry_data['internal_activity_type'] = internal_type
    
    elif activity_type == ActivityType.ABSENCE:
        if not data.get('absence_type'):
            return jsonify({'error': 'absence_type is required for absence activities'}), 400
        
        try:
            absence_type = AbsenceType(data['absence_type'])
        except ValueError:
            return jsonify({'error': 'Invalid absence type'}), 400
        
        entry_data['absence_type'] = absence_type
    
    entry = TimesheetEntry(**entry_data)
    
    try:
        db.session.add(entry)
        db.session.commit()
        
        # Build response data
        response_data = {
            'id': entry.id,
            'work_date': entry.work_date.isoformat(),
            'activity_type': entry.activity_type.value,
            'time_fraction': entry.time_fraction,
            'description': entry.description
        }
        
        if entry.activity_type == ActivityType.PROJECT:
            response_data.update({
                'project_id': entry.project_id,
                'project_name': entry.project.name,
                'client_company': entry.project.client_company,
                'work_location': entry.work_location.value
            })
        elif entry.activity_type == ActivityType.INTERNAL:
            response_data['internal_activity_type'] = entry.internal_activity_type.value
        elif entry.activity_type == ActivityType.ABSENCE:
            response_data['absence_type'] = entry.absence_type.value
        
        return jsonify(response_data), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create timesheet entry'}), 500

@timesheet_bp.route('/api/consultants/<int:consultant_id>/timesheet/<int:year>/<int:month>', methods=['GET'])
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
    entries = TimesheetEntry.query.filter(
        TimesheetEntry.consultant_id == consultant_id,
        TimesheetEntry.work_date >= first_day,
        TimesheetEntry.work_date <= last_day
    ).order_by(TimesheetEntry.work_date).all()
    
    # Group entries by date
    daily_entries = {}
    total_project_time = 0
    total_internal_time = 0
    total_absence_time = 0
    
    for entry in entries:
        date_str = entry.work_date.isoformat()
        if date_str not in daily_entries:
            daily_entries[date_str] = {
                'date': date_str,
                'activities': [],
                'total_time': 0
            }
        
        activity_data = {
            'id': entry.id,
            'activity_type': entry.activity_type.value,
            'time_fraction': entry.time_fraction,
            'description': entry.description
        }
        
        if entry.activity_type == ActivityType.PROJECT:
            activity_data.update({
                'project_id': entry.project_id,
                'project_name': entry.project.name,
                'client_company': entry.project.client_company,
                'work_location': entry.work_location.value
            })
            total_project_time += entry.time_fraction
        elif entry.activity_type == ActivityType.INTERNAL:
            activity_data['internal_activity_type'] = entry.internal_activity_type.value
            total_internal_time += entry.time_fraction
        elif entry.activity_type == ActivityType.ABSENCE:
            activity_data['absence_type'] = entry.absence_type.value
            total_absence_time += entry.time_fraction
        
        daily_entries[date_str]['activities'].append(activity_data)
        daily_entries[date_str]['total_time'] += entry.time_fraction
    
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
        'daily_entries': list(daily_entries.values()),
        'summary': {
            'total_project_time': total_project_time,
            'total_internal_time': total_internal_time,
            'total_absence_time': total_absence_time,
            'total_working_days': len([d for d in daily_entries.values() if d['total_time'] > 0])
        }
    })

@timesheet_bp.route('/api/consultants/<int:consultant_id>/timesheet/<int:year>/<int:month>/summary', methods=['GET'])
def get_monthly_summary(consultant_id, year, month):
    """Get monthly summary grouped by projects and activity types"""
    consultant = Consultant.query.get_or_404(consultant_id)
    
    # Get first and last day of month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    
    entries = TimesheetEntry.query.filter(
        TimesheetEntry.consultant_id == consultant_id,
        TimesheetEntry.work_date >= first_day,
        TimesheetEntry.work_date <= last_day
    ).all()
    
    if not entries:
        return jsonify({'message': 'No timesheet entries found for this period'}), 404
    
    # Group by projects and activity types
    projects_summary = {}
    internal_summary = {}
    absence_summary = {}
    
    for entry in entries:
        if entry.activity_type == ActivityType.PROJECT:
            project_id = entry.project_id
            if project_id not in projects_summary:
                projects_summary[project_id] = {
                    'project_id': project_id,
                    'project_name': entry.project.name,
                    'client_company': entry.project.client_company,
                    'represented_by': entry.project.represented_by,
                    'supervisor_email': entry.project.supervisor_email,
                    'total_time': 0,
                    'remote_time': 0,
                    'on_site_time': 0,
                    'hybrid_time': 0,
                    'days_worked': set()
                }
            
            projects_summary[project_id]['total_time'] += entry.time_fraction
            projects_summary[project_id]['days_worked'].add(entry.work_date)
            
            if entry.work_location == WorkLocation.REMOTE:
                projects_summary[project_id]['remote_time'] += entry.time_fraction
            elif entry.work_location == WorkLocation.ON_SITE:
                projects_summary[project_id]['on_site_time'] += entry.time_fraction
            elif entry.work_location == WorkLocation.HYBRID:
                projects_summary[project_id]['hybrid_time'] += entry.time_fraction
        
        elif entry.activity_type == ActivityType.INTERNAL:
            activity_type = entry.internal_activity_type.value
            if activity_type not in internal_summary:
                internal_summary[activity_type] = {
                    'activity_type': activity_type,
                    'total_time': 0,
                    'days_count': set()
                }
            internal_summary[activity_type]['total_time'] += entry.time_fraction
            internal_summary[activity_type]['days_count'].add(entry.work_date)
        
        elif entry.activity_type == ActivityType.ABSENCE:
            absence_type = entry.absence_type.value
            if absence_type not in absence_summary:
                absence_summary[absence_type] = {
                    'absence_type': absence_type,
                    'total_time': 0,
                    'days_count': set()
                }
            absence_summary[absence_type]['total_time'] += entry.time_fraction
            absence_summary[absence_type]['days_count'].add(entry.work_date)
    
    # Convert sets to counts
    for project in projects_summary.values():
        project['days_worked'] = len(project['days_worked'])
    
    for activity in internal_summary.values():
        activity['days_count'] = len(activity['days_count'])
    
    for absence in absence_summary.values():
        absence['days_count'] = len(absence['days_count'])
    
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
        'projects_summary': list(projects_summary.values()),
        'internal_activities_summary': list(internal_summary.values()),
        'absences_summary': list(absence_summary.values()),
        'totals': {
            'total_project_time': sum(p['total_time'] for p in projects_summary.values()),
            'total_internal_time': sum(a['total_time'] for a in internal_summary.values()),
            'total_absence_time': sum(a['total_time'] for a in absence_summary.values())
        }
    })

@timesheet_bp.route('/api/consultants/<int:consultant_id>/daily-validation/<work_date>', methods=['GET'])
def validate_daily_time(consultant_id, work_date):
    """Check current time allocation for a specific day"""
    try:
        parsed_date = datetime.strptime(work_date, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
    
    entries = TimesheetEntry.query.filter_by(
        consultant_id=consultant_id,
        work_date=parsed_date
    ).all()
    
    total_time = sum(entry.time_fraction for entry in entries)
    remaining_time = 1.0 - total_time
    
    return jsonify({
        'work_date': work_date,
        'total_allocated_time': total_time,
        'remaining_time': max(0, remaining_time),
        'is_complete': abs(total_time - 1.0) < 0.001,
        'entries_count': len(entries)
    })