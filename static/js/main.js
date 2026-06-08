/* ============================================================
   PizzaPlan — main.js
   Utilitaires globaux : thème, toasts, API, modals
   ============================================================ */

/* ---------------------------------------------------------- */
/*  THÈME                                                     */
/* ---------------------------------------------------------- */

const THEMES = ['light', 'dark', 'red', 'blue'];
const THEME_KEY = 'pizzaplan_theme';

function applyTheme(theme) {
  if (!THEMES.includes(theme)) theme = 'light';
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_KEY, theme);
  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.theme === theme);
  });
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY) || 'light';
  applyTheme(saved);
}

// Injecte le sélecteur de thème dans la nav
function injectThemeSwitcher() {
  const navRight = document.querySelector('.nav-right');
  if (!navRight) return;

  const switcher = document.createElement('div');
  switcher.className = 'theme-switcher';
  THEMES.forEach(t => {
    const btn = document.createElement('button');
    btn.className = 'theme-btn';
    btn.dataset.theme = t;
    btn.title = `Thème ${t}`;
    btn.setAttribute('aria-label', `Thème ${t}`);
    btn.addEventListener('click', () => applyTheme(t));
    switcher.appendChild(btn);
  });
  navRight.prepend(switcher);
}

/* ---------------------------------------------------------- */
/*  TOASTS                                                    */
/* ---------------------------------------------------------- */

function toast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span class="toast-dot"></span><span>${message}</span>`;
  container.appendChild(el);

  setTimeout(() => {
    el.classList.add('removing');
    el.addEventListener('animationend', () => el.remove());
  }, duration);
}

const toastSuccess = msg => toast(msg, 'success');
const toastError   = msg => toast(msg, 'error', 4500);
const toastWarning = msg => toast(msg, 'warning');
const toastInfo    = msg => toast(msg, 'info');

/* ---------------------------------------------------------- */
/*  API HELPER                                                */
/* ---------------------------------------------------------- */

async function api(method, url, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
  };
  if (body) opts.body = JSON.stringify(body);

  try {
    const res = await fetch(url, opts);
    const data = await res.json();

    if (!res.ok) {
      const msg = data?.error || `Erreur ${res.status}`;
      throw new Error(msg);
    }
    return data;
  } catch (err) {
    if (err.name === 'TypeError') {
      throw new Error('Impossible de contacter le serveur');
    }
    throw err;
  }
}

const apiGet    = url       => api('GET',    url);
const apiPost   = (url, b)  => api('POST',   url, b);
const apiPut    = (url, b)  => api('PUT',    url, b);
const apiDelete = url       => api('DELETE', url);

/* ---------------------------------------------------------- */
/*  AUTH                                                      */
/* ---------------------------------------------------------- */

async function logout() {
  try {
    await apiPost('/api/auth/logout');
  } catch (_) {}
  window.location.href = '/';
}

/* ---------------------------------------------------------- */
/*  MODALS                                                    */
/* ---------------------------------------------------------- */

function openModal(id) {
  const backdrop = document.getElementById(id);
  if (!backdrop) return;
  backdrop.style.display = 'flex';
  requestAnimationFrame(() => backdrop.classList.add('open'));
  document.body.style.overflow = 'hidden';
}

function closeModal(id) {
  const backdrop = document.getElementById(id);
  if (!backdrop) return;
  backdrop.classList.remove('open');
  document.body.style.overflow = '';
  backdrop.addEventListener('transitionend', () => {
    backdrop.style.display = 'none';
  }, { once: true });
}

// Ferme les modals en cliquant en dehors
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-backdrop')) {
    e.target.classList.remove('open');
    document.body.style.overflow = '';
    setTimeout(() => { e.target.style.display = 'none'; }, 220);
  }
});

// Ferme avec Escape
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop.open').forEach(m => {
      m.classList.remove('open');
      document.body.style.overflow = '';
      setTimeout(() => { m.style.display = 'none'; }, 220);
    });
  }
});

/* ---------------------------------------------------------- */
/*  UTILS                                                     */
/* ---------------------------------------------------------- */

function formatHours(h) {
  const total = Math.round(h * 60);
  const hh = Math.floor(total / 60);
  const mm = total % 60;
  return mm === 0 ? `${hh}h` : `${hh}h${String(mm).padStart(2, '0')}`;
}

function isoMonday(date = new Date()) {
  const d = new Date(date);
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  d.setHours(0, 0, 0, 0);
  return d;
}

function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

function toISO(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function weekLabel(monday) {
  const sunday = addDays(monday, 6);
  const fmt = d => d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
  return `${fmt(monday)} – ${fmt(sunday)}`;
}

/* ---------------------------------------------------------- */
/*  INIT                                                      */
/* ---------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  injectThemeSwitcher();
});


/* ---------------------------------------------------------- */
/*  FEEDBACK WIDGET                                           */
/* ---------------------------------------------------------- */

async function initFeedbackWidget() {
  const msg  = document.getElementById('feedback-msg');
  const send = document.getElementById('feedback-send-btn');
  if (!msg) return;

  // Compteur caractères
  msg.addEventListener('input', () => {
    document.getElementById('feedback-char').textContent =
      `${msg.value.length} / 2000`;
  });

  // Envoyer
  send.addEventListener('click', async () => {
    const message = msg.value.trim();
    if (!message) { toastError('Message vide'); return; }
    send.disabled = true;
    try {
      await apiPost('/api/feedbacks', { message });
      msg.value = '';
      document.getElementById('feedback-char').textContent = '0 / 2000';
      toastSuccess('Retour envoyé, merci !');
      loadMyFeedbacks();
    } catch (err) {
      toastError(err.message);
    } finally {
      send.disabled = false;
    }
  });

  // Charge mes feedbacks quand on ouvre la modal
  document.getElementById('feedback-fab')?.addEventListener('click', loadMyFeedbacks);
}

async function loadMyFeedbacks() {
  const container = document.getElementById('my-feedbacks-list');
  if (!container) return;

  const STATUS = {
    unread:      { label:'Non lu',   cls:'badge-neutral' },
    in_progress: { label:'En cours', cls:'badge-warning' },
    integrated:  { label:'Intégré',  cls:'badge-success' },
    refused:     { label:'Refusé',   cls:'badge-danger'  },
  };

  try {
    const feedbacks = await apiGet('/api/feedbacks/mine');
    if (!feedbacks.length) {
      container.innerHTML = '<span class="text-3">Aucun retour envoyé pour l\'instant.</span>';
      return;
    }
    container.innerHTML = feedbacks.slice(0,5).map(f => {
      const s   = STATUS[f.status] || STATUS.unread;
      const date = new Date(f.created_at).toLocaleDateString('fr-FR',{day:'numeric',month:'short'});
      return `
        <div class="my-feedback-row">
          <span class="my-feedback-msg">${f.message.slice(0,60)}${f.message.length>60?'…':''}</span>
          <span class="badge ${s.cls}">${s.label}</span>
          <span class="text-3" style="font-size:0.75rem">${date}</span>
        </div>`;
    }).join('');
  } catch (_) {
    container.innerHTML = '<span class="text-3">Impossible de charger les retours.</span>';
  }
}

document.addEventListener('DOMContentLoaded', initFeedbackWidget);