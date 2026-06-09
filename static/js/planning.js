/* ============================================================
   planning.js — Création et génération de planning
   ============================================================ */

const DAYS_FULL  = ['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'];
const DAYS_SHORT = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'];
const ROLE_LABELS = { manager:'Manager', assistant:'Assistant Manager', employee:'Employé' };

// État global
let employees    = [];
let validated    = new Set();   // employee_ids validés
let constraints  = {};          // employee_id -> liste de contraintes
let generatedShifts = null;     // shifts retournés par l'API
let scheduleId   = null;

/* ---------------------------------------------------------- */
/*  INIT                                                      */
/* ---------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', async () => {
  // Label semaine
  const monday = new Date(WEEK_START);
  document.getElementById('planning-week-label').textContent = weekLabel(monday);

  // Récupère le schedule existant
  try {
    const schedule = await apiGet(`/api/schedules/${WEEK_START}`);
    if (!schedule) {
      toastError('Planning introuvable, retour au dashboard');
      setTimeout(() => window.location.href = '/dashboard', 1500);
      return;
    }
    scheduleId = schedule.id;
  } catch (err) {
    toastError(err.message);
    return;
  }

  // Charge les employés
  try {
    employees = await apiGet('/api/employees');
  } catch (err) {
    toastError(err.message);
    return;
  }

  renderEmpList();

  document.getElementById('generate-btn-2')
    .addEventListener('click', startGeneration);

  document.getElementById('validate-all-btn')
    .addEventListener('click', () => {
      employees.forEach(emp => validated.add(emp.id));
      renderEmpList();
      toastSuccess('Tous les équipiers validés !');
    });
  document.getElementById('regenerate-btn')
    .addEventListener('click', startGeneration);
  document.getElementById('confirm-btn')
    .addEventListener('click', confirmPlanning);
  document.getElementById('cm-save-btn')
    .addEventListener('click', saveConstraints);
  document.getElementById('cm-add-forced')
    .addEventListener('click', addForcedRow);
  // Bouton retour : supprime le draft vide si aucun shift n'a été confirmé
  document.querySelector('a[href="/dashboard"]')?.addEventListener('click', async e => {
    if (generatedShifts !== null) return; // planning généré mais pas confirmé : on garde le draft
    try {
      const schedule = await apiGet(`/api/schedules/${WEEK_START}`);
      // Supprime seulement si le planning est encore un draft sans shifts
      if (schedule && schedule.status === 'draft' &&
          (!schedule.shifts || schedule.shifts.length === 0)) {
        await apiDelete(`/api/schedules/${WEEK_START}`);
      }
    } catch (_) {}
    // laisse la navigation se faire normalement
  });

  document.getElementById('cm-absent-week')
    .addEventListener('change', e => {
      const disabled = e.target.checked;
      document.getElementById('cm-days-section').style.opacity  = disabled ? '0.4' : '1';
      document.getElementById('cm-excl-section').style.opacity  = disabled ? '0.4' : '1';
      document.getElementById('cm-forced-section').style.opacity= disabled ? '0.4' : '1';
      ['cm-days-section','cm-excl-section','cm-forced-section'].forEach(id => {
        document.getElementById(id).querySelectorAll('input,select')
          .forEach(el => el.disabled = disabled);
      });
    });
});

/* ---------------------------------------------------------- */
/*  LISTE ÉQUIPIERS                                           */
/* ---------------------------------------------------------- */
function renderEmpList() {
  const container = document.getElementById('emp-list');
  container.innerHTML = '';

  const sorted = [...employees].sort((a,b) => {
    const o = {manager:0, assistant:1, employee:2};
    return (o[a.role]??3)-(o[b.role]??3) || a.name.localeCompare(b.name,'fr');
  });

  sorted.forEach(emp => {
    const isValidated = validated.has(emp.id);
    const hasConstraints = constraints[emp.id]?.length > 0;

    const card = document.createElement('div');
    card.className = `emp-constraint-card ${isValidated ? 'validated' : ''}`;
    card.id = `emp-card-${emp.id}`;
    card.innerHTML = `
      <div class="emp-constraint-info">
        <div class="emp-avatar emp-avatar-${emp.role}">
          ${emp.name.charAt(0).toUpperCase()}
        </div>
        <div>
          <div class="emp-constraint-name">${escHtml(emp.name)}</div>
          <div class="emp-constraint-meta">
            ${ROLE_LABELS[emp.role]} · ${emp.hours_per_week}h/sem
            ${hasConstraints ? `<span class="badge badge-warning ml-8">${constraints[emp.id].length} contrainte(s)</span>` : ''}
          </div>
        </div>
      </div>
      <div class="emp-constraint-actions">
        <button class="btn btn-secondary btn-sm" onclick="openConstraintModal(${emp.id})">
          ⚙️ Contraintes
        </button>
        <button class="btn ${isValidated ? 'btn-success' : 'btn-primary'} btn-sm"
                onclick="toggleValidate(${emp.id})">
          ${isValidated ? '✓ Validé' : 'Valider'}
        </button>
      </div>`;
    container.appendChild(card);
  });

  updateValidatedCount();
}

