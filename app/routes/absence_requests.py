from flask import Blueprint, request, jsonify
from datetime import datetime, date
from app.extensions import db
from app.models import (Consultant, AbsenceRequest, AbsenceRequestDay, TimesheetEntry,
                       AbsenceRequestType, AbsenceRequestStatus, ActivityType)

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
        
        if existing_days + total_days_requested > 25:
            return jsonify({
                'error': f'Annual absence limit exceeded. Current: {existing_days} days, requesting: {total_days_requested} days. Maximum: 25 days per year (excluding Congés Sans Solde)'
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
            'created_at': absence_request.created_at.isoformat()
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
    conges_sans_solde_days = 0
    
    by_type = {}
    
    for request in absence_requests:
        for day in request.absence_days:
            if day.absence_date.year == year:
                # Count by status
                if day.status == AbsenceRequestStatus.ACCEPTED:
                    accepted_days += day.time_fraction
                elif day.status == AbsenceRequestStatus.PENDING:
                    pending_days += day.time_fraction
                elif day.status == AbsenceRequestStatus.REFUSED:
                    refused_days += day.time_fraction
                
                # Count Congés Sans Solde separately
                if request.absence_type == AbsenceRequestType.CONGES_SANS_SOLDE:
                    if day.status in [AbsenceRequestStatus.ACCEPTED, AbsenceRequestStatus.PENDING]:
                        conges_sans_solde_days += day.time_fraction
                
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
    used_days = accepted_days + pending_days - conges_sans_solde_days
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
    
    absences = []
    for day, request in absence_days:
        absences.append({
            'id': day.id,
            'request_reference': request.request_reference,
            'absence_date': day.absence_date.isoformat(),
            'absence_type': request.absence_type.value,
            'time_fraction': day.time_fraction,
            'status': day.status.value,
            'commentary': request.commentary,
            'justification': request.justification
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
        'absences': absences
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

@absence_requests_bp.route('/api/absence-requests/<int:request_id>/review', methods=['PUT'])
def review_absence_request(request_id):
    """HR team review absence request (accept/refuse individual days)"""
    data = request.get_json()
    
    required_fields = ['reviewed_by', 'day_decisions']
    for field in required_fields:
        if not data or field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    absence_request = AbsenceRequest.query.get_or_404(request_id)
    
    if absence_request.status != AbsenceRequestStatus.PENDING:
        return jsonify({'error': 'Only pending requests can be reviewed'}), 400
    
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