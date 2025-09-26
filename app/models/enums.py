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

class ProjectActivityType(Enum):
    NORMALE = "Normale"
    ASTREINTE_CALENDAIRE_SEMAINE = "Astreinte Calendaire Semaine"
    ASTREINTE_CALENDAIRE_SAMEDI = "Astreinte Calendaire Samedi"
    ASTREINTE_CALENDAIRE_DIMANCHE = "Astreinte Calendaire Dimanche"
    ASTREINTE_CALENDAIRE_JOURS_FERIES = "Astreinte Calendaire Jours Fériés"

class AbsenceRequestType(Enum):
    CP = "CP"
    RTT = "RTT"
    CONGES_SANS_SOLDE = "Congés Sans Solde"
    MALADIE = "Maladie"
    EXCEPTIONNELLE = "Exceptionnelle"
    PATERNITE = "Paternité"
    MATERNITE = "Maternité"

class AbsenceRequestStatus(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REFUSED = "refused"
    PARTIALLY_ACCEPTED = "partially_accepted"