function updateValidatedCount() {
  const total = employees.length;
  const count = validated.size;
  document.getElementById('validated-count').textContent = `${count} / ${total} validés`;

  const canGenerate = count === total && total > 0;
  document.getElementById('generate-btn-2').disabled = !canGenerate;
  if (canGenerate) {
    document.getElementById('generate-btn-2').classList.add('btn-pulse');
  }
}

function toggleValidate(empId) {
  if (validated.has(empId)) {
    validated.delete(empId);
  } else {
    validated.add(empId);
  }
  renderEmpList();
}

/* ---------------------------------------------------------- */
/*  MODAL CONTRAINTES                                         */
/* ---------------------------------------------------------- */
let currentEmpId = null;

function openConstraintModal(empId) {
  currentEmpId = empId;
  const emp = employees.find(e => e.id === empId);
  if (!emp) return;

  document.getElementById('cm-emp-name').textContent = emp.name;
  document.getElementById('cm-emp-info').textContent =
    `${ROLE_LABELS[emp.role]} · ${emp.hours_per_week}h / semaine`;

  const existing = constraints[empId] || [];

  // Absent toute la semaine
  const absentAll = existing.some(c => c.constraint_type === 'unavailable' && c.day_of_week === null);
  // Bouton retour : supprime le draft vide si aucun shift n'a été confirmé
  document.querySelector('a[href="/dashboard"]')?.addEventListener('click', async e => {
    if (generatedShifts !== null) return; // planning généré mais pas confirmé : on garde le draft
    try {
      const schedule = await apiGet(`/api/schedules/${WEEK_START}`);
      // Supprime seulement si le planning est encore un draft sans shifts
      if (schedule && schedule.status === 'draft' &&
          (!schedule.shifts || schedule.shifts.length === 0)) {
        await apiDelete(`/api/schedules/${WEEK_START}`);
      }
    } catch (_) {}
    // laisse la navigation se faire normalement
  });

  document.getElementById('cm-absent-week').checked = absentAll;

  // Jours indisponibles
  const unavailDays = existing
    .filter(c => c.constraint_type === 'unavailable' && c.day_of_week !== null)
    .map(c => c.day_of_week);

  const daysContainer = document.getElementById('cm-days');
  daysContainer.innerHTML = DAYS_FULL.map((name, idx) => `
    <label class="day-checkbox-label">
      <input type="checkbox" value="${idx}" ${unavailDays.includes(idx) ? 'checked' : ''}
             class="cm-unavail-day">
      <span>${name}</span>
    </label>`).join('');

  // Exclusions de service
  const exclContainer = document.getElementById('cm-excl');
  exclContainer.innerHTML = '';
  DAYS_FULL.forEach((name, dayIdx) => {
    const exclMorn = existing.some(c =>
      c.constraint_type === 'exclude_service' &&
      c.day_of_week === dayIdx && c.exclude_service_type === 'morning');
    const exclEven = existing.some(c =>
      c.constraint_type === 'exclude_service' &&
      c.day_of_week === dayIdx && c.exclude_service_type === 'evening');

    exclContainer.innerHTML += `
      <div class="excl-row">
        <span class="excl-day">${name.slice(0,3)}</span>
        <label class="excl-label">
          <input type="checkbox" value="morning" data-day="${dayIdx}"
                 class="cm-excl-svc" ${exclMorn ? 'checked' : ''}>
          <span>Matin</span>
        </label>
        <label class="excl-label">
          <input type="checkbox" value="evening" data-day="${dayIdx}"
                 class="cm-excl-svc" ${exclEven ? 'checked' : ''}>
          <span>Soir</span>
        </label>
      </div>`;
  });

  // Jours imposés
  const forced = existing.filter(c => c.constraint_type === 'forced');
  const forcedList = document.getElementById('cm-forced-list');
  forcedList.innerHTML = '';
  forced.forEach(c => addForcedRow(c));

  // Override heures
  const override = existing.find(c => c.hours_override !== null && c.hours_override !== undefined);
  document.getElementById('cm-hours-override').value = override?.hours_override ?? '';

  openModal('constraint-modal');
}

