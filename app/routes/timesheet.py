from flask import Blueprint, request, jsonify
from datetime import datetime, date
import calendar
from app.extensions import db
from app.models import (Consultant, Project, ProjectAssignment, MonthlyTimesheet, DailyTimesheetEntry,
                       ActivityType, InternalActivityType, AbsenceRequestType, ProjectActivityType, AstreinteLocation, AstreinteType, AbsenceRequestStatus, AbsenceRequestDay, AbsenceRequest, TimesheetStatus)

timesheet_bp = Blueprint('timesheet', __name__)

# Load timesheet data (period, status, number of declared days, reviewed by, reviewed at, manager comments) for a given consultant
@timesheet_bp.route('/api/consultant/<int:consultant_id>/timesheets', methods=['GET'])
def get_timesheets_per_consultant(consultant_id):
    """Get timesheet data for a given consultant"""
    consultant = Consultant.query.get_or_404(consultant_id)
    result = []

    monthly_timesheets = consultant.monthly_timesheets

    for monthly_timesheet in monthly_timesheets:
        one_monthly_timesheet = {}

        # Basic info
        one_monthly_timesheet['monthly_timesheet_id'] = monthly_timesheet.id
        one_monthly_timesheet['period'] = {
            'year': monthly_timesheet.year,
            'month_name': calendar.month_name[monthly_timesheet.month]
        }
        one_monthly_timesheet['status'] = monthly_timesheet.status.value if monthly_timesheet.status else None
        one_monthly_timesheet['number_of_declared_days'] = len(set(entry.work_date for entry in monthly_timesheet.daily_entries))
        one_monthly_timesheet['reviewed_by'] = monthly_timesheet.reviewed_by
        one_monthly_timesheet['reviewed_at'] = monthly_timesheet.reviewed_at
        one_monthly_timesheet['manager_comments'] = monthly_timesheet.manager_comments

        # ---- Calculate repartition ----
        total_hours = 0.0
        absence_hours = 0.0

        for entry in monthly_timesheet.daily_entries:
            # Skip astreinte from total hours
            if (
                entry.activity_type == ActivityType.PROJECT and
                entry.mission_activity_type == ProjectActivityType.ASTREINTE
            ):
                continue

            # Count toward total hours
            total_hours += entry.number_of_hours or 0.0

            # Count absence hours
            if entry.activity_type == ActivityType.ABSENCE:
                absence_hours += entry.number_of_hours or 0.0

        # Compute repartition %
        repartition = (absence_hours / total_hours * 100) if total_hours > 0 else 0.0
        one_monthly_timesheet['repartition'] = round(100 - repartition, 1)  # e.g. 23.4

        result.append(one_monthly_timesheet)

    return jsonify(result)


