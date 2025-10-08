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

class ProjectActivityType(Enum):
    NORMALE = "Normale"
    ASTREINTE = "Astreinte"

class AstreinteLocation(Enum):
    REMOTE = "Remote"
    ONSITE = "On_site"

class AstreinteType(Enum):
    PASSIVE = "Passive"
    ACTIVE = "Active"

class AbsenceRequestType(Enum):
    CP = "CP"
    RTT = "RTT"
    CONGES_SANS_SOLDE = "Congés Sans Solde"
    MALADIE = "Maladie"
    EXCEPTIONNELLE = "Exceptionnelle"
    PATERNITE = "Paternité"
    MATERNITE = "Maternité"

class AbsenceRequestStatus(Enum):
    SAVED = "saved"
    PENDING = "pending"
    ACCEPTED = "accepted"
    REFUSED = "refused"
    PARTIALLY_ACCEPTED = "partially_accepted"

class TimesheetStatus(Enum):
    SAVED = "saved"
    PENDING = "pending"
    VALIDATED = "validated"
    REFUSED = "refused"