function addForcedRow(existing = null) {
  const list = document.getElementById('cm-forced-list');
  const row  = document.createElement('div');
  row.className = 'forced-row';
  row.innerHTML = `
    <select class="form-select form-select-sm cm-forced-day">
      ${DAYS_FULL.map((n,i) => `<option value="${i}" ${existing?.day_of_week===i?'selected':''}>${n}</option>`).join('')}
    </select>
    <input class="form-input form-input-sm" type="time" placeholder="Début"
           value="${existing?.forced_start || ''}" class-ref="cm-forced-start">
    <input class="form-input form-input-sm" type="time" placeholder="Fin"
           value="${existing?.forced_end || ''}" class-ref="cm-forced-end">
    <button class="btn btn-ghost btn-sm btn-icon" onclick="this.parentElement.remove()">✕</button>`;
  list.appendChild(row);
}

function saveConstraints() {
  const empId = currentEmpId;
  if (!empId) return;

  const list = [];

  // Absent toute la semaine
  if (document.getElementById('cm-absent-week').checked) {
    list.push({ constraint_type: 'unavailable', day_of_week: null });
  } else {
    // Jours indisponibles
    document.querySelectorAll('.cm-unavail-day:checked').forEach(el => {
      list.push({ constraint_type: 'unavailable', day_of_week: parseInt(el.value) });
    });

    // Exclusions service
    document.querySelectorAll('.cm-excl-svc:checked').forEach(el => {
      list.push({
        constraint_type:      'exclude_service',
        day_of_week:          parseInt(el.dataset.day),
        exclude_service_type: el.value,
      });
    });

    // Jours imposés
    document.querySelectorAll('.forced-row').forEach(row => {
      const day   = parseInt(row.querySelector('.cm-forced-day').value);
      const start = row.querySelectorAll('input[type="time"]')[0].value;
      const end   = row.querySelectorAll('input[type="time"]')[1].value;
      if (start && end) {
        list.push({
          constraint_type: 'forced',
          day_of_week:     day,
          forced_start:    start,
          forced_end:      end,
        });
      }
    });
  }

  // Override heures
  const override = parseFloat(document.getElementById('cm-hours-override').value);
  if (!isNaN(override) && override !== 0) {
    list.push({ constraint_type: 'unavailable', hours_override: override });
    // On attache l'override à la première contrainte ou séparément
    list[list.length - 1] = {
      constraint_type: list[0]?.constraint_type || 'unavailable',
      hours_override:  override,
      day_of_week:     null,
    };
  }

  constraints[empId] = list;

  // Sauvegarde en base
  apiPost(`/api/schedules/${WEEK_START}/constraints`, {
    employee_id: empId,
    constraints: list,
  }).catch(err => toastError(err.message));

  closeModal('constraint-modal');
  toastSuccess('Contraintes enregistrées');
  renderEmpList();
}

