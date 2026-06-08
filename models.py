from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


# ------------------------------------------------------------------ #
#  MANAGERS                                                           #
# ------------------------------------------------------------------ #
class Manager(db.Model):
    __tablename__ = 'managers'

    id         = db.Column(db.Integer, primary_key=True)
    pseudo     = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employees        = db.relationship('Employee',       backref='manager', lazy=True)
    service_configs  = db.relationship('ServiceConfig',  backref='manager', lazy=True)
    schedules        = db.relationship('Schedule',       backref='manager', lazy=True)
    feedbacks        = db.relationship('Feedback',       backref='manager', lazy=True)

    def to_dict(self):
        return {
            'id':         self.id,
            'pseudo':     self.pseudo,
            'created_at': self.created_at.isoformat(),
        }


# ------------------------------------------------------------------ #
#  EMPLOYEES                                                          #
# ------------------------------------------------------------------ #
class Employee(db.Model):
    __tablename__ = 'employees'

    ROLE_LABELS = {
        'manager':   'Manager',
        'assistant': 'Assistant Manager',
        'employee':  'Employé',
    }

    id             = db.Column(db.Integer, primary_key=True)
    manager_id     = db.Column(db.Integer, db.ForeignKey('managers.id'), nullable=False)
    name           = db.Column(db.String(100), nullable=False)
    role           = db.Column(
                        db.Enum('manager', 'assistant', 'employee'),
                        nullable=False, default='employee')
    hours_per_week = db.Column(db.Numeric(5, 2), nullable=False)
    is_active      = db.Column(db.Boolean, default=True, nullable=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    shifts      = db.relationship('Shift',               backref='employee', lazy=True)
    constraints = db.relationship('PlanningConstraint',  backref='employee', lazy=True)

    def to_dict(self):
        return {
            'id':             self.id,
            'name':           self.name,
            'role':           self.role,
            'role_label':     self.ROLE_LABELS.get(self.role, self.role),
            'hours_per_week': float(self.hours_per_week),
            'is_active':      self.is_active,
            'created_at':     self.created_at.isoformat(),
        }


# ------------------------------------------------------------------ #
#  SERVICE_CONFIGS                                                    #
#  Une ligne par (manager, jour, type de service).                   #
#  day_of_week : 0 = lundi … 6 = dimanche                           #
# ------------------------------------------------------------------ #
class ServiceConfig(db.Model):
    __tablename__ = 'service_configs'

    id             = db.Column(db.Integer, primary_key=True)
    manager_id     = db.Column(db.Integer, db.ForeignKey('managers.id'),  nullable=False)
    day_of_week    = db.Column(db.SmallInteger, nullable=False)
    service_type   = db.Column(db.Enum('morning', 'evening'),             nullable=False)
    open_time      = db.Column(db.Time, nullable=False)
    close_time     = db.Column(db.Time, nullable=False)
    required_staff = db.Column(db.SmallInteger, nullable=False, default=2)
    break_start    = db.Column(db.Time, nullable=True)
    break_end      = db.Column(db.Time, nullable=True)

    slots = db.relationship('ServiceSlot', backref='service_config',
                            lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('manager_id', 'day_of_week', 'service_type',
                            name='uq_service_configs_day_type'),
    )

    def to_dict(self):
        return {
            'id':             self.id,
            'manager_id':     self.manager_id,
            'day_of_week':    self.day_of_week,
            'service_type':   self.service_type,
            'open_time':      self.open_time.strftime('%H:%M') if self.open_time else None,
            'close_time':     self.close_time.strftime('%H:%M') if self.close_time else None,
            'required_staff': self.required_staff,
            'break_start':    self.break_start.strftime('%H:%M') if self.break_start else None,
            'break_end':      self.break_end.strftime('%H:%M') if self.break_end else None,
            'slots':          [s.to_dict() for s in self.slots],
        }


# ------------------------------------------------------------------ #
#  SERVICE_SLOTS                                                      #
#  Créneaux spéciaux d'un service : ouverture, arrivées,             #
#  départs, close.                                                    #
#  required_staff : uniquement pour opening et close.                #
#  end_time       : uniquement pour opening et close.                #
# ------------------------------------------------------------------ #
class ServiceSlot(db.Model):
    __tablename__ = 'service_slots'

    id                = db.Column(db.Integer, primary_key=True)
    service_config_id = db.Column(db.Integer,
                                  db.ForeignKey('service_configs.id'), nullable=False)
    slot_type         = db.Column(
                            db.Enum('opening', 'arrival', 'departure', 'close'),
                            nullable=False)
    start_time        = db.Column(db.Time, nullable=False)
    end_time          = db.Column(db.Time, nullable=True)
    required_staff    = db.Column(db.SmallInteger, nullable=True)

    def to_dict(self):
        return {
            'id':             self.id,
            'slot_type':      self.slot_type,
            'start_time':     self.start_time.strftime('%H:%M'),
            'end_time':       self.end_time.strftime('%H:%M') if self.end_time else None,
            'required_staff': self.required_staff,
        }


# ------------------------------------------------------------------ #
#  SCHEDULES                                                          #
#  Un planning par semaine. week_start = le lundi de la semaine.     #
# ------------------------------------------------------------------ #
class Schedule(db.Model):
    __tablename__ = 'schedules'

    id         = db.Column(db.Integer, primary_key=True)
    manager_id = db.Column(db.Integer, db.ForeignKey('managers.id'), nullable=False)
    week_start = db.Column(db.Date, nullable=False)
    status     = db.Column(db.Enum('draft', 'published'),
                           nullable=False, default='draft')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    shifts      = db.relationship('Shift',              backref='schedule',
                                  lazy=True, cascade='all, delete-orphan')
    constraints = db.relationship('PlanningConstraint', backref='schedule',
                                  lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('manager_id', 'week_start',
                            name='uq_schedules_manager_week'),
    )

    def to_dict(self, with_shifts=False):
        data = {
            'id':         self.id,
            'manager_id': self.manager_id,
            'week_start': self.week_start.isoformat(),
            'status':     self.status,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        if with_shifts:
            data['shifts'] = [s.to_dict() for s in self.shifts]
        return data


# ------------------------------------------------------------------ #
#  SHIFTS                                                             #
#  Un shift = un créneau de travail pour un employé sur un jour.     #
#  Deux shifts possibles le même jour (matin + soir = coupure).      #
# ------------------------------------------------------------------ #
class Shift(db.Model):
    __tablename__ = 'shifts'

    id          = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules.id'),  nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'),  nullable=False)
    day_of_week = db.Column(db.SmallInteger, nullable=False)
    start_time  = db.Column(db.Time, nullable=False)
    end_time    = db.Column(db.Time, nullable=False)
    slot_id     = db.Column(db.Integer, db.ForeignKey('service_slots.id'), nullable=True)

    slot = db.relationship('ServiceSlot', lazy=True)

    def duration_hours(self):
        """Durée du shift en heures (sans compter les pauses)."""
        start = self.start_time.hour * 60 + self.start_time.minute
        end   = self.end_time.hour   * 60 + self.end_time.minute
        return round((end - start) / 60, 2)

    def to_dict(self):
        return {
            'id':          self.id,
            'schedule_id': self.schedule_id,
            'employee_id': self.employee_id,
            'day_of_week': self.day_of_week,
            'start_time':  self.start_time.strftime('%H:%M'),
            'end_time':    self.end_time.strftime('%H:%M'),
            'slot_id':     self.slot_id,
            'hours':       self.duration_hours(),
        }


