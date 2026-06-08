-- ============================================================
--  Pizzeria Planning App — init_db.sql
--  À exécuter une seule fois pour créer toutes les tables.
--  Compatible MariaDB 10.5+
--  Usage : mysql -u root -p pizzeria_db < init_db.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS pizzeria_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE pizzeria_db;

-- ------------------------------------------------------------
-- 1. MANAGERS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS managers (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    pseudo      VARCHAR(80)     NOT NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_managers_pseudo (pseudo)
) ENGINE=InnoDB;


-- ------------------------------------------------------------
-- 2. EMPLOYEES
-- Soft-delete via is_active pour conserver l'historique des plannings.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employees (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    manager_id      INT UNSIGNED    NOT NULL,
    name            VARCHAR(100)    NOT NULL,
    role            ENUM(
                        'manager',
                        'assistant',
                        'employee'
                    )               NOT NULL DEFAULT 'employee',
    hours_per_week  DECIMAL(5,2)    NOT NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    CONSTRAINT fk_employees_manager
        FOREIGN KEY (manager_id) REFERENCES managers(id)
        ON DELETE RESTRICT
) ENGINE=InnoDB;


-- ------------------------------------------------------------
-- 3. SERVICE_CONFIGS
-- Une ligne par (manager, jour de semaine, type de service).
-- day_of_week : 0 = lundi … 6 = dimanche
-- service_type : morning | evening
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS service_configs (
    id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    manager_id      INT UNSIGNED    NOT NULL,
    day_of_week     TINYINT         NOT NULL COMMENT '0=lun 6=dim',
    service_type    ENUM(
                        'morning',
                        'evening'
                    )               NOT NULL,
    open_time       TIME            NOT NULL,
    close_time      TIME            NOT NULL,
    required_staff  TINYINT         NOT NULL DEFAULT 2,
    break_start     TIME                NULL COMMENT 'Début pause non payée',
    break_end       TIME                NULL COMMENT 'Fin pause non payée',

    PRIMARY KEY (id),
    UNIQUE KEY uq_service_configs_day_type (manager_id, day_of_week, service_type),
    CONSTRAINT fk_service_configs_manager
        FOREIGN KEY (manager_id) REFERENCES managers(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;


-- ------------------------------------------------------------
-- 4. SERVICE_SLOTS
-- Créneaux spéciaux rattachés à un service :
--   opening   : ouverture avant le service soir
--   arrival   : heure d'arrivée possible dans le service
--   departure : heure de départ possible dans le service
--   close     : fermeture après le service soir
-- required_staff : utilisé uniquement pour opening et close.
-- end_time        : utilisé uniquement pour opening et close.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS service_slots (
    id                  INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    service_config_id   INT UNSIGNED    NOT NULL,
    slot_type           ENUM(
                            'opening',
                            'arrival',
                            'departure',
                            'close'
                        )               NOT NULL,
    start_time          TIME            NOT NULL,
    end_time            TIME                NULL,
    required_staff      TINYINT             NULL,

    PRIMARY KEY (id),
    CONSTRAINT fk_service_slots_config
        FOREIGN KEY (service_config_id) REFERENCES service_configs(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;


-- ------------------------------------------------------------
-- 5. SCHEDULES
-- Un planning par semaine.
-- week_start : toujours un lundi (DATE du lundi de la semaine).
-- status     : draft = en cours de construction / published = validé
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schedules (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    manager_id  INT UNSIGNED    NOT NULL,
    week_start  DATE            NOT NULL COMMENT 'Lundi de la semaine',
    status      ENUM(
                    'draft',
                    'published'
                )               NOT NULL DEFAULT 'draft',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_schedules_manager_week (manager_id, week_start),
    CONSTRAINT fk_schedules_manager
        FOREIGN KEY (manager_id) REFERENCES managers(id)
        ON DELETE RESTRICT
) ENGINE=InnoDB;


-- ------------------------------------------------------------
-- 6. SHIFTS
-- Un shift = un créneau de travail pour un employé sur un jour.
-- Un employé peut avoir deux shifts le même jour (matin + soir).
-- slot_id : optionnel — lie le shift à un service_slot (ouverture/close…)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shifts (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    schedule_id INT UNSIGNED    NOT NULL,
    employee_id INT UNSIGNED    NOT NULL,
    day_of_week TINYINT         NOT NULL COMMENT '0=lun 6=dim',
    start_time  TIME            NOT NULL,
    end_time    TIME            NOT NULL,
    slot_id     INT UNSIGNED        NULL COMMENT 'Lien optionnel vers service_slots',

    PRIMARY KEY (id),
    CONSTRAINT fk_shifts_schedule
        FOREIGN KEY (schedule_id) REFERENCES schedules(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_shifts_employee
        FOREIGN KEY (employee_id) REFERENCES employees(id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_shifts_slot
        FOREIGN KEY (slot_id) REFERENCES service_slots(id)
        ON DELETE SET NULL
) ENGINE=InnoDB;


-- ------------------------------------------------------------
-- 7. PLANNING_CONSTRAINTS
-- Contraintes posées sur un employé pour un planning donné,
-- avant la génération automatique.
--
-- constraint_type :
--   unavailable      → absent ce jour (ou toute la semaine si day_of_week IS NULL)
--   forced           → imposé sur ce jour
--   exclude_service  → exclu d'un service (morning/evening) ce jour
--
-- forced_start / forced_end : renseignés uniquement pour type = 'forced'
-- exclude_service_type      : renseigné uniquement pour type = 'exclude_service'
-- hours_override            : delta d'heures (+/-) pour ce planning uniquement
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS planning_constraints (
    id                      INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    schedule_id             INT UNSIGNED    NOT NULL,
    employee_id             INT UNSIGNED    NOT NULL,
    constraint_type         ENUM(
                                'unavailable',
                                'forced',
                                'exclude_service'
                            )               NOT NULL,
    day_of_week             TINYINT             NULL COMMENT 'NULL = toute la semaine',
    forced_start            TIME                NULL,
    forced_end              TIME                NULL,
    exclude_service_type    ENUM(
                                'morning',
                                'evening'
                            )                   NULL,
    hours_override          DECIMAL(5,2)        NULL COMMENT 'Delta +/- heures semaine',

    PRIMARY KEY (id),
    CONSTRAINT fk_constraints_schedule
        FOREIGN KEY (schedule_id) REFERENCES schedules(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_constraints_employee
        FOREIGN KEY (employee_id) REFERENCES employees(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;


-- ------------------------------------------------------------
-- 8. FEEDBACKS
-- Retours des managers sur l'app.
-- status :
--   unread       → pas encore lu par le super-admin (toi)
--   refused      → refusé / pas prévu
--   in_progress  → en cours d'intégration
--   integrated   → intégré dans l'app
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feedbacks (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    manager_id  INT UNSIGNED    NOT NULL,
    message     TEXT            NOT NULL,
    status      ENUM(
                    'unread',
                    'refused',
                    'in_progress',
                    'integrated'
                )               NOT NULL DEFAULT 'unread',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    CONSTRAINT fk_feedbacks_manager
        FOREIGN KEY (manager_id) REFERENCES managers(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;