/* ---------------------------------------------------------- */
/*  GÉNÉRATION                                                */
/* ---------------------------------------------------------- */
async function startGeneration() {
  // Passe à l'étape 2
  setPhase('generating');

  try {
    const result = await apiPost(`/api/schedules/${WEEK_START}/generate`, {});

    generatedShifts = result.shifts;

    // Met à jour le label tentatives
    document.getElementById('gen-attempt-label').textContent =
      `Planning trouvé en ${result.attempts} tentative(s)`;

    await new Promise(r => setTimeout(r, 600)); // petit délai pour l'animation

    renderResult(result);
    setPhase('result');
  } catch (err) {
    toastError(err.message);
    setPhase('constraints');
  }
}

/* ---------------------------------------------------------- */
/*  RENDU RÉSULTAT                                            */
/* ---------------------------------------------------------- */
function renderResult(result) {
  const { shifts, anomalies, attempts } = result;

  // Meta
  document.getElementById('result-meta').textContent =
    `Généré en ${attempts} tentative(s) · ${shifts.length} shifts · ${anomalies.length} anomalie(s)`;

  // Anomalies
  const anomSection = document.getElementById('anomalies-section');
  const anomList    = document.getElementById('anomalies-list');
  anomList.innerHTML = '';

  if (anomalies.length > 0) {
    anomalies.forEach(a => {
      const div = document.createElement('div');
      div.className = `alert alert-${a.level === 'critical' ? 'critical' : 'warning'} mb-8`;
      div.innerHTML = `<span>${a.level === 'critical' ? '🚨' : '⚠️'}</span><span>${a.message}</span>`;
      anomList.appendChild(div);
    });
    anomSection.classList.remove('hidden');
  } else {
    anomSection.classList.add('hidden');
  }

  // Grille calendrier
  renderResultGrid(shifts);

  // Récap heures
  renderHoursRecap(shifts);
}

function renderResultGrid(shifts) {
  const grid = document.getElementById('result-grid');
  grid.innerHTML = '';

  const monday = new Date(WEEK_START);
  const empMap = {};
  employees.forEach(e => { empMap[e.id] = e; });

  // Index shifts
  const shiftIdx = {};
  shifts.forEach(s => {
    const key = `${s.employee_id}-${s.day_of_week}`;
    if (!shiftIdx[key]) shiftIdx[key] = [];
    shiftIdx[key].push(s);
  });

  // En-tête
  const header = document.createElement('div');
  header.className = 'cal-header';
  header.innerHTML = `<div class="cal-cell cal-cell-name cal-header-cell">Équipier</div>`;
  for (let d = 0; d < 7; d++) {
    const dayDate = addDays(monday, d);
    const isToday = toISO(dayDate) === toISO(new Date());
    header.innerHTML += `
      <div class="cal-cell cal-header-cell ${isToday ? 'cal-today' : ''}">
        <span class="cal-day-short">${DAYS_SHORT[d]}</span>
        <span class="cal-day-date">${dayDate.getDate()}</span>
      </div>`;
  }
  grid.appendChild(header);

  // Lignes
  const sorted = [...employees].sort((a,b) => {
    const o = {manager:0,assistant:1,employee:2};
    return (o[a.role]??3)-(o[b.role]??3);
  });

  sorted.forEach(emp => {
    const row = document.createElement('div');
    row.className = 'cal-row';

    const nameCell = document.createElement('div');
    nameCell.className = 'cal-cell cal-cell-name';
    nameCell.innerHTML = `
      <span class="cal-emp-dot cal-dot-${emp.role}"></span>
      <span class="cal-emp-name">${emp.name}</span>`;
    row.appendChild(nameCell);

    for (let d = 0; d < 7; d++) {
      const cell   = document.createElement('div');
      const dayShifts = shiftIdx[`${emp.id}-${d}`] || [];
      cell.className = `cal-cell cal-day-cell ${dayShifts.length ? 'has-shifts' : 'cal-off'}`;

      if (dayShifts.length) {
        cell.innerHTML = dayShifts.map(s => `
          <div class="cal-shift cal-shift-${emp.role}">
            <span class="cal-shift-time">${s.start_time}–${s.end_time}</span>
          </div>`).join('');
      } else {
        cell.innerHTML = `<span class="cal-off-label">—</span>`;
      }

      row.appendChild(cell);
    }
    grid.appendChild(row);
  });
}

