/* ============================================================
   dashboard.js — Calendrier semaine navigable
   ============================================================ */

const DAYS_SHORT = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'];
const DAYS_FULL  = ['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'];

let currentMonday = isoMonday();
let currentSchedule = null;

/* ---------------------------------------------------------- */
/*  INIT                                                      */
/* ---------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  renderWeekNav();
  loadWeek(currentMonday);

  document.getElementById('prev-week').addEventListener('click', () => {
    currentMonday = addDays(currentMonday, -7);
    renderWeekNav();
    loadWeek(currentMonday);
  });

  document.getElementById('next-week').addEventListener('click', () => {
    currentMonday = addDays(currentMonday, 7);
    renderWeekNav();
    loadWeek(currentMonday);
  });

  document.getElementById('today-btn').addEventListener('click', () => {
    currentMonday = isoMonday();
    renderWeekNav();
    loadWeek(currentMonday);
  });

  document.getElementById('new-planning-btn').addEventListener('click', openNewPlanningModal);
  document.getElementById('create-planning-btn').addEventListener('click', createPlanning);
});

/* ---------------------------------------------------------- */
/*  NAVIGATION SEMAINE                                        */
/* ---------------------------------------------------------- */
function renderWeekNav() {
  document.getElementById('week-label').textContent = weekLabel(currentMonday);
  const isToday = toISO(currentMonday) === toISO(isoMonday());
  document.getElementById('today-btn').disabled = isToday;
}

/* ---------------------------------------------------------- */
/*  CHARGEMENT DU PLANNING                                    */
/* ---------------------------------------------------------- */
async function loadWeek(monday) {
  const grid    = document.getElementById('calendar-grid');
  const empty   = document.getElementById('calendar-empty');
  const loading = document.getElementById('calendar-loading');

  grid.innerHTML    = '';
  empty.classList.add('hidden');
  loading.classList.remove('hidden');

  try {
    const data = await apiGet(`/api/schedules/${toISO(monday)}`);
    currentSchedule = data;
    loading.classList.add('hidden');

    if (!data || !data.shifts || data.shifts.length === 0) {
      empty.classList.remove('hidden');
      return;
    }

    renderCalendar(data, monday);
  } catch (err) {
    loading.classList.add('hidden');
    empty.classList.remove('hidden');
    toastError(err.message);
  }
}

