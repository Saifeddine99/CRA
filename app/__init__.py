from flask import Flask, jsonify
from config import config
from app.extensions import db, cors

def create_app(config_name='default'):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # Initialize extensions
    db.init_app(app)
    cors.init_app(app)  # Allow all domains for all routes
    
    # Import models to ensure they're registered with SQLAlchemy
    from app.models import (
        Consultant, Project, ProjectAssignment, TimesheetEntry,
        ActivityType, InternalActivityType, AbsenceType, WorkLocation
    )
    
    # Register blueprints
    from app.routes import (
        consultants_bp, projects_bp, project_assignments_bp,
        timesheet_bp, utils_bp
    )
    
    app.register_blueprint(consultants_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(project_assignments_bp)
    app.register_blueprint(timesheet_bp)
    app.register_blueprint(utils_bp)
    
    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Resource not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app