function renderHoursRecap(shifts) {
  const recap = document.getElementById('hours-recap');
  recap.innerHTML = '';

  const worked = {};
  shifts.forEach(s => {
    const start = s.start_time.split(':').map(Number);
    const end   = s.end_time.split(':').map(Number);
    const h = (end[0]*60+end[1] - start[0]*60-start[1]) / 60;
    worked[s.employee_id] = (worked[s.employee_id] || 0) + h;
  });

  const sorted = [...employees].sort((a,b) => {
    const o = {manager:0,assistant:1,employee:2};
    return (o[a.role]??3)-(o[b.role]??3);
  });

  recap.innerHTML = `<h3 class="section-title mb-16">Récap des heures</h3>`;
  const grid = document.createElement('div');
  grid.className = 'hours-recap-grid';

  sorted.forEach(emp => {
    const actual  = worked[emp.id] || 0;
    const target  = emp.hours_per_week;
    const delta   = actual - target;
    const sign    = delta >= 0 ? '+' : '';
    const cls     = Math.abs(delta) <= 1 ? 'ok' : delta > 0 ? 'over' : 'under';

    grid.innerHTML += `
      <div class="hours-recap-card hours-${cls}">
        <div class="flex items-center gap-8 mb-8">
          <div class="emp-avatar emp-avatar-${emp.role}" style="width:28px;height:28px;font-size:0.78rem">
            ${emp.name.charAt(0).toUpperCase()}
          </div>
          <span class="emp-name" style="font-size:0.875rem">${escHtml(emp.name)}</span>
        </div>
        <div class="hours-recap-values">
          <span class="hours-actual font-mono">${formatHours(actual)}</span>
          <span class="hours-target text-3">/ ${target}h</span>
          <span class="hours-delta hours-delta-${cls} font-mono">${sign}${delta.toFixed(1)}h</span>
        </div>
      </div>`;
  });

  recap.appendChild(grid);
}

/* ---------------------------------------------------------- */
/*  CONFIRMATION                                              */
/* ---------------------------------------------------------- */
async function confirmPlanning() {
  if (!generatedShifts) return;
  const btn = document.getElementById('confirm-btn');
  btn.disabled = true;
  btn.textContent = 'Enregistrement…';

  try {
    await apiPost(`/api/schedules/${WEEK_START}/generate/confirm`, {
      shifts: generatedShifts,
    });
    toastSuccess('Planning validé et enregistré !');
    setTimeout(() => window.location.href = '/dashboard', 800);
  } catch (err) {
    toastError(err.message);
    btn.disabled = false;
    btn.textContent = '✓ Valider ce planning';
  }
}

/* ---------------------------------------------------------- */
/*  NAVIGATION PHASES                                         */
/* ---------------------------------------------------------- */
function setPhase(phase) {
  document.getElementById('phase-constraints').classList.toggle('hidden', phase !== 'constraints');
  document.getElementById('phase-generating').classList.toggle('hidden', phase !== 'generating');
  document.getElementById('phase-result').classList.toggle('hidden', phase !== 'result');

  document.getElementById('step-1').classList.toggle('active',   phase === 'constraints');
  document.getElementById('step-1').classList.toggle('done',     phase !== 'constraints');
  document.getElementById('step-2').classList.toggle('active',   phase === 'generating');
  document.getElementById('step-2').classList.toggle('done',     phase === 'result');
  document.getElementById('step-3').classList.toggle('active',   phase === 'result');
}

/* ---------------------------------------------------------- */
/*  UTILS                                                     */
/* ---------------------------------------------------------- */
function escHtml(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
                    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