@timesheet_bp.route('/api/timesheets', methods=['POST'])
def create_timesheet():
    """Create a new monthly timesheet with daily activity entries"""
    data = request.get_json()

    required_fields = ['consultant_id', 'work_dates', 'month', 'year']
    for field in required_fields:
        if not data or field not in data:
            return jsonify({'error': f'{field} is required'}), 400

    consultant_id = data['consultant_id']
    month = data['month']
    year = data['year']

    # Validate month and year
    if not (1 <= month <= 12):
        return jsonify({'error': 'month must be between 1 and 12'}), 400
    if year < 2000 or year > 2100:
        return jsonify({'error': 'year must be reasonable'}), 400

    # Check if a monthly timesheet already exists
    existing = MonthlyTimesheet.query.filter_by(consultant_id=consultant_id, month=month, year=year).first()
    if existing:
        return jsonify({'error': 'Timesheet for this month already exists for this consultant'}), 400

    # Validate work_dates
    work_dates = data.get('work_dates')
    if not isinstance(work_dates, dict):
        return jsonify({'error': 'work_dates must be an object'}), 400

    # Determine timesheet status
    try:
        status = TimesheetStatus(data.get('status', 'saved'))
    except ValueError:
        return jsonify({'error': 'Invalid status'}), 400

    # Create monthly timesheet
    monthly_timesheet = MonthlyTimesheet(
        consultant_id=consultant_id,
        month=month,
        year=year,
        description=data.get('description'),
        status=status
    )

    db.session.add(monthly_timesheet)
    db.session.flush()  # Get ID for foreign key

    # Iterate through each date in work_dates
    for date_str, activities in work_dates.items():
        try:
            work_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': f'Invalid date format for {date_str}. Use YYYY-MM-DD'}), 400

        if not isinstance(activities, list) or not activities:
            return jsonify({'error': f'Activities for {date_str} must be a non-empty list'}), 400

        total_hours_day = 0
        for activity in activities:
            # Basic validation
            if 'activity_type' not in activity or 'number_of_hours' not in activity:
                return jsonify({'error': f'Missing required fields for {date_str}'}), 400

            try:
                activity_type = ActivityType(activity['activity_type'])
            except ValueError:
                return jsonify({'error': f'Invalid activity_type for {date_str}'}), 400

            number_of_hours = activity['number_of_hours']
            if not isinstance(number_of_hours, (int, float)) or number_of_hours <= 0 or number_of_hours > 24:
                return jsonify({'error': f'Invalid number_of_hours for {date_str}'}), 400

            total_hours_day += number_of_hours
            # We must consider astreintes (so 24h max)
            if total_hours_day > 24:
                return jsonify({'error': f'Total hours exceed 24 for {date_str}'}), 400

            # Initialize optional fields
            mission_id = None
            mission_activity_type = None
            astreinte_location = None
            astreinte_type = None
            internal_activity_type = None
            absence_type = None
            absence_request_id = None

            # PROJECT activities validation
            if activity_type == ActivityType.PROJECT:
                if not activity.get('mission_id'):
                    return jsonify({'error': f'mission_id required for project activity on {date_str}'}), 400
                mission_id = activity['mission_id']
                assignment = ProjectAssignment.query.get(mission_id)
                if not assignment:
                    return jsonify({'error': f'Mission with id {mission_id} not found'}), 404
                if assignment.consultant_id != consultant_id:
                    return jsonify({'error': f'Consultant not assigned to mission {mission_id}'}), 400

                # Project activity type
                try:
                    mission_activity_type = ProjectActivityType(activity.get('mission_activity_type', 'Normale'))
                except ValueError:
                    return jsonify({'error': f'Invalid mission_activity_type for {date_str}'}), 400                

                if mission_activity_type == ProjectActivityType.ASTREINTE:
                    if not activity.get('astreinte_location'):
                        return jsonify({'error': f'astreinte_location is required for Astreinte on {date_str}'}), 400
                    if not activity.get('astreinte_type'):
                        return jsonify({'error': f'astreinte_type is required for Astreinte on {date_str}'}), 400

                    try:
                        astreinte_location = AstreinteLocation(activity['astreinte_location'])
                    except ValueError:
                        return jsonify({'error': f'Invalid astreinte_location for {date_str}. Must be one of {[l.value for l in AstreinteLocation]}'}), 400

                    try:
                        astreinte_type = AstreinteType(activity['astreinte_type'])
                    except ValueError:
                        return jsonify({'error': f'Invalid astreinte_type for {date_str}. Must be one of {[t.value for t in AstreinteType]}'}), 400

            # INTERNAL activities validation
            elif activity_type == ActivityType.INTERNAL:
                if not activity.get('internal_activity_type'):
                    return jsonify({'error': f'internal_activity_type required for internal activity on {date_str}'}), 400
                try:
                    internal_activity_type = InternalActivityType(activity['internal_activity_type'])
                except ValueError:
                    return jsonify({'error': f'Invalid internal_activity_type for {date_str}'}), 400

            # ABSENCE activities validation
            elif activity_type == ActivityType.ABSENCE:
                # absence_type is required
                if not activity.get('absence_type'):
                    return jsonify({'error': f'absence_type required for absence activity on {date_str}'}), 400
                try:
                    absence_type = AbsenceRequestType(activity['absence_type'])
                except ValueError:
                    return jsonify({'error': f'Invalid absence_type for {date_str}'}), 400

                # absence_request_id is mandatory
                if not activity.get('absence_request_id'):
                    return jsonify({'error': f'absence_request_id required for absence activity on {date_str}'}), 400
                absence_request_id = activity['absence_request_id']

                absence_request = AbsenceRequest.query.get(absence_request_id)
                if not absence_request:
                    return jsonify({'error': f'Absence request with id {absence_request_id} not found'}), 404
                if absence_request.consultant_id != consultant_id:
                    return jsonify({'error': f'Absence request {absence_request_id} does not belong to consultant {consultant_id}'}), 400

                # mission_id is optional for absence
                if activity.get('mission_id'):
                    mission_id = activity['mission_id']
                    assignment = ProjectAssignment.query.get(mission_id)
                    if not assignment:
                        return jsonify({'error': f'Mission with id {mission_id} not found'}), 404
                    if assignment.consultant_id != consultant_id:
                        return jsonify({'error': f'Consultant not assigned to mission {mission_id}'}), 400

            # Create daily entry
            daily_entry = DailyTimesheetEntry(
                monthly_timesheet_id=monthly_timesheet.id,
                consultant_id=consultant_id,
                work_date=work_date,
                activity_type=activity_type,
                number_of_hours=number_of_hours,
                mission_id=mission_id,
                mission_activity_type=mission_activity_type,
                internal_activity_type=internal_activity_type,
                absence_type=absence_type,
                absence_request_id=absence_request_id,
                astreinte_location=astreinte_location,
                astreinte_type=astreinte_type,
                description=activity.get('description'),
                status=status
            )
            db.session.add(daily_entry)

    try:
        db.session.commit()
        return jsonify({'message': 'Timesheet created successfully', 'monthly_timesheet_id': monthly_timesheet.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@timesheet_bp.route('/api/timesheets/<int:timesheet_id>', methods=['GET'])
def get_monthly_timesheet_by_id(timesheet_id):
    """Retrieve full details of a monthly timesheet, grouped by mission, internal activity, and absences"""
    
    # Fetch monthly timesheet
    monthly_timesheet = MonthlyTimesheet.query.get(timesheet_id)
    if not monthly_timesheet:
        return jsonify({'error': f'Monthly timesheet with id {timesheet_id} not found'}), 404

    # Fetch all related daily entries
    daily_entries = DailyTimesheetEntry.query.filter_by(monthly_timesheet_id=timesheet_id).all()

    # Initialize response structure
    response = {
        "missions": {},
        "internal_activities": {},
        "Absences": {}
    }

    # Process each daily entry
    for entry in daily_entries:
        work_date = entry.work_date.isoformat()
        hours = entry.number_of_hours

        # 1️⃣ PROJECT ACTIVITIES (must have mission_id)
        if entry.activity_type == ActivityType.PROJECT:
            if not entry.mission_id:
                # Skip invalid project entries without mission_id
                continue

            mission_id = entry.mission_id

            # Ensure mission key exists
            if mission_id not in response["missions"]:
                response["missions"][mission_id] = {
                    "normal_activity": [],
                    "astreinte": [],
                    "absence": []
                }

            # Astreinte logic
            if entry.mission_activity_type == ProjectActivityType.ASTREINTE:
                response["missions"][mission_id]["astreinte"].append({
                    "work_date": work_date,
                    "number_of_hours": hours,
                    "astreinte_location": entry.astreinte_location.value if entry.astreinte_location else None,
                    "astreinte_type": entry.astreinte_type.value if entry.astreinte_type else None
                })

            # Normal project work
            else:
                response["missions"][mission_id]["normal_activity"].append({
                    "work_date": work_date,
                    "number_of_hours": hours
                })

        # 2️⃣ INTERNAL ACTIVITIES
        elif entry.activity_type == ActivityType.INTERNAL:
            if not entry.internal_activity_type:
                continue
            activity_type = entry.internal_activity_type.value
            if activity_type not in response["internal_activities"]:
                response["internal_activities"][activity_type] = []
            response["internal_activities"][activity_type].append({
                "work_date": work_date,
                "number_of_hours": hours
            })

        # 3️⃣ ABSENCES (can be mission-related or internal)
        elif entry.activity_type == ActivityType.ABSENCE:
            if not entry.absence_type:
                continue
            absence_type = entry.absence_type.value

            # Absence linked to a mission
            if entry.mission_id:
                mission_id = entry.mission_id
                if mission_id not in response["missions"]:
                    response["missions"][mission_id] = {
                        "normal_activity": [],
                        "astreinte": [],
                        "absence": []
                    }

                response["missions"][mission_id]["absence"].append({
                    "work_date": work_date,
                    "number_of_hours": hours,
                    "absence_type": absence_type,
                    "absence_request_id": entry.absence_request_id
                })

            # Internal absence (not linked to mission)
            else:
                if absence_type not in response["Absences"]:
                    response["Absences"][absence_type] = {
                        "absence_request_id": entry.absence_request_id,
                        "dates": []
                    }

                response["Absences"][absence_type]["dates"].append({
                    "work_date": work_date,
                    "number_of_hours": hours
                })

    return jsonify(response), 200

'''
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
    entries = DailyTimesheetEntry.query.filter(
        DailyTimesheetEntry.consultant_id == consultant_id,
        DailyTimesheetEntry.work_date >= first_day,
        DailyTimesheetEntry.work_date <= last_day
    ).order_by(DailyTimesheetEntry.work_date).all()
    
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
                'projectActivityType': entry.project_activity_type.value
            })
            total_project_time += entry.time_fraction
        elif entry.activity_type == ActivityType.INTERNAL:
            activity_data['internal_activity_type'] = entry.internal_activity_type.value
            total_internal_time += entry.time_fraction
        elif entry.activity_type == ActivityType.ABSENCE:
            activity_data['absence_type'] = entry.absence_type.value
            if entry.absence_request_id:
                activity_data['absence_request_id'] = entry.absence_request_id
            total_absence_time += entry.time_fraction
        
        daily_entries[date_str]['activities'].append(activity_data)
        daily_entries[date_str]['total_time'] += entry.time_fraction
    
    return jsonify({
        'consultant': {
            'id': consultant.id,
            'name': consultant.name,
            'email': consultant.email
        },
        'status': (entries[0].status if entries else ''),
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

'''
'''
@timesheet_bp.route('/api/consultants/<int:consultant_id>/timesheet/<int:year>/<int:month>/summary', methods=['GET'])
def get_monthly_summary(consultant_id, year, month):
    """Get monthly summary grouped by projects and activity types"""
    consultant = Consultant.query.get_or_404(consultant_id)
    
    # Get first and last day of month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    
    entries = DailyTimesheetEntry.query.filter(
        DailyTimesheetEntry.consultant_id == consultant_id,
        DailyTimesheetEntry.work_date >= first_day,
        DailyTimesheetEntry.work_date <= last_day
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
                    'normale_time': 0,
                    'astreinte_semaine_time': 0,
                    'astreinte_samedi_time': 0,
                    'astreinte_dimanche_time': 0,
                    'astreinte_jours_feries_time': 0,
                    'days_worked': set()
                }
            
            projects_summary[project_id]['total_time'] += entry.time_fraction
            projects_summary[project_id]['days_worked'].add(entry.work_date)
            
            if entry.project_activity_type == ProjectActivityType.NORMALE:
                projects_summary[project_id]['normale_time'] += entry.time_fraction
            elif entry.project_activity_type == ProjectActivityType.ASTREINTE_CALENDAIRE_SEMAINE:
                projects_summary[project_id]['astreinte_semaine_time'] += entry.time_fraction
            elif entry.project_activity_type == ProjectActivityType.ASTREINTE_CALENDAIRE_SAMEDI:
                projects_summary[project_id]['astreinte_samedi_time'] += entry.time_fraction
            elif entry.project_activity_type == ProjectActivityType.ASTREINTE_CALENDAIRE_DIMANCHE:
                projects_summary[project_id]['astreinte_dimanche_time'] += entry.time_fraction
            elif entry.project_activity_type == ProjectActivityType.ASTREINTE_CALENDAIRE_JOURS_FERIES:
                projects_summary[project_id]['astreinte_jours_feries_time'] += entry.time_fraction
        
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
'''

@timesheet_bp.route('/api/timesheets/monthly', methods=['GET'])
def get_monthly_timesheets():
    """Get all consultants' timesheets for a specific month/year (for HR portal)"""
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    
    # Validate required parameters
    if not month or not year:
        return jsonify({'error': 'Both month and year parameters are required'}), 400
    
    # Validate month range
    if month < 1 or month > 12:
        return jsonify({'error': 'Month must be between 1 and 12'}), 400
    
    # Validate year range (reasonable bounds)
    if year < 2000 or year > 2100:
        return jsonify({'error': 'Year must be between 2000 and 2100'}), 400
    
    # Query timesheets for the specified month/year, excluding 'saved' status
    timesheets = MonthlyTimesheet.query.filter(
        MonthlyTimesheet.month == month,
        MonthlyTimesheet.year == year,
        MonthlyTimesheet.status != TimesheetStatus.SAVED
    ).all()
    
    return jsonify([{
        'id': timesheet.id,
        'timesheet_reference': timesheet.timesheet_reference,
        'consultant_id': timesheet.consultant_id,
        'consultant_name': timesheet.consultant.name,
        'consultant_email': timesheet.consultant.email,
        'month': timesheet.month,
        'year': timesheet.year,
        'description': timesheet.description,
        'status': timesheet.status.value,
        'created_at': timesheet.created_at.isoformat(),
        'updated_at': timesheet.updated_at.isoformat(),
        'reviewed_at': timesheet.reviewed_at.isoformat() if timesheet.reviewed_at else None,
        'reviewed_by': timesheet.reviewed_by,
        'manager_comments': timesheet.manager_comments
    } for timesheet in timesheets]), 200


@timesheet_bp.route('/api/timesheets/<int:monthly_timesheet_id>', methods=['DELETE'])
def delete_timesheet(monthly_timesheet_id):
    """Delete a monthly timesheet and all its related daily entries"""
    try:
        # Find the monthly timesheet
        monthly_timesheet = MonthlyTimesheet.query.get(monthly_timesheet_id)
        if not monthly_timesheet:
            return jsonify({'error': f'Monthly timesheet with id {monthly_timesheet_id} not found'}), 404

        # Deletion automatically cascades to DailyTimesheetEntry because of:
        # daily_entries = db.relationship(..., cascade='all, delete-orphan')
        db.session.delete(monthly_timesheet)
        db.session.commit()

        return jsonify({
            'message': 'Monthly timesheet and related daily entries deleted successfully',
            'monthly_timesheet_id': monthly_timesheet_id
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@timesheet_bp.route('/api/timesheets/status', methods=['PUT'])
def update_timesheet_status():
    """Update the status of a monthly timesheet and all related daily entries"""
    data = request.get_json()

    # Validate required fields
    if not data or 'monthly_timesheet_id' not in data or 'status' not in data:
        return jsonify({'error': 'monthly_timesheet_id and status are required'}), 400

    monthly_timesheet_id = data['monthly_timesheet_id']
    new_status_str = data['status']

    # Validate new status
    try:
        new_status = TimesheetStatus(new_status_str)
    except ValueError:
        return jsonify({'error': f'Invalid status "{new_status_str}". Must be one of: {[s.value for s in TimesheetStatus]}'}), 400

    # Check if the monthly timesheet exists
    monthly_timesheet = MonthlyTimesheet.query.get(monthly_timesheet_id)
    if not monthly_timesheet:
        return jsonify({'error': f'Monthly timesheet with id {monthly_timesheet_id} not found'}), 404

    try:
        # Update monthly timesheet status
        monthly_timesheet.status = new_status
        monthly_timesheet.updated_at = datetime.utcnow()

        # Update all related daily entries
        DailyTimesheetEntry.query.filter_by(monthly_timesheet_id=monthly_timesheet_id).update({
            'status': new_status,
            'updated_at': datetime.utcnow()
        })

        db.session.commit()

        return jsonify({
            'message': 'Timesheet status updated successfully',
            'monthly_timesheet_id': monthly_timesheet_id,
            'new_status': new_status.value
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
