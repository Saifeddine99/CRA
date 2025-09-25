from .consultants import consultants_bp
from .projects import projects_bp
from .project_assignments import project_assignments_bp
from .timesheet import timesheet_bp
from .utils import utils_bp

__all__ = [
    'consultants_bp', 'projects_bp', 'project_assignments_bp', 
    'timesheet_bp', 'utils_bp'
]