/* ---------------------------------------------------------- */
/*  RENDU DU CALENDRIER                                       */
/* ---------------------------------------------------------- */
function renderCalendar(schedule, monday) {
  const grid = document.getElementById('calendar-grid');
  grid.innerHTML = '';

  const isPast = addDays(monday, 6) < new Date();

  // Collecte les employés présents dans ce planning
  const empMap = {};
  schedule.shifts.forEach(s => {
    if (!empMap[s.employee_id]) {
      empMap[s.employee_id] = {
        id:   s.employee_id,
        name: s.employee_name || `#${s.employee_id}`,
        role: s.employee_role || 'employee',
      };
    }
  });
  const employees = Object.values(empMap).sort((a, b) => {
    const order = { manager: 0, assistant: 1, employee: 2 };
    return (order[a.role] ?? 3) - (order[b.role] ?? 3) || a.name.localeCompare(b.name);
  });

  // Index shifts par (employee_id, day_of_week)
  const shiftIdx = {};
  schedule.shifts.forEach(s => {
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
        <span class="cal-day-date ${isToday ? 'cal-today-badge' : ''}">${dayDate.getDate()}</span>
      </div>`;
  }
  grid.appendChild(header);

  // Lignes employés
  employees.forEach(emp => {
    const row = document.createElement('div');
    row.className = 'cal-row';

    // Colonne nom
    const nameCell = document.createElement('div');
    nameCell.className = 'cal-cell cal-cell-name';
    nameCell.innerHTML = `
      <span class="cal-emp-dot cal-dot-${emp.role}"></span>
      <span class="cal-emp-name">${emp.name}</span>`;
    row.appendChild(nameCell);

    // Colonnes jours
    for (let d = 0; d < 7; d++) {
      const cell   = document.createElement('div');
      const shifts = shiftIdx[`${emp.id}-${d}`] || [];
      const dayDate = addDays(monday, d);
      const isToday = toISO(dayDate) === toISO(new Date());
      const editable = !isPast && toISO(dayDate) >= toISO(new Date());

      cell.className = `cal-cell cal-day-cell ${isToday ? 'cal-today-col' : ''} ${shifts.length ? 'has-shifts' : 'cal-off'}`;

      if (shifts.length) {
        cell.innerHTML = shifts.map(s => `
          <div class="cal-shift cal-shift-${emp.role}">
            <span class="cal-shift-time">${s.start_time}–${s.end_time}</span>
            <span class="cal-shift-h">${formatHours(s.hours)}</span>
          </div>`).join('');
      } else {
        cell.innerHTML = `<span class="cal-off-label">—</span>`;
      }

      if (editable) {
        cell.classList.add('cal-editable');
        cell.title = 'Cliquer pour modifier';
        cell.addEventListener('click', () => openShiftEditor(emp, d, shifts, schedule.id, toISO(monday)));
      }

      row.appendChild(cell);
    }

    grid.appendChild(row);
  });

  // Ligne total heures
  renderHoursRow(grid, schedule, employees, shiftIdx);

  // Badge statut
  const statusBadge = schedule.status === 'published'
    ? `<span class="badge badge-success">Publié</span>`
    : `<span class="badge badge-neutral">Brouillon</span>`;
  const actions = document.createElement('div');
  actions.className = 'cal-actions';
  actions.innerHTML = `
    <div class="flex items-center gap-12">
      ${statusBadge}
      ${schedule.status === 'draft' && !isPast
        ? `<a href="/planning/${toISO(monday)}" class="btn btn-primary btn-sm">Modifier / Générer</a>`
        : ''}
    </div>`;
  grid.appendChild(actions);
}

function renderHoursRow(grid, schedule, employees, shiftIdx) {
  const row = document.createElement('div');
  row.className = 'cal-row cal-row-totals';

  row.innerHTML = `<div class="cal-cell cal-cell-name cal-totals-label">Total heures</div>`;

  for (let d = 0; d < 7; d++) {
    let total = 0;
    employees.forEach(emp => {
      const shifts = shiftIdx[`${emp.id}-${d}`] || [];
      shifts.forEach(s => { total += s.hours || 0; });
    });
    row.innerHTML += `
      <div class="cal-cell cal-totals-cell">
        ${total > 0 ? `<span class="cal-total-val">${formatHours(total)}</span>` : '<span class="text-3">—</span>'}
      </div>`;
  }
  grid.appendChild(row);
}

/* ---------------------------------------------------------- */
/*  ÉDITEUR RAPIDE DE SHIFT (inline)                         */
/* ---------------------------------------------------------- */
function openShiftEditor(emp, day, shifts, scheduleId, weekStart) {
  const existing = shifts[0];
  const title    = existing ? 'Modifier le shift' : 'Ajouter un shift';

  // Simple prompt inline via modal générique
  const html = `
    <div class="shift-editor">
      <div class="shift-editor-emp">
        <span class="cal-emp-dot cal-dot-${emp.role}"></span>
        <strong>${emp.name}</strong> — ${DAYS_FULL[day]}
      </div>
      <div class="flex gap-12 mt-16">
        <div class="form-group" style="flex:1">
          <label class="form-label">Début</label>
          <input class="form-input" type="time" id="se-start"
                 value="${existing ? existing.start_time : '10:30'}">
        </div>
        <div class="form-group" style="flex:1">
          <label class="form-label">Fin</label>
          <input class="form-input" type="time" id="se-end"
                 value="${existing ? existing.end_time : '14:30'}">
        </div>
      </div>
      ${existing ? `<button class="btn btn-danger w-full mt-8" id="se-delete">Supprimer ce shift</button>` : ''}
    </div>`;

  // Réutilise la modal générique
  showGenericModal(title, html, async () => {
    const start = document.getElementById('se-start').value;
    const end   = document.getElementById('se-end').value;
    if (!start || !end) { toastError('Horaires requis'); return false; }

    try {
      if (existing) {
        await apiPut(`/api/schedules/${weekStart}/shifts/${existing.id}`, {
          employee_id: emp.id, day_of_week: day, start_time: start, end_time: end
        });
      } else {
        await apiPost(`/api/schedules/${weekStart}/shifts`, {
          employee_id: emp.id, day_of_week: day, start_time: start, end_time: end
        });
      }
      toastSuccess('Shift mis à jour');
      loadWeek(currentMonday);
      return true;
    } catch (err) {
      toastError(err.message);
      return false;
    }
  });

  // Bouton supprimer
  setTimeout(() => {
    const delBtn = document.getElementById('se-delete');
    if (delBtn) delBtn.addEventListener('click', async () => {
      try {
        await apiDelete(`/api/schedules/${weekStart}/shifts/${existing.id}`);
        toastSuccess('Shift supprimé');
        closeModal('generic-modal');
        loadWeek(currentMonday);
      } catch (err) { toastError(err.message); }
    });
  }, 50);
}

/* ---------------------------------------------------------- */
/*  MODAL GÉNÉRIQUE RÉUTILISABLE                              */
/* ---------------------------------------------------------- */
function showGenericModal(title, bodyHtml, onConfirm) {
  let modal = document.getElementById('generic-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'generic-modal';
    modal.className = 'modal-backdrop';
    modal.style.display = 'none';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-header">
          <div class="modal-title" id="gm-title"></div>
          <button class="modal-close" onclick="closeModal('generic-modal')">✕</button>
        </div>
        <div id="gm-body"></div>
        <div class="modal-footer">
          <button class="btn btn-secondary" onclick="closeModal('generic-modal')">Annuler</button>
          <button class="btn btn-primary" id="gm-confirm">Confirmer</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }

  document.getElementById('gm-title').textContent = title;
  document.getElementById('gm-body').innerHTML    = bodyHtml;

  const confirmBtn = document.getElementById('gm-confirm');
  confirmBtn.replaceWith(confirmBtn.cloneNode(true));
  document.getElementById('gm-confirm').addEventListener('click', async () => {
    const ok = await onConfirm();
    if (ok) closeModal('generic-modal');
  });

  openModal('generic-modal');
}

/* ---------------------------------------------------------- */
/*  NOUVEAU PLANNING                                          */
/* ---------------------------------------------------------- */
function openNewPlanningModal() {
  const select = document.getElementById('new-planning-week');
  select.innerHTML = '';

  // Propose les 8 prochaines semaines
  for (let i = 1; i <= 8; i++) {
    const monday = addDays(isoMonday(), i * 7);
    const opt    = document.createElement('option');
    opt.value       = toISO(monday);
    opt.textContent = weekLabel(monday);
    select.appendChild(opt);
  }

  openModal('new-planning-modal');
}

async function createPlanning() {
  const weekStart  = document.getElementById('new-planning-week').value;
  const copyPrev   = document.querySelector('[name="copy_mode"]:checked').value === 'copy';
  const btn        = document.getElementById('create-planning-btn');

  btn.disabled = true;
  btn.textContent = 'Création…';

  try {
    await apiPost('/api/schedules', { week_start: weekStart, copy_previous: copyPrev });
    closeModal('new-planning-modal');
    toastSuccess('Planning créé !');
    window.location.href = `/planning/${weekStart}`;
  } catch (err) {
    toastError(err.message);
    btn.disabled = false;
    btn.textContent = 'Créer';
  }
}