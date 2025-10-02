from flask import Blueprint, request, jsonify
from datetime import datetime, date
import calendar  # noqa: F401
from app.extensions import db
from app.models import (Consultant, AbsenceRequest, AbsenceRequestDay,
                       AbsenceRequestType, AbsenceRequestStatus, TimesheetEntry, ActivityType)  # noqa: F401

absence_requests_bp = Blueprint('absence_requests', __name__)

@absence_requests_bp.route('/api/absence-requests', methods=['POST'])
def create_absence_request():
    """Create a new absence request with multiple days"""
    data = request.get_json()
    
    required_fields = ['consultant_id', 'absence_type', 'days']
    for field in required_fields:
        if not data or field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    # Validate consultant exists
    consultant = Consultant.query.get_or_404(data['consultant_id'])
    
    # Validate absence type
    try:
        absence_type = AbsenceRequestType(data['absence_type'])
    except ValueError:
        return jsonify({'error': 'Invalid absence type'}), 400
    
    # Validate days data
    if not data['days'] or not isinstance(data['days'], list):
        return jsonify({'error': 'days must be a non-empty list'}), 400
    
    # Parse and validate each day
    parsed_days = []
    for day_data in data['days']:
        if not isinstance(day_data, dict) or 'date' not in day_data or 'time_fraction' not in day_data:
            return jsonify({'error': 'Each day must have date and time_fraction'}), 400
        
        try:
            absence_date = datetime.strptime(day_data['date'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        time_fraction = day_data['time_fraction']
        if time_fraction not in [0.5, 1.0]:
            return jsonify({'error': 'time_fraction must be 0.5 or 1.0'}), 400
        
        parsed_days.append({
            'date': absence_date,
            'time_fraction': time_fraction
        })
    
    # Check for conflicts with existing absence requests
    existing_conflicts = []
    for day in parsed_days:
        # Check for existing absence requests on the same day
        existing_absence = db.session.query(AbsenceRequestDay).join(AbsenceRequest).filter(
            AbsenceRequest.consultant_id == data['consultant_id'],
            AbsenceRequestDay.absence_date == day['date'],
            AbsenceRequestDay.status.in_([AbsenceRequestStatus.PENDING, AbsenceRequestStatus.ACCEPTED])
        ).first()
        
        if existing_absence:
            existing_conflicts.append(day['date'].isoformat())
    
    if existing_conflicts:
        return jsonify({
            'error': f'Consultant already has absence requests for these dates: {", ".join(existing_conflicts)}'
        }), 400
    
    # Check annual limit (excluding Congés Sans Solde)
    if absence_type != AbsenceRequestType.CONGES_SANS_SOLDE:
        current_year = datetime.now().year
        total_days_requested = sum(day['time_fraction'] for day in parsed_days)
        
        # Get existing accepted/pending days for the year
        existing_days = db.session.query(db.func.sum(AbsenceRequestDay.time_fraction)).join(AbsenceRequest).filter(
            AbsenceRequest.consultant_id == data['consultant_id'],
            AbsenceRequest.absence_type != AbsenceRequestType.CONGES_SANS_SOLDE,
            AbsenceRequestDay.status.in_([AbsenceRequestStatus.ACCEPTED, AbsenceRequestStatus.PENDING]),
            db.func.strftime('%Y', AbsenceRequestDay.absence_date) == str(current_year)
        ).scalar() or 0
        
        total_remaining_days = max(0, 25 - existing_days)
        
        if existing_days + total_days_requested > 25:
            return jsonify({
                'error': f'Annual absence limit exceeded. Remaining days available: {total_remaining_days}. You are requesting: {total_days_requested} days'
            }), 400
    
    # Create the absence request
    absence_request = AbsenceRequest(
        consultant_id=data['consultant_id'],
        absence_type=absence_type,
        commentary=data.get('commentary'),
        justification=data.get('justification')
    )
    
    try:
        db.session.add(absence_request)
        db.session.flush()  # Get the ID
        
        # Create absence days
        for day in parsed_days:
            absence_day = AbsenceRequestDay(
                absence_request_id=absence_request.id,
                absence_date=day['date'],
                time_fraction=day['time_fraction']
            )
            db.session.add(absence_day)
        
        db.session.commit()
        
        # Process timesheet updates for each absence day
        affected_months = set()
        
        for day in parsed_days:
            absence_date = day['date']
            absence_time_fraction = day['time_fraction']
            
            # Get first and last day of the month containing this absence date
            first_day = date(absence_date.year, absence_date.month, 1)
            last_day = date(absence_date.year, absence_date.month, calendar.monthrange(absence_date.year, absence_date.month)[1])
            
            # Check if timesheet is submitted for this month
            submitted_entries = TimesheetEntry.query.filter(
                TimesheetEntry.consultant_id == data['consultant_id'],
                TimesheetEntry.work_date >= first_day,
                TimesheetEntry.work_date <= last_day
            ).first()
            
            if submitted_entries:
                # Timesheet is submitted, need to update it
                affected_months.add((absence_date.year, absence_date.month))
                
                # Get all timesheet entries for this specific date
                daily_entries = TimesheetEntry.query.filter(
                    TimesheetEntry.consultant_id == data['consultant_id'],
                    TimesheetEntry.work_date == absence_date,
                    TimesheetEntry.activity_type != ActivityType.ABSENCE
                ).order_by(TimesheetEntry.id).all()
                
                if daily_entries:
                    if absence_time_fraction == 1.0:
                        # Full day absence - remove all activities and replace with absence
                        for entry in daily_entries:
                            db.session.delete(entry)
                        
                        # Create new absence entry
                        absence_entry = TimesheetEntry(
                            consultant_id=data['consultant_id'],
                            work_date=absence_date,
                            activity_type=ActivityType.ABSENCE,
                            time_fraction=1.0,
                            absence_type=absence_type,
                            absence_request_id=absence_request.id,
                            description=f"Absence: {absence_type.value}",
                            status='pending'
                        )
                        db.session.add(absence_entry)
                        
                    elif absence_time_fraction == 0.5:
                        # Half day absence
                        total_existing_time = sum(entry.time_fraction for entry in daily_entries)
                        
                        if total_existing_time == 1.0:
                            # User has full day activities, need to adjust
                            if len(daily_entries) == 1:
                                # Single activity of 1.0, convert to 0.5
                                daily_entries[0].time_fraction = 0.5
                            else:
                                # Multiple activities, remove the last one and adjust if needed
                                last_entry = daily_entries[-1]
                                db.session.delete(last_entry)
                                
                                # Check if remaining activities sum to 0.5
                                remaining_time = sum(entry.time_fraction for entry in daily_entries[:-1])
                                if remaining_time > 0.5:
                                    # Adjust the first entry to make room for absence
                                    daily_entries[0].time_fraction = 0.5
                                    # Remove other entries if necessary
                                    for entry in daily_entries[1:-1]:
                                        db.session.delete(entry)
                        
                        elif total_existing_time == 0.5:
                            # Already half day, keep as is
                            pass
                        else:
                            # Other cases, adjust first entry to 0.5 and remove others
                            if daily_entries:
                                daily_entries[0].time_fraction = 0.5
                                for entry in daily_entries[1:]:
                                    db.session.delete(entry)
                        
                        # Create absence entry
                        absence_entry = TimesheetEntry(
                            consultant_id=data['consultant_id'],
                            work_date=absence_date,
                            activity_type=ActivityType.ABSENCE,
                            time_fraction=0.5,
                            absence_type=absence_type,
                            absence_request_id=absence_request.id,
                            description=f"Absence: {absence_type.value}",
                            status='pending'
                        )
                        db.session.add(absence_entry)
                else:
                    # Day is empty but timesheet exists for the month
                    # Create the absence entry directly
                    absence_entry = TimesheetEntry(
                        consultant_id=absence_request.consultant_id,
                        work_date=absence_date,
                        activity_type=ActivityType.ABSENCE,
                        time_fraction=absence_time_fraction,
                        absence_type=absence_type,
                        absence_request_id=absence_request.id,
                        description=f"Absence: {absence_type.value}",
                        status='pending'
                    )
                    db.session.add(absence_entry)
                    
        # Update status of all records in affected months to 'pending'
        for year, month in affected_months:
            first_day = date(year, month, 1)
            last_day = date(year, month, calendar.monthrange(year, month)[1])
            
            month_entries = TimesheetEntry.query.filter(
                TimesheetEntry.consultant_id == data['consultant_id'],
                TimesheetEntry.work_date >= first_day,
                TimesheetEntry.work_date <= last_day
            ).all()
            
            for entry in month_entries:
                entry.status = 'pending'
        
        db.session.commit()
        
        return jsonify({
            'id': absence_request.id,
            'request_reference': absence_request.request_reference,
            'absence_type': absence_request.absence_type.value,
            'status': absence_request.status.value,
            'commentary': absence_request.commentary,
            'justification': absence_request.justification,
            'total_days': sum(day['time_fraction'] for day in parsed_days),
            'days': [{
                'date': day['date'].isoformat(),
                'time_fraction': day['time_fraction']
            } for day in parsed_days],
            'created_at': absence_request.created_at.isoformat(),
            'affected_months': len(affected_months)
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create absence request'}), 500

@absence_requests_bp.route('/api/consultants/<int:consultant_id>/absence-summary/<int:year>', methods=['GET'])
def get_absence_summary(consultant_id, year):
    """Get consultant's absence summary for a specific year"""
    consultant = Consultant.query.get_or_404(consultant_id)
    
    if year < 2020 or year > 2030:
        return jsonify({'error': 'Invalid year'}), 400
    
    # Get all absence requests for the year
    absence_requests = db.session.query(AbsenceRequest).filter(
        AbsenceRequest.consultant_id == consultant_id,
        db.exists().where(
            db.and_(
                AbsenceRequestDay.absence_request_id == AbsenceRequest.id,
                db.func.strftime('%Y', AbsenceRequestDay.absence_date) == str(year)
            )
        )
    ).all()
    
    # Calculate totals by status and type
    accepted_days = 0
    pending_days = 0
    refused_days = 0
    
    by_type = {}
    
    for request in absence_requests:
        for day in request.absence_days:
            if day.absence_date.year == year:
                # Count by status (excluding Congés Sans Solde)
                if request.absence_type != AbsenceRequestType.CONGES_SANS_SOLDE:
                    if day.status == AbsenceRequestStatus.ACCEPTED:
                        accepted_days += day.time_fraction
                    elif day.status == AbsenceRequestStatus.PENDING:
                        pending_days += day.time_fraction
                    elif day.status == AbsenceRequestStatus.REFUSED:
                        refused_days += day.time_fraction
                
                # Count by type
                type_key = request.absence_type.value
                if type_key not in by_type:
                    by_type[type_key] = {'accepted': 0, 'pending': 0, 'refused': 0}
                
                if day.status == AbsenceRequestStatus.ACCEPTED:
                    by_type[type_key]['accepted'] += day.time_fraction
                elif day.status == AbsenceRequestStatus.PENDING:
                    by_type[type_key]['pending'] += day.time_fraction
                elif day.status == AbsenceRequestStatus.REFUSED:
                    by_type[type_key]['refused'] += day.time_fraction
    
    # Calculate remaining days (excluding Congés Sans Solde)
    used_days = accepted_days + pending_days
    remaining_days = max(0, 25 - used_days)
    
    return jsonify({
        'consultant': {
            'id': consultant.id,
            'name': consultant.name,
            'email': consultant.email
        },
        'year': year,
        'summary': {
            'accepted_days': accepted_days,
            'pending_days': pending_days,
            'refused_days': refused_days,
            'total_used_days': used_days,  # Excluding Congés Sans Solde
            'remaining_days': remaining_days,
            'annual_limit': 25
        },
        'by_type': by_type
    })

@absence_requests_bp.route('/api/consultants/<int:consultant_id>/absence-requests/<int:year>/<int:month>', methods=['GET'])
def get_monthly_absences(consultant_id, year, month):
    """Get accepted and pending absences for timesheet display"""
    consultant = Consultant.query.get_or_404(consultant_id)
    
    if not (1 <= month <= 12) or year < 2020 or year > 2030:
        return jsonify({'error': 'Invalid month or year'}), 400
    
    # Get first and last day of month
    first_day = date(year, month, 1)
    from calendar import monthrange
    last_day = date(year, month, monthrange(year, month)[1])
    
    # Query absence days for the month
    absence_days = db.session.query(AbsenceRequestDay, AbsenceRequest).join(AbsenceRequest).filter(
        AbsenceRequest.consultant_id == consultant_id,
        AbsenceRequestDay.absence_date >= first_day,
        AbsenceRequestDay.absence_date <= last_day,
        AbsenceRequestDay.status.in_([AbsenceRequestStatus.ACCEPTED, AbsenceRequestStatus.PENDING])
    ).order_by(AbsenceRequestDay.absence_date).all()
    
    # Group by absence type
    absences_by_type = {}
    for day, request in absence_days:
        absence_type = request.absence_type.value
        
        if absence_type not in absences_by_type:
            absences_by_type[absence_type] = []
        
        absences_by_type[absence_type].append({
            'work_date': day.absence_date.isoformat(),
            'status': day.status.value,
            'time_fraction': day.time_fraction,
            'absence_request_id': request.id
        })
    
    return jsonify({
        'consultant': {
            'id': consultant.id,
            'name': consultant.name,
            'email': consultant.email
        },
        'period': {
            'year': year,
            'month': month
        },
        'absences': absences_by_type
    })

@absence_requests_bp.route('/api/absence-requests/<int:request_id>', methods=['GET'])
def get_absence_request(request_id):
    """Get detailed absence request"""
    absence_request = AbsenceRequest.query.get_or_404(request_id)
    
    return jsonify({
        'id': absence_request.id,
        'request_reference': absence_request.request_reference,
        'consultant': {
            'id': absence_request.consultant.id,
            'name': absence_request.consultant.name,
            'email': absence_request.consultant.email
        },
        'absence_type': absence_request.absence_type.value,
        'commentary': absence_request.commentary,
        'justification': absence_request.justification,
        'status': absence_request.status.value,
        'created_at': absence_request.created_at.isoformat(),
        'reviewed_at': absence_request.reviewed_at.isoformat() if absence_request.reviewed_at else None,
        'reviewed_by': absence_request.reviewed_by,
        'hr_comments': absence_request.hr_comments,
        'days': [{
            'id': day.id,
            'absence_date': day.absence_date.isoformat(),
            'time_fraction': day.time_fraction,
            'status': day.status.value
        } for day in absence_request.absence_days]
    })

@absence_requests_bp.route('/api/absence-requests', methods=['GET'])
def get_all_absence_requests():
    """Get all absence requests (for HR team)"""
    status_filter = request.args.get('status')
    consultant_id = request.args.get('consultant_id')
    
    query = AbsenceRequest.query
    
    if status_filter:
        try:
            status_enum = AbsenceRequestStatus(status_filter)
            query = query.filter(AbsenceRequest.status == status_enum)
        except ValueError:
            return jsonify({'error': 'Invalid status'}), 400
    
    if consultant_id:
        query = query.filter(AbsenceRequest.consultant_id == consultant_id)
    
    requests = query.order_by(AbsenceRequest.created_at.desc()).all()
    
    result = []
    for req in requests:
        total_days = sum(day.time_fraction for day in req.absence_days)
        result.append({
            'id': req.id,
            'request_reference': req.request_reference,
            'consultant': {
                'id': req.consultant.id,
                'name': req.consultant.name,
                'email': req.consultant.email
            },
            'absence_type': req.absence_type.value,
            'total_days': total_days,
            'status': req.status.value,
            'created_at': req.created_at.isoformat(),
            'reviewed_at': req.reviewed_at.isoformat() if req.reviewed_at else None,
            'reviewed_by': req.reviewed_by
        })
    
    return jsonify(result)

@absence_requests_bp.route('/api/consultants/<int:consultant_id>/absence-requests/<int:year>', methods=['GET'])
def get_consultant_absence_requests(consultant_id, year):
    """Get all absence requests for a specific consultant and year"""
    consultant = Consultant.query.get_or_404(consultant_id)
    
    if year < 2020 or year > 2030:
        return jsonify({'error': 'Invalid year'}), 400
    
    # Get all absence requests for the consultant that have days in the specified year
    absence_requests = db.session.query(AbsenceRequest).filter(
        AbsenceRequest.consultant_id == consultant_id,
        db.exists().where(
            db.and_(
                AbsenceRequestDay.absence_request_id == AbsenceRequest.id,
                db.func.strftime('%Y', AbsenceRequestDay.absence_date) == str(year)
            )
        )
    ).order_by(AbsenceRequest.created_at.desc()).all()
    
    result = []
    for request in absence_requests:
        # Calculate total days for this request in the specified year
        total_days = sum(
            day.time_fraction for day in request.absence_days 
            if day.absence_date.year == year
        )
        
        result.append({
            'absence_type': request.absence_type.value,
            'created_at': request.created_at.date().isoformat(),
            'request_id': request.id,
            'status': request.status.value,
            'total_days': total_days
        })
    
    return jsonify(result)

@absence_requests_bp.route('/api/absence-requests/<int:request_id>', methods=['PUT'])
def update_absence_request(request_id):
    """Update an absence request (pending or refused). After update, status becomes pending."""
    data = request.get_json()

    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    # Fetch request
    absence_request = AbsenceRequest.query.get_or_404(request_id)

    # Only pending, refused, or accepted requests can be updated
    if absence_request.status not in [AbsenceRequestStatus.PENDING, AbsenceRequestStatus.REFUSED, AbsenceRequestStatus.ACCEPTED]:
        return jsonify({'error': 'Only pending, refused, or accepted requests can be updated'}), 400

    # Optional fields
    new_commentary = data.get('commentary', absence_request.commentary)
    new_justification = data.get('justification', absence_request.justification)

    # Absence type can be updated; default to current if not provided
    absence_type_value = data.get('absence_type', absence_request.absence_type.value)
    try:
        new_absence_type = AbsenceRequestType(absence_type_value)
    except ValueError:
        return jsonify({'error': 'Invalid absence type'}), 400

    # Days can be updated by providing full replacement list under `days`
    days_payload = data.get('days')
    parsed_days = None
    if days_payload is not None:
        if not isinstance(days_payload, list) or len(days_payload) == 0:
            return jsonify({'error': 'days must be a non-empty list'}), 400
        # Parse
        parsed_days = []
        for day_data in days_payload:
            if not isinstance(day_data, dict) or 'date' not in day_data or 'time_fraction' not in day_data:
                return jsonify({'error': 'Each day must have date and time_fraction'}), 400
            try:
                absence_date = datetime.strptime(day_data['date'], '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
            time_fraction = day_data['time_fraction']
            if time_fraction not in [0.5, 1.0]:
                return jsonify({'error': 'time_fraction must be 0.5 or 1.0'}), 400
            parsed_days.append({'date': absence_date, 'time_fraction': time_fraction})

        # Validate conflicts against other requests for the same consultant
        existing_conflicts = []
        for day in parsed_days:
            conflict = db.session.query(AbsenceRequestDay).join(AbsenceRequest).filter(
                AbsenceRequest.consultant_id == absence_request.consultant_id,
                AbsenceRequestDay.absence_date == day['date'],
                AbsenceRequestDay.status.in_([AbsenceRequestStatus.PENDING, AbsenceRequestStatus.ACCEPTED]),
                AbsenceRequestDay.absence_request_id != absence_request.id
            ).first()
            if conflict:
                existing_conflicts.append(day['date'].isoformat())
        if existing_conflicts:
            return jsonify({'error': f'Consultant already has absence requests for these dates: {", ".join(existing_conflicts)}'}), 400

        # Validate annual limit (excluding Congés Sans Solde)
        if new_absence_type != AbsenceRequestType.CONGES_SANS_SOLDE:
            current_year = datetime.now().year
            total_days_requested = sum(day['time_fraction'] for day in parsed_days)
            existing_days = db.session.query(db.func.sum(AbsenceRequestDay.time_fraction)).join(AbsenceRequest).filter(
                AbsenceRequest.consultant_id == absence_request.consultant_id,
                AbsenceRequest.absence_type != AbsenceRequestType.CONGES_SANS_SOLDE,
                AbsenceRequestDay.status.in_([AbsenceRequestStatus.ACCEPTED, AbsenceRequestStatus.PENDING]),
                db.func.strftime('%Y', AbsenceRequestDay.absence_date) == str(current_year),
                AbsenceRequestDay.absence_request_id != absence_request.id
            ).scalar() or 0
            if existing_days + total_days_requested > 25:
                remaining_days = max(0, 25 - existing_days)
                return jsonify({'error': f'Annual absence limit exceeded. Remaining days available: {remaining_days}. You are requesting: {total_days_requested} days'}), 400

    try:
        # Apply simple field updates
        absence_request.absence_type = new_absence_type
        absence_request.commentary = new_commentary
        absence_request.justification = new_justification

        # If days provided, replace existing days for this request
        if parsed_days is not None:
            # Delete existing days
            AbsenceRequestDay.query.filter_by(absence_request_id=absence_request.id).delete()
            # Delete related timesheet entries
            TimesheetEntry.query.filter_by(absence_request_id=absence_request.id).delete()
            # Insert new days
            for day in parsed_days:
                db.session.add(AbsenceRequestDay(
                    absence_request_id=absence_request.id,
                    absence_date=day['date'],
                    time_fraction=day['time_fraction']
                ))
            
            # Process timesheet updates for each new absence day
            affected_months = set()
            
            for day in parsed_days:
                absence_date = day['date']
                absence_time_fraction = day['time_fraction']
                
                # Get first and last day of the month containing this absence date
                first_day = date(absence_date.year, absence_date.month, 1)
                last_day = date(absence_date.year, absence_date.month, calendar.monthrange(absence_date.year, absence_date.month)[1])
                
                # Check if timesheet is submitted for this month
                submitted_entries = TimesheetEntry.query.filter(
                    TimesheetEntry.consultant_id == absence_request.consultant_id,
                    TimesheetEntry.work_date >= first_day,
                    TimesheetEntry.work_date <= last_day
                ).first()
                
                if submitted_entries:
                    # Timesheet is submitted, need to update it
                    affected_months.add((absence_date.year, absence_date.month))
                    
                    # Get all timesheet entries for this specific date
                    daily_entries = TimesheetEntry.query.filter(
                        TimesheetEntry.consultant_id == absence_request.consultant_id,
                        TimesheetEntry.work_date == absence_date,
                        TimesheetEntry.activity_type != ActivityType.ABSENCE
                    ).order_by(TimesheetEntry.id).all()
                    
                    if daily_entries:
                        if absence_time_fraction == 1.0:
                            # Full day absence - remove all activities and replace with absence
                            for entry in daily_entries:
                                db.session.delete(entry)
                            
                            # Create new absence entry
                            absence_entry = TimesheetEntry(
                                consultant_id=absence_request.consultant_id,
                                work_date=absence_date,
                                activity_type=ActivityType.ABSENCE,
                                time_fraction=1.0,
                                absence_type=new_absence_type,
                                absence_request_id=absence_request.id,
                                description=f"Absence: {new_absence_type.value}",
                                status='pending'
                            )
                            db.session.add(absence_entry)
                            
                        elif absence_time_fraction == 0.5:
                            # Half day absence
                            total_existing_time = sum(entry.time_fraction for entry in daily_entries)
                            
                            if total_existing_time == 1.0:
                                # User has full day activities, need to adjust
                                if len(daily_entries) == 1:
                                    # Single activity of 1.0, convert to 0.5
                                    daily_entries[0].time_fraction = 0.5
                                else:
                                    # Multiple activities, remove the last one and adjust if needed
                                    last_entry = daily_entries[-1]
                                    db.session.delete(last_entry)
                                    
                                    # Check if remaining activities sum to 0.5
                                    remaining_time = sum(entry.time_fraction for entry in daily_entries[:-1])
                                    if remaining_time > 0.5:
                                        # Adjust the first entry to make room for absence
                                        daily_entries[0].time_fraction = 0.5
                                        # Remove other entries if necessary
                                        for entry in daily_entries[1:-1]:
                                            db.session.delete(entry)
                            
                            elif total_existing_time == 0.5:
                                # Already half day, keep as is
                                pass
                            else:
                                # Other cases, adjust first entry to 0.5 and remove others
                                if daily_entries:
                                    daily_entries[0].time_fraction = 0.5
                                    for entry in daily_entries[1:]:
                                        db.session.delete(entry)
                            
                            # Create absence entry
                            absence_entry = TimesheetEntry(
                                consultant_id=absence_request.consultant_id,
                                work_date=absence_date,
                                activity_type=ActivityType.ABSENCE,
                                time_fraction=0.5,
                                absence_type=new_absence_type,
                                absence_request_id=absence_request.id,
                                description=f"Absence: {new_absence_type.value}",
                                status='pending'
                            )
                            db.session.add(absence_entry)
                    else:
                        # Day is empty but timesheet exists for the month
                        # Create the absence entry directly
                        absence_entry = TimesheetEntry(
                            consultant_id=absence_request.consultant_id,
                            work_date=absence_date,
                            activity_type=ActivityType.ABSENCE,
                            time_fraction=absence_time_fraction,
                            absence_type=new_absence_type,
                            absence_request_id=absence_request.id,
                            description=f"Absence: {new_absence_type.value}",
                            status='pending'
                        )
                        db.session.add(absence_entry)

            # Update status of all records in affected months to 'pending'
            for year, month in affected_months:
                first_day = date(year, month, 1)
                last_day = date(year, month, calendar.monthrange(year, month)[1])
                
                month_entries = TimesheetEntry.query.filter(
                    TimesheetEntry.consultant_id == absence_request.consultant_id,
                    TimesheetEntry.work_date >= first_day,
                    TimesheetEntry.work_date <= last_day
                ).all()
                
                for entry in month_entries:
                    entry.status = 'pending'

        # After updates, set overall status from payload or default to pending
        new_status_value = data.get('status', AbsenceRequestStatus.PENDING.value)
        try:
            new_status = AbsenceRequestStatus(new_status_value)
        except ValueError:
            return jsonify({'error': "Invalid status. Allowed: 'pending', 'refused', or 'accepted'"}), 400
        if new_status not in [AbsenceRequestStatus.PENDING, AbsenceRequestStatus.REFUSED, AbsenceRequestStatus.ACCEPTED]:
            return jsonify({'error': "Status must be 'pending', 'refused', or 'accepted' for updates"}), 400
        absence_request.status = new_status

        db.session.commit()

        # Build response
        return jsonify({
            'id': absence_request.id,
            'request_reference': absence_request.request_reference,
            'absence_type': absence_request.absence_type.value,
            'status': absence_request.status.value,
            'commentary': absence_request.commentary,
            'justification': absence_request.justification,
            'days': [{
                'date': d.absence_date.isoformat(),
                'time_fraction': d.time_fraction
            } for d in absence_request.absence_days]
        })
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to update absence request'}), 500

@absence_requests_bp.route('/api/absence-requests/<int:request_id>/review', methods=['PUT'])
def review_absence_request(request_id):
    """HR team review absence request (accept/refuse individual days)"""
    data = request.get_json()
    
    required_fields = ['reviewed_by', 'day_decisions']
    for field in required_fields:
        if not data or field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    absence_request = AbsenceRequest.query.get_or_404(request_id)
    
    #if absence_request.status != AbsenceRequestStatus.PENDING:
        #return jsonify({'error': 'Only pending requests can be reviewed'}), 400
    
    # Validate day decisions
    day_decisions = data['day_decisions']
    if not isinstance(day_decisions, list):
        return jsonify({'error': 'day_decisions must be a list'}), 400
    
    try:
        # Process each day decision
        accepted_count = 0
        refused_count = 0
        
        for decision in day_decisions:
            if 'day_id' not in decision or 'status' not in decision:
                return jsonify({'error': 'Each decision must have day_id and status'}), 400
            
            day = AbsenceRequestDay.query.filter_by(
                id=decision['day_id'],
                absence_request_id=request_id
            ).first()
            
            if not day:
                return jsonify({'error': f'Day {decision["day_id"]} not found in this request'}), 400
            
            try:
                new_status = AbsenceRequestStatus(decision['status'])
            except ValueError:
                return jsonify({'error': 'Invalid status. Use accepted or refused'}), 400
            
            if new_status not in [AbsenceRequestStatus.ACCEPTED, AbsenceRequestStatus.REFUSED]:
                return jsonify({'error': 'Status must be accepted or refused'}), 400
            
            day.status = new_status
            
            if new_status == AbsenceRequestStatus.ACCEPTED:
                accepted_count += 1
            else:
                refused_count += 1
        
        # Update overall request status
        total_days = len(absence_request.absence_days)
        if accepted_count == total_days:
            absence_request.status = AbsenceRequestStatus.ACCEPTED
        elif refused_count == total_days:
            absence_request.status = AbsenceRequestStatus.REFUSED
        else:
            absence_request.status = AbsenceRequestStatus.PARTIALLY_ACCEPTED
        
        # Update review information
        absence_request.reviewed_at = datetime.utcnow()
        absence_request.reviewed_by = data['reviewed_by']
        absence_request.hr_comments = data.get('hr_comments')
        
        db.session.commit()
        
        return jsonify({
            'id': absence_request.id,
            'status': absence_request.status.value,
            'reviewed_at': absence_request.reviewed_at.isoformat(),
            'reviewed_by': absence_request.reviewed_by,
            'hr_comments': absence_request.hr_comments,
            'accepted_days': accepted_count,
            'refused_days': refused_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to review absence request'}), 500

@absence_requests_bp.route('/api/absence-requests/<int:request_id>', methods=['DELETE'])
def delete_absence_request(request_id):
    """Delete an absence request only if it's pending. Related timesheet entries and child days are removed via cascade delete-orphan."""
    absence_request = AbsenceRequest.query.get_or_404(request_id)

    if absence_request.status != AbsenceRequestStatus.PENDING:
        return jsonify({'error': 'Only pending requests can be deleted'}), 400

    try:
        # Extract all dates from the absence request to determine affected months
        affected_months = set()
        consultant_id = absence_request.consultant_id
        
        for absence_day in absence_request.absence_days:
            absence_date = absence_day.absence_date
            affected_months.add((absence_date.year, absence_date.month))

        
        # Delete the absence request (this will cascade delete related timesheet entries and absence days)
        db.session.delete(absence_request)

        # Update status of all remaining timesheet entries in affected months to 'pending'
        for year, month in affected_months:
            first_day = date(year, month, 1)
            last_day = date(year, month, calendar.monthrange(year, month)[1])
            
            month_entries = TimesheetEntry.query.filter(
                TimesheetEntry.consultant_id == consultant_id,
                TimesheetEntry.work_date >= first_day,
                TimesheetEntry.work_date <= last_day
            ).all()
            
            for entry in month_entries:
                entry.status = 'pending'
        
        db.session.commit()
        
        return jsonify({
            'message': 'Absence request deleted successfully',
            'id': request_id,
            'affected_months': len(affected_months)
        }), 200
        
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete absence request'}), 500