# ------------------------------------------------------------------ #
#  PLANNING_CONSTRAINTS                                               #
#  Contraintes par employé pour un planning donné.                   #
#  day_of_week NULL = contrainte sur toute la semaine.               #
# ------------------------------------------------------------------ #
class PlanningConstraint(db.Model):
    __tablename__ = 'planning_constraints'

    id                   = db.Column(db.Integer, primary_key=True)
    schedule_id          = db.Column(db.Integer, db.ForeignKey('schedules.id'),  nullable=False)
    employee_id          = db.Column(db.Integer, db.ForeignKey('employees.id'),  nullable=False)
    constraint_type      = db.Column(
                               db.Enum('unavailable', 'forced', 'exclude_service'),
                               nullable=False)
    day_of_week          = db.Column(db.SmallInteger, nullable=True)  # NULL = toute la semaine
    forced_start         = db.Column(db.Time, nullable=True)
    forced_end           = db.Column(db.Time, nullable=True)
    exclude_service_type = db.Column(db.Enum('morning', 'evening'), nullable=True)
    hours_override       = db.Column(db.Numeric(5, 2), nullable=True)

    def to_dict(self):
        return {
            'id':                   self.id,
            'schedule_id':          self.schedule_id,
            'employee_id':          self.employee_id,
            'constraint_type':      self.constraint_type,
            'day_of_week':          self.day_of_week,
            'forced_start':         self.forced_start.strftime('%H:%M') if self.forced_start else None,
            'forced_end':           self.forced_end.strftime('%H:%M') if self.forced_end else None,
            'exclude_service_type': self.exclude_service_type,
            'hours_override':       float(self.hours_override) if self.hours_override else None,
        }


# ------------------------------------------------------------------ #
#  FEEDBACKS                                                          #
#  Retours des managers sur l'app.                                   #
#  Statuts : unread → refused / in_progress → integrated            #
# ------------------------------------------------------------------ #
class Feedback(db.Model):
    __tablename__ = 'feedbacks'

    STATUS_LABELS = {
        'unread':      'Non lu',
        'refused':     'Refusé',
        'in_progress': 'En cours',
        'integrated':  'Intégré',
    }

    id         = db.Column(db.Integer, primary_key=True)
    manager_id = db.Column(db.Integer, db.ForeignKey('managers.id'), nullable=False)
    message    = db.Column(db.Text, nullable=False)
    status     = db.Column(
                     db.Enum('unread', 'refused', 'in_progress', 'integrated'),
                     nullable=False, default='unread')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id':           self.id,
            'manager_id':   self.manager_id,
            'manager':      self.manager.pseudo if self.manager else None,
            'message':      self.message,
            'status':       self.status,
            'status_label': self.STATUS_LABELS.get(self.status, self.status),
            'created_at':   self.created_at.isoformat(),
            'updated_at':   self.updated_at.isoformat(),
        }