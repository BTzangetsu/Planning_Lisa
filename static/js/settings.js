/* ============================================================
   settings.js — Configuration des services par jour
   Stratégie : configs{} est la source de vérité unique.
   Le DOM lit depuis configs, et on écrit dans configs au save.
   ============================================================ */

const DAYS      = ['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'];
const SVC_LABEL = { morning: '☀️ Service matin', evening: '🌙 Service soir' };

let configs   = {};   // configs[dayIdx][stype] = objet config
let activeDay = 0;

/* ---------------------------------------------------------- */
/*  INIT                                                      */
/* ---------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', async () => {
  buildDayTabs();
  await loadSettings();
  renderDay(activeDay);
  document.getElementById('save-all-btn').addEventListener('click', saveAll);
  document.getElementById('slot-save-btn').addEventListener('click', saveSlot);
  // slot-type change : attaché dans openSlotModal après ouverture
});

/* ---------------------------------------------------------- */
/*  TABS JOURS                                                */
/* ---------------------------------------------------------- */
function buildDayTabs() {
  const container = document.getElementById('days-tabs');
  DAYS.forEach((name, idx) => {
    const btn = document.createElement('button');
    btn.className = `day-tab ${idx === 0 ? 'active' : ''}`;
    btn.textContent = name.slice(0, 3);
    btn.dataset.day = idx;
    btn.addEventListener('click', () => {
      // 1. Persiste le DOM du jour courant dans configs AVANT de changer
      syncDomToConfigs(activeDay);
      // 2. Change de jour
      document.querySelectorAll('.day-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeDay = idx;
      // 3. Render depuis configs (pas depuis le DOM)
      renderDay(idx);
    });
    container.appendChild(btn);
  });
}

/* ---------------------------------------------------------- */
/*  CHARGEMENT API → configs{}                                */
/* ---------------------------------------------------------- */
async function loadSettings() {
  document.getElementById('settings-loading').style.display = 'flex';
  try {
    const data = await apiGet('/api/settings');
    configs = {};
    data.forEach(cfg => {
      if (!configs[cfg.day_of_week]) configs[cfg.day_of_week] = {};
      configs[cfg.day_of_week][cfg.service_type] = {
        id:             cfg.id,
        day_of_week:    cfg.day_of_week,
        service_type:   cfg.service_type,
        open_time:      cfg.open_time,
        close_time:     cfg.close_time,
        required_staff: cfg.required_staff,
        break_start:    cfg.break_start || '',
        break_end:      cfg.break_end   || '',
        slots:          cfg.slots       || [],
      };
    });
  } catch (err) {
    toastError(err.message);
  } finally {
    document.getElementById('settings-loading').style.display = 'none';
  }
}

/* ---------------------------------------------------------- */
/*  DOM → configs{} (sync avant save ou changement de jour)  */
/* ---------------------------------------------------------- */
function syncDomToConfigs(dayIdx) {
  ['morning', 'evening'].forEach(stype => {
    const activeChk = document.getElementById(`svc-active-${dayIdx}-${stype}`);
    if (!activeChk) return; // service non rendu

    if (!configs[dayIdx]) configs[dayIdx] = {};

    if (!activeChk.checked) {
      // Service désactivé — on marque mais on garde l'id pour pouvoir supprimer
      if (configs[dayIdx][stype]) configs[dayIdx][stype]._disabled = true;
      return;
    }

    const open  = document.getElementById(`open_${dayIdx}_${stype}`)?.value  || '';
    const close = document.getElementById(`close_${dayIdx}_${stype}`)?.value || '';
    const staff = document.getElementById(`staff_${dayIdx}_${stype}`)?.value || '2';

    const existing = configs[dayIdx][stype] || {};

    configs[dayIdx][stype] = {
      ...existing,
      day_of_week:    dayIdx,
      service_type:   stype,
      open_time:      open,
      close_time:     close,
      required_staff: parseInt(staff) || 2,
      slots:          existing.slots || [],
      _disabled:      false,
    };

    if (stype === 'evening') {
      configs[dayIdx][stype].break_start =
        document.getElementById(`break_start_${dayIdx}`)?.value || '';
      configs[dayIdx][stype].break_end =
        document.getElementById(`break_end_${dayIdx}`)?.value   || '';
    }
  });
}

/* ---------------------------------------------------------- */
/*  configs{} → DOM (render)                                  */
/* ---------------------------------------------------------- */
function renderDay(dayIdx) {
  const content = document.getElementById('settings-content');
  document.getElementById('settings-loading').style.display = 'none';

  const dayCfg  = configs[dayIdx] || {};
  const hasData = Object.keys(dayCfg).filter(k => !k.startsWith('_')).length > 0;

  content.innerHTML = `
    <div class="settings-day-panel" id="day-panel-${dayIdx}">
      <div class="settings-day-header">
        <span class="settings-day-title">${DAYS[dayIdx]}</span>
        <label class="toggle-label">
          <input type="checkbox" id="day-active-${dayIdx}"
                 ${hasData ? 'checked' : ''}
                 onchange="toggleDay(${dayIdx}, this.checked)">
          <span class="toggle-track-small"></span>
          <span class="text-sm text-2">Jour actif</span>
        </label>
      </div>

      <div id="day-services-${dayIdx}" class="${!hasData ? 'hidden' : ''}">
        ${buildServicePanel(dayIdx, 'morning', dayCfg.morning)}
        ${buildServicePanel(dayIdx, 'evening', dayCfg.evening)}
      </div>

      <div class="settings-inactive ${hasData ? 'hidden' : ''}"
           id="day-inactive-${dayIdx}">
        <span class="text-3">Ce jour est désactivé — aucun service ne sera planifié.</span>
      </div>
    </div>`;
}

function buildServicePanel(dayIdx, stype, cfg) {
  const active = !!cfg && !cfg._disabled;
  const label  = SVC_LABEL[stype];
  const slots  = active ? (cfg.slots || []) : [];
  const slotsHtml = slots.map((s, i) => buildSlotRow(dayIdx, stype, s, i)).join('');

  const openVal  = cfg?.open_time  || (stype === 'morning' ? '10:30' : '17:30');
  const closeVal = cfg?.close_time || (stype === 'morning' ? '14:30' : '23:00');
  const staffVal = cfg?.required_staff || 3;

  const breakHtml = stype === 'evening' ? `
    <div class="flex gap-12">
      <div class="form-group" style="flex:1">
        <label class="form-label">Début pause (non payée)</label>
        <input class="form-input" type="time" id="break_start_${dayIdx}"
               value="${cfg?.break_start || '14:30'}">
      </div>
      <div class="form-group" style="flex:1">
        <label class="form-label">Fin pause</label>
        <input class="form-input" type="time" id="break_end_${dayIdx}"
               value="${cfg?.break_end || '17:30'}">
      </div>
    </div>` : '';

  return `
    <div class="service-panel" id="svc-${dayIdx}-${stype}">
      <div class="service-panel-header">
        <div class="flex items-center gap-12">
          <span class="service-panel-title">${label}</span>
          <label class="toggle-label">
            <input type="checkbox" id="svc-active-${dayIdx}-${stype}"
                   ${active ? 'checked' : ''}
                   onchange="toggleService(${dayIdx}, '${stype}', this.checked)">
            <span class="toggle-track-small"></span>
            <span class="text-xs text-2">Actif</span>
          </label>
        </div>
      </div>
      <div class="service-panel-body ${!active ? 'hidden' : ''}"
           id="svc-body-${dayIdx}-${stype}">
        <div class="flex gap-12">
          <div class="form-group" style="flex:1">
            <label class="form-label">Ouverture</label>
            <input class="form-input" type="time"
                   id="open_${dayIdx}_${stype}" value="${openVal}">
          </div>
          <div class="form-group" style="flex:1">
            <label class="form-label">Fermeture</label>
            <input class="form-input" type="time"
                   id="close_${dayIdx}_${stype}" value="${closeVal}">
          </div>
          <div class="form-group" style="flex:1">
            <label class="form-label">Nb personnes requis</label>
            <input class="form-input" type="number"
                   id="staff_${dayIdx}_${stype}" min="1" max="20" value="${staffVal}">
          </div>
        </div>
        ${breakHtml}
        <div class="slots-section">
          <div class="slots-header">
            <span class="slots-title">Créneaux spéciaux</span>
            <button class="btn btn-ghost btn-sm"
                    onclick="openSlotModal(${dayIdx}, '${stype}')">+ Ajouter</button>
          </div>
          <div class="slots-list" id="slots-${dayIdx}-${stype}">
            ${slotsHtml || '<p class="text-xs text-3 slots-empty">Aucun créneau défini</p>'}
          </div>
        </div>
      </div>
    </div>`;
}

function buildSlotRow(dayIdx, stype, slot, idx) {
  const typeLabels = {
    opening: '🔑 Ouverture', arrival: '➡️ Arrivée',
    departure: '⬅️ Départ',  close: '🔒 Close',
  };
  const staffInfo = slot.required_staff
    ? `<span class="slot-staff">${slot.required_staff} pers.</span>` : '';
  const timeInfo  = slot.end_time
    ? `${slot.start_time} → ${slot.end_time}` : slot.start_time;

  return `
    <div class="slot-row">
      <span class="slot-type-label">${typeLabels[slot.slot_type] || slot.slot_type}</span>
      <span class="slot-time font-mono">${timeInfo}</span>
      ${staffInfo}
      <button class="btn btn-ghost btn-sm btn-icon slot-delete"
              onclick="deleteSlot(${dayIdx}, '${stype}', ${idx})">✕</button>
    </div>`;
}

/* ---------------------------------------------------------- */
/*  TOGGLES                                                   */
/* ---------------------------------------------------------- */
function toggleDay(dayIdx, active) {
  document.getElementById(`day-services-${dayIdx}`).classList.toggle('hidden', !active);
  document.getElementById(`day-inactive-${dayIdx}`).classList.toggle('hidden', active);
  if (!active && configs[dayIdx]) configs[dayIdx]._deleted = true;
  else if (configs[dayIdx])       delete configs[dayIdx]._deleted;
}

function toggleService(dayIdx, stype, active) {
  document.getElementById(`svc-body-${dayIdx}-${stype}`).classList.toggle('hidden', !active);
}

/* ---------------------------------------------------------- */
/*  SLOTS                                                     */
/* ---------------------------------------------------------- */
function openSlotModal(dayIdx, stype) {
  document.getElementById('slot-day').value   = dayIdx;
  document.getElementById('slot-stype').value = stype;
  document.getElementById('slot-start').value = '';
  document.getElementById('slot-end').value   = '';
  document.getElementById('slot-staff').value = 2;
  document.getElementById('slot-modal-title').textContent = 'Ajouter un créneau';

  const typeSelect = document.getElementById('slot-type');
  typeSelect.value = stype === 'evening' ? 'opening' : 'arrival';
  typeSelect.querySelectorAll('option').forEach(opt => {
    opt.hidden = stype === 'morning' && opt.value === 'opening';
  });

  typeSelect.onchange = updateSlotModalFields;
  updateSlotModalFields();

  // Charge les créneaux existants des autres jours (même service_type)
  loadExistingSlots(dayIdx, stype);

  openModal('slot-modal');
}

function loadExistingSlots(currentDay, stype) {
  const container = document.getElementById('existing-slots-list');
  if (!container) return;

  // Collecte tous les slots uniques des autres jours pour ce stype
  const seen = new Set();
  const slots = [];

  Object.entries(configs).forEach(([dayIdx, dayCfg]) => {
    if (parseInt(dayIdx) === currentDay) return;
    const cfg = dayCfg[stype];
    if (!cfg || !cfg.slots) return;
    cfg.slots.forEach(s => {
      const key = `${s.slot_type}|${s.start_time}|${s.end_time || ''}|${s.required_staff || ''}`;
      if (!seen.has(key)) {
        seen.add(key);
        slots.push({ ...s, _fromDay: parseInt(dayIdx) });
      }
    });
  });

  if (slots.length === 0) {
    container.innerHTML = '<span class="text-xs text-3">Aucun créneau enregistré sur les autres jours.</span>';
    return;
  }

  const typeLabels = { opening: '🔑 Ouverture', arrival: '➡️ Arrivée', departure: '⬅️ Départ' };

  container.innerHTML = slots.map((s, i) => {
    const timeInfo  = s.end_time ? `${s.start_time} → ${s.end_time}` : s.start_time;
    const staffInfo = s.required_staff ? ` · ${s.required_staff} pers.` : '';
    return `
      <button class="existing-slot-chip" onclick="applyExistingSlot(${i})" data-idx="${i}">
        <span>${typeLabels[s.slot_type] || s.slot_type}</span>
        <span class="font-mono">${timeInfo}${staffInfo}</span>
        <span class="text-3">${DAYS[s._fromDay]}</span>
      </button>`;
  }).join('');

  // Stocke temporairement pour applyExistingSlot
  container._slots = slots;
}

function applyExistingSlot(idx) {
  const container = document.getElementById('existing-slots-list');
  const slot = container._slots?.[idx];
  if (!slot) return;

  const typeSelect = document.getElementById('slot-type');
  typeSelect.value = slot.slot_type;
  document.getElementById('slot-start').value = slot.start_time;
  document.getElementById('slot-end').value   = slot.end_time || '';
  document.getElementById('slot-staff').value = slot.required_staff || 2;

  updateSlotModalFields();

  // Highlight le chip sélectionné
  container.querySelectorAll('.existing-slot-chip').forEach((btn, i) => {
    btn.classList.toggle('selected', i === idx);
  });
}

function updateSlotModalFields() {
  const type       = document.getElementById('slot-type')?.value;
  const endGroup   = document.getElementById('slot-end-group');
  const staffGroup = document.getElementById('slot-staff-group');
  const endInput   = document.getElementById('slot-end');
  const staffInput = document.getElementById('slot-staff');
  if (!endGroup || !staffGroup) return;

  const needsExtra = ['opening', 'close'].includes(type);
  endGroup.style.opacity   = needsExtra ? '1' : '0.4';
  staffGroup.style.opacity = needsExtra ? '1' : '0.4';
  if (endInput)   endInput.disabled   = !needsExtra;
  if (staffInput) staffInput.disabled = !needsExtra;
}

function saveSlot() {
  const dayIdx = parseInt(document.getElementById('slot-day').value);
  const stype  = document.getElementById('slot-stype').value;
  const type   = document.getElementById('slot-type').value;
  const start  = document.getElementById('slot-start').value;
  const end    = document.getElementById('slot-end').value;
  const staff  = document.getElementById('slot-staff').value;

  if (!start) { toastError('Heure de début requise'); return; }

  const slot = { slot_type: type, start_time: start };
  if (['opening','close'].includes(type)) {
    if (end)   slot.end_time       = end;
    if (staff) slot.required_staff = parseInt(staff);
  }

  if (!configs[dayIdx])        configs[dayIdx] = {};
  if (!configs[dayIdx][stype]) configs[dayIdx][stype] = {
    day_of_week: dayIdx, service_type: stype,
    open_time:   stype === 'morning' ? '10:30' : '17:30',
    close_time:  stype === 'morning' ? '14:30' : '23:00',
    required_staff: 3, slots: [],
  };
  if (!configs[dayIdx][stype].slots) configs[dayIdx][stype].slots = [];
  configs[dayIdx][stype].slots.push(slot);

  closeModal('slot-modal');
  renderDay(dayIdx);
  toastInfo('Créneau ajouté — pensez à enregistrer');
}

function deleteSlot(dayIdx, stype, idx) {
  configs[dayIdx]?.[stype]?.slots?.splice(idx, 1);
  renderDay(dayIdx);
  toastInfo('Créneau supprimé — pensez à enregistrer');
}

/* ---------------------------------------------------------- */
/*  SAUVEGARDE                                                */
/* ---------------------------------------------------------- */
async function saveAll() {
  const btn     = document.getElementById('save-all-btn');
  const text    = document.getElementById('save-all-text');
  const spinner = document.getElementById('save-all-spinner');

  // Persiste le DOM courant dans configs avant tout
  syncDomToConfigs(activeDay);

  btn.disabled = true;
  text.textContent = 'Enregistrement…';
  spinner.classList.remove('hidden');

  try {
    const dayCfg = configs[activeDay] || {};

    // Supprime si jour désactivé
    if (dayCfg._deleted) {
      for (const stype of ['morning', 'evening']) {
        if (dayCfg[stype]?.id) await apiDelete(`/api/settings/${dayCfg[stype].id}`);
      }
      toastSuccess(`${DAYS[activeDay]} désactivé !`);
      await loadSettings();
      renderDay(activeDay);
      return;
    }

    // Sauvegarde chaque service actif depuis configs (pas le DOM)
    for (const stype of ['morning', 'evening']) {
      const cfg = dayCfg[stype];
      if (!cfg || cfg._disabled || !cfg.open_time || !cfg.close_time) continue;

      const payload = {
        day_of_week:    activeDay,
        service_type:   stype,
        open_time:      cfg.open_time,
        close_time:     cfg.close_time,
        required_staff: cfg.required_staff || 2,
        slots:          cfg.slots || [],
      };

      if (stype === 'evening') {
        if (cfg.break_start) payload.break_start = cfg.break_start;
        if (cfg.break_end)   payload.break_end   = cfg.break_end;
      }

      await apiPost('/api/settings', payload);
    }

    toastSuccess(`${DAYS[activeDay]} enregistré !`);
    await loadSettings();
    renderDay(activeDay);
  } catch (err) {
    toastError(err.message);
  } finally {
    btn.disabled = false;
    text.textContent = 'Enregistrer';
    spinner.classList.add('hidden');
  }
}