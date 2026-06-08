/* ============================================================
   team.js — Gestion de l'équipe
   ============================================================ */

const ROLE_LABELS = {
  manager:   'Manager',
  assistant: 'Assistant Manager',
  employee:  'Employé',
};

const ROLE_BADGE = {
  manager:   'badge-accent',
  assistant: 'badge-info',
  employee:  'badge-neutral',
};

let allEmployees = [];
let activeFilter = 'all';
let searchQuery  = '';
let pendingDeleteId = null;

/* ---------------------------------------------------------- */
/*  INIT                                                      */
/* ---------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  loadEmployees();

  document.getElementById('add-emp-btn')
    .addEventListener('click', () => openEmpModal());

  document.getElementById('emp-save-btn')
    .addEventListener('click', saveEmployee);

  document.getElementById('delete-confirm-btn')
    .addEventListener('click', confirmDelete);

  // Filtres par rôle
  document.querySelectorAll('.filter-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeFilter = btn.dataset.role;
      renderTable();
    });
  });

  // Recherche
  document.getElementById('team-search').addEventListener('input', e => {
    searchQuery = e.target.value.toLowerCase().trim();
    renderTable();
  });
});

/* ---------------------------------------------------------- */
/*  CHARGEMENT                                                */
/* ---------------------------------------------------------- */
async function loadEmployees() {
  try {
    allEmployees = await apiGet('/api/employees');
    renderStats();
    renderTable();
    const count = allEmployees.length;
    document.getElementById('team-subtitle').textContent =
      `${count} équipier${count > 1 ? 's' : ''} dans votre équipe`;
  } catch (err) {
    toastError(err.message);
    document.getElementById('team-subtitle').textContent = 'Erreur de chargement';
  }
}

/* ---------------------------------------------------------- */
/*  STATS                                                     */
/* ---------------------------------------------------------- */
function renderStats() {
  const managers   = allEmployees.filter(e => e.role === 'manager').length;
  const assistants = allEmployees.filter(e => e.role === 'assistant').length;
  const employees  = allEmployees.filter(e => e.role === 'employee').length;
  const totalH     = allEmployees.reduce((s, e) => s + e.hours_per_week, 0);

  document.getElementById('team-stats').innerHTML = `
    <div class="stat-card">
      <div class="stat-value">${allEmployees.length}</div>
      <div class="stat-label">Équipiers au total</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${managers + assistants}</div>
      <div class="stat-label">Managers &amp; Assistants</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${formatHours(totalH)}</div>
      <div class="stat-label">Heures contractuelles / sem.</div>
    </div>`;
}

