/* ============================================================
   login.js
   ============================================================ */

const DAYS = ['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'];

/* ---------------------------------------------------------- */
/*  THÈME SWITCHER SUR LA PAGE LOGIN                          */
/* ---------------------------------------------------------- */
function buildLoginThemeSwitcher() {
  const container = document.getElementById('login-theme-switcher');
  if (!container) return;
  const THEMES = ['light','dark','red','blue'];
  THEMES.forEach(t => {
    const btn = document.createElement('button');
    btn.className = 'theme-btn';
    btn.dataset.theme = t;
    btn.title = `Thème ${t}`;
    btn.setAttribute('aria-label', `Thème ${t}`);
    const saved = localStorage.getItem('pizzaplan_theme') || 'light';
    if (t === saved) btn.classList.add('active');
    btn.addEventListener('click', () => applyTheme(t));
    container.appendChild(btn);
  });
}

/* ---------------------------------------------------------- */
/*  FORMULAIRE DE LOGIN                                       */
/* ---------------------------------------------------------- */
document.getElementById('login-form').addEventListener('submit', async e => {
  e.preventDefault();

  const pseudo    = document.getElementById('pseudo').value.trim();
  const errorEl   = document.getElementById('pseudo-error');
  const btnText   = document.getElementById('btn-text');
  const spinner   = document.getElementById('btn-spinner');
  const submitBtn = document.getElementById('submit-btn');

  errorEl.classList.add('hidden');

  if (!pseudo) {
    errorEl.textContent = 'Veuillez entrer votre pseudo.';
    errorEl.classList.remove('hidden');
    return;
  }

  // État chargement
  submitBtn.disabled = true;
  btnText.textContent = 'Connexion…';
  spinner.classList.remove('hidden');

  try {
    const data = await apiPost('/api/auth/login', { pseudo });

    // Affiche le message d'accueil
    showGreeting(data.manager.pseudo, data.is_new);

    if (data.is_new) {
      // Petit délai pour que l'animation du greeting soit visible
      setTimeout(() => openOnboarding(), 700);
    } else {
      setTimeout(() => { window.location.href = '/dashboard'; }, 600);
    }
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove('hidden');
    submitBtn.disabled = false;
    btnText.textContent = 'Connexion';
    spinner.classList.add('hidden');
  }
});

function showGreeting(pseudo, isNew) {
  const el   = document.getElementById('greeting');
  const text = document.getElementById('greeting-text');
  text.textContent = isNew
    ? `Bienvenue ${pseudo} ! 👋`
    : `Bon retour, ${pseudo} ! 👋`;
  el.style.display = 'block';
  requestAnimationFrame(() => el.classList.add('visible'));
}

/* ---------------------------------------------------------- */
/*  ONBOARDING — config services par défaut                  */
/* ---------------------------------------------------------- */

const DEFAULT_MORNING = { open: '10:30', close: '14:30', staff: 3 };
const DEFAULT_EVENING = { open: '17:30', close: '23:00', staff: 5,
                          break_start: '14:30', break_end: '17:30' };

function openOnboarding() {
  buildOnboardingForm();
  openModal('onboarding-modal');
}

function buildOnboardingForm() {
  const body = document.getElementById('onboarding-body');
  body.innerHTML = '';

  DAYS.forEach((dayName, dayIdx) => {
    const section = document.createElement('div');
    section.className = 'onboarding-day';
    section.innerHTML = `
      <div class="onboarding-day-header">
        <span class="onboarding-day-name">${dayName}</span>
        <label class="toggle-label">
          <input type="checkbox" class="day-active-toggle"
                 data-day="${dayIdx}" checked>
          <span class="toggle-track-small"></span>
          <span class="text-xs text-2">Actif</span>
        </label>
      </div>
      <div class="onboarding-day-body" id="day-body-${dayIdx}">
        ${buildServiceRow(dayIdx, 'morning', DEFAULT_MORNING)}
        ${buildServiceRow(dayIdx, 'evening', DEFAULT_EVENING)}
      </div>
    `;
    body.appendChild(section);

    // Toggle actif/inactif
    section.querySelector('.day-active-toggle').addEventListener('change', e => {
      document.getElementById(`day-body-${dayIdx}`)
        .classList.toggle('disabled', !e.target.checked);
    });
  });
}

function buildServiceRow(dayIdx, stype, defaults) {
  const label = stype === 'morning' ? '☀️ Matin' : '🌙 Soir';
  const breakHtml = stype === 'evening' ? `
    <div class="service-row-field">
      <label class="form-label">Début pause</label>
      <input class="form-input form-input-sm" type="time"
             name="break_start" data-day="${dayIdx}" data-stype="${stype}"
             value="${defaults.break_start || ''}">
    </div>
    <div class="service-row-field">
      <label class="form-label">Fin pause</label>
      <input class="form-input form-input-sm" type="time"
             name="break_end" data-day="${dayIdx}" data-stype="${stype}"
             value="${defaults.break_end || ''}">
    </div>` : '';

  return `
    <div class="service-row" data-day="${dayIdx}" data-stype="${stype}">
      <div class="service-row-label">${label}</div>
      <div class="service-row-fields">
        <div class="service-row-field">
          <label class="form-label">Ouverture</label>
          <input class="form-input form-input-sm" type="time"
                 name="open_time" data-day="${dayIdx}" data-stype="${stype}"
                 value="${defaults.open}">
        </div>
        <div class="service-row-field">
          <label class="form-label">Fermeture</label>
          <input class="form-input form-input-sm" type="time"
                 name="close_time" data-day="${dayIdx}" data-stype="${stype}"
                 value="${defaults.close}">
        </div>
        ${breakHtml}
        <div class="service-row-field">
          <label class="form-label">Nb personnes</label>
          <input class="form-input form-input-sm" type="number"
                 name="required_staff" data-day="${dayIdx}" data-stype="${stype}"
                 value="${defaults.staff}" min="1" max="20">
        </div>
      </div>
    </div>`;
}

document.getElementById('onboarding-save').addEventListener('click', async () => {
  const spinner = document.getElementById('onboarding-spinner');
  spinner.classList.remove('hidden');

  const configs = collectOnboardingData();

  try {
    for (const cfg of configs) {
      await apiPost('/api/settings', cfg);
    }
    toastSuccess('Configuration enregistrée !');
    closeModal('onboarding-modal');
    setTimeout(() => { window.location.href = '/dashboard'; }, 500);
  } catch (err) {
    toastError(err.message);
  } finally {
    spinner.classList.add('hidden');
  }
});

document.getElementById('onboarding-skip').addEventListener('click', () => {
  closeModal('onboarding-modal');
  window.location.href = '/dashboard';
});

function collectOnboardingData() {
  const configs = [];
  DAYS.forEach((_, dayIdx) => {
    const body   = document.getElementById(`day-body-${dayIdx}`);
    if (body.classList.contains('disabled')) return;

    ['morning','evening'].forEach(stype => {
      const row = body.querySelector(`.service-row[data-stype="${stype}"]`);
      if (!row) return;

      const get = name => row.querySelector(`[name="${name}"]`)?.value || '';

      const open  = get('open_time');
      const close = get('close_time');
      if (!open || !close) return;

      const cfg = {
        day_of_week:    dayIdx,
        service_type:   stype,
        open_time:      open,
        close_time:     close,
        required_staff: parseInt(get('required_staff')) || 2,
      };

      const bs = get('break_start');
      const be = get('break_end');
      if (bs) cfg.break_start = bs;
      if (be) cfg.break_end   = be;

      configs.push(cfg);
    });
  });
  return configs;
}

/* ---------------------------------------------------------- */
/*  INIT                                                      */
/* ---------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  buildLoginThemeSwitcher();
});