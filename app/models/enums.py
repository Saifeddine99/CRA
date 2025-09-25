from enum import Enum

class ActivityType(Enum):
    PROJECT = "project"
    INTERNAL = "internal"
    ABSENCE = "absence"

class InternalActivityType(Enum):
    OFFICE = "office"
    INTER_CONTRACT = "inter_contract"
    INTERNAL_PROJECT = "internal_project"
    TRAINING = "training"

class AbsenceType(Enum):
    SICK_LEAVE = "sick_leave"
    VACATION = "vacation"
    PERSONAL_LEAVE = "personal_leave"
    PUBLIC_HOLIDAY = "public_holiday"
    UNPAID_LEAVE = "unpaid_leave"

class WorkLocation(Enum):
    REMOTE = "remote"
    ON_SITE = "on_site"
    HYBRID = "hybrid"