/* ---------------------------------------------------------- */
/*  RENDU TABLEAU                                             */
/* ---------------------------------------------------------- */
function renderTable() {
  const tbody = document.getElementById('team-tbody');
  const empty = document.getElementById('team-empty');

  let filtered = allEmployees;

  if (activeFilter !== 'all') {
    filtered = filtered.filter(e => e.role === activeFilter);
  }

  if (searchQuery) {
    filtered = filtered.filter(e =>
      e.name.toLowerCase().includes(searchQuery) ||
      ROLE_LABELS[e.role].toLowerCase().includes(searchQuery)
    );
  }

  // Tri : managers → assistants → employés, puis alphabétique
  filtered.sort((a, b) => {
    const order = { manager: 0, assistant: 1, employee: 2 };
    return (order[a.role] ?? 3) - (order[b.role] ?? 3) || a.name.localeCompare(b.name, 'fr');
  });

  tbody.innerHTML = '';

  if (filtered.length === 0) {
    document.getElementById('team-table-wrapper')
      .querySelector('table').style.display = 'none';
    empty.classList.remove('hidden');
    return;
  }

  document.getElementById('team-table-wrapper')
    .querySelector('table').style.display = '';
  empty.classList.add('hidden');

  filtered.forEach(emp => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <div class="emp-name-cell">
          <div class="emp-avatar emp-avatar-${emp.role}">
            ${emp.name.charAt(0).toUpperCase()}
          </div>
          <span class="emp-name">${escHtml(emp.name)}</span>
        </div>
      </td>
      <td>
        <span class="badge ${ROLE_BADGE[emp.role]}">
          ${ROLE_LABELS[emp.role]}
        </span>
      </td>
      <td>
        <span class="emp-hours font-mono">${emp.hours_per_week}h</span>
      </td>
      <td>
        <span class="badge badge-success">Actif</span>
      </td>
      <td>
        <div class="emp-actions">
          <button class="btn btn-ghost btn-sm btn-icon" title="Modifier"
                  onclick="openEmpModal(${emp.id})">✏️</button>
          <button class="btn btn-ghost btn-sm btn-icon" title="Retirer"
                  onclick="openDeleteModal(${emp.id}, '${escHtml(emp.name)}')">🗑️</button>
        </div>
      </td>`;
    tbody.appendChild(tr);
  });
}

/* ---------------------------------------------------------- */
/*  MODAL AJOUT / ÉDITION                                     */
/* ---------------------------------------------------------- */
function openEmpModal(empId = null) {
  const titleEl   = document.getElementById('emp-modal-title');
  const saveText  = document.getElementById('emp-save-text');
  const idInput   = document.getElementById('emp-id');
  const nameInput = document.getElementById('emp-name');
  const roleInput = document.getElementById('emp-role');
  const hoursInput= document.getElementById('emp-hours');

  // Réinitialise les erreurs
  document.getElementById('emp-name-error').classList.add('hidden');
  document.getElementById('emp-hours-error').classList.add('hidden');

  if (empId) {
    const emp = allEmployees.find(e => e.id === empId);
    if (!emp) return;
    titleEl.textContent  = 'Modifier l\'équipier';
    saveText.textContent = 'Enregistrer';
    idInput.value        = emp.id;
    nameInput.value      = emp.name;
    roleInput.value      = emp.role;
    hoursInput.value     = emp.hours_per_week;
  } else {
    titleEl.textContent  = 'Ajouter un équipier';
    saveText.textContent = 'Ajouter';
    idInput.value        = '';
    nameInput.value      = '';
    roleInput.value      = 'employee';
    hoursInput.value     = '';
  }

  openModal('emp-modal');
  setTimeout(() => nameInput.focus(), 250);
}

async function saveEmployee() {
  const empId  = document.getElementById('emp-id').value;
  const name   = document.getElementById('emp-name').value.trim();
  const role   = document.getElementById('emp-role').value;
  const hours  = document.getElementById('emp-hours').value;
  const btn    = document.getElementById('emp-save-btn');
  const spinner= document.getElementById('emp-save-spinner');

  // Validation front
  let valid = true;

  if (!name) {
    showFieldError('emp-name-error', 'Nom requis');
    valid = false;
  } else {
    document.getElementById('emp-name-error').classList.add('hidden');
  }

  if (!hours || parseFloat(hours) <= 0 || parseFloat(hours) > 60) {
    showFieldError('emp-hours-error', 'Entre 1 et 60 heures');
    valid = false;
  } else {
    document.getElementById('emp-hours-error').classList.add('hidden');
  }

  if (!valid) return;

  btn.disabled = true;
  spinner.classList.remove('hidden');

  const payload = { name, role, hours_per_week: parseFloat(hours) };

  try {
    if (empId) {
      await apiPut(`/api/employees/${empId}`, payload);
      toastSuccess('Équipier mis à jour');
    } else {
      await apiPost('/api/employees', payload);
      toastSuccess('Équipier ajouté !');
    }
    closeModal('emp-modal');
    await loadEmployees();
  } catch (err) {
    toastError(err.message);
  } finally {
    btn.disabled = false;
    spinner.classList.add('hidden');
  }
}

/* ---------------------------------------------------------- */
/*  SUPPRESSION                                               */
/* ---------------------------------------------------------- */
function openDeleteModal(empId, empName) {
  pendingDeleteId = empId;
  document.getElementById('delete-confirm-text').textContent =
    `Retirer ${empName} de l'équipe ? Cette action est réversible depuis la base de données mais l'équipier n'apparaîtra plus dans les nouveaux plannings.`;
  openModal('delete-modal');
}

async function confirmDelete() {
  if (!pendingDeleteId) return;
  const btn = document.getElementById('delete-confirm-btn');
  btn.disabled = true;

  try {
    await apiDelete(`/api/employees/${pendingDeleteId}`);
    toastSuccess('Équipier retiré');
    closeModal('delete-modal');
    pendingDeleteId = null;
    await loadEmployees();
  } catch (err) {
    toastError(err.message);
    btn.disabled = false;
  }
}

/* ---------------------------------------------------------- */
/*  UTILS                                                     */
/* ---------------------------------------------------------- */
function showFieldError(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.classList.remove('hidden');
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;')
            .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}