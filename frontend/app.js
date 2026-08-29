/* ============================================================================
   GARUDA — Master Client Logic
   SIH PS 26187 — Team Nexus
   ----------------------------------------------------------------------------
   This file is organised into clearly separated modules so it can be wired
   directly into a FastAPI + PostgreSQL + YOLOv8/OpenCV backend without any
   restructuring:

     GarudaConfig      -> environment / endpoint configuration
     GarudaAPI         -> thin fetch() wrapper for the REST backend
     GarudaAuthStore   -> JWT + session persistence (localStorage)
     GarudaAuth        -> login/logout flows (used by login.html)
     GarudaGuard       -> route protection (used by dashboard.html / admin.html)
     GarudaSocket      -> WebSocket client for real-time AI alerts
     GarudaState       -> in-memory client state (incidents, cameras, users)
     GarudaDashboard   -> UI controller for dashboard.html
     GarudaAdmin       -> UI controller for admin.html
     GarudaToast       -> lightweight notification helper
   ============================================================================ */

/* ---------------------------------------------------------------------------
   1. CONFIG
   --------------------------------------------------------------------------- */
const GarudaConfig = Object.freeze({
  API_BASE_URL: 'http://localhost:8000/api/v1',
  WS_BASE_URL: 'ws://localhost:8000/ws',
  TOKEN_STORAGE_KEY: 'garuda_auth_token',
  SESSION_STORAGE_KEY: 'garuda_session',
  // When false, GarudaAPI falls back to local mock data so the UI remains
  // fully demoable without a live FastAPI backend running.
  BACKEND_ENABLED: true,
});

/* ---------------------------------------------------------------------------
   2. REST API WRAPPER  (-> FastAPI)
   --------------------------------------------------------------------------- */
const GarudaAPI = {
  async _request(path, options = {}) {
    const token = GarudaAuthStore.getToken();
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    };

    const response = await fetch(`${GarudaConfig.API_BASE_URL}${path}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new Error(errorBody.detail || `Request failed: ${response.status}`);
    }
    return response.status === 204 ? null : response.json();
  },

  // --- Auth ---------------------------------------------------------------
  // POST /auth/login  { userId, password, role } -> { token, user }
  login(payload) {
    return this._request('/auth/login', { method: 'POST', body: JSON.stringify(payload) });
  },
  // POST /auth/logout
  logout() {
    return this._request('/auth/logout', { method: 'POST' });
  },

  // --- Incidents / Alerts ---------------------------------------------------
  // GET /incidents?status=unresolved
  fetchIncidents(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this._request(`/incidents${qs ? `?${qs}` : ''}`);
  },
  // PATCH /incidents/{id}/dismiss
  dismissIncident(incidentId) {
    return this._request(`/incidents/${incidentId}/dismiss`, { method: 'PATCH' });
  },

  // --- Cameras / AI Feed -----------------------------------------------------
  // GET /cameras -> [{ id, name, streamUrl, coords }]
  fetchCameras() {
    return this._request('/cameras');
  },
  // GET /analytics/threat-frequency?window=24h
  fetchThreatFrequency(windowParam = '24h') {
    return this._request(`/analytics/threat-frequency?window=${windowParam}`);
  },
  // GET /audit-log?scope=camera|global
  fetchAuditLog(scope = 'camera') {
    return this._request(`/audit-log?scope=${scope}`);
  },

  // --- Admin: Operator Management ---------------------------------------
  // GET /admin/operators
  fetchOperators() {
    return this._request('/admin/operators');
  },
  // POST /admin/operators  { userId, fullName, clearance, password }
  provisionUser(payload) {
    return this._request('/admin/operators', { method: 'POST', body: JSON.stringify(payload) });
  },
  // POST /admin/operators/{id}/force-logout
  forceLogoutUser(userId) {
    return this._request(`/admin/operators/${userId}/force-logout`, { method: 'POST' });
  },
  // DELETE /admin/operators/{id}
  deleteUser(userId) {
    return this._request(`/admin/operators/${userId}`, { method: 'DELETE' });
  },
};

/* ---------------------------------------------------------------------------
   3. AUTH STORE  (JWT persistence)
   --------------------------------------------------------------------------- */
const GarudaAuthStore = {
  setSession({ token, role, userId, fullName }) {
    localStorage.setItem(GarudaConfig.TOKEN_STORAGE_KEY, token || 'demo-token');
    localStorage.setItem(
      GarudaConfig.SESSION_STORAGE_KEY,
      JSON.stringify({ role, userId, fullName, issuedAt: Date.now() })
    );
  },
  getToken() {
    return localStorage.getItem(GarudaConfig.TOKEN_STORAGE_KEY);
  },
  getSession() {
    try {
      return JSON.parse(localStorage.getItem(GarudaConfig.SESSION_STORAGE_KEY)) || null;
    } catch {
      return null;
    }
  },
  clear() {
    localStorage.removeItem(GarudaConfig.TOKEN_STORAGE_KEY);
    localStorage.removeItem(GarudaConfig.SESSION_STORAGE_KEY);
  },
};

/* ---------------------------------------------------------------------------
   4. AUTH FLOWS  (login.html)
   --------------------------------------------------------------------------- */
const GarudaAuth = {
  async loadCaptcha(mode) {
    if (!GarudaConfig.BACKEND_ENABLED) return;
    try {
      const res = await fetch(`${GarudaConfig.API_BASE_URL}/auth/captcha/generate`);
      const data = await res.json();
      const captchaId = data.captcha_id;

      document.getElementById(`${mode}-captcha-id`).value = captchaId;
      document.getElementById(`${mode}-captcha-img`).src = `${GarudaConfig.API_BASE_URL}/auth/captcha/image/${captchaId}`;
      document.getElementById(`${mode}-captcha`).value = '';
    } catch (err) {
      console.error('Failed to load CAPTCHA', err);
    }
  },

  async handleLoginSubmit({ form, role, idField, passwordField, statusEl, submitBtn, redirectTo }) {
    const userIdInput = document.getElementById(idField);
    const passwordInput = document.getElementById(passwordField);

    // Dynamically get the captcha fields based on the role (operator or admin)
    const prefix = role === 'admin' ? 'admin' : 'operator';
    const captchaInput = document.getElementById(`${prefix}-captcha`);
    const captchaIdInput = document.getElementById(`${prefix}-captcha-id`);

    const userId = userIdInput.value.trim();
    const password = passwordInput.value;
    const captchaAnswer = captchaInput ? captchaInput.value.trim() : '';
    const captchaId = captchaIdInput ? captchaIdInput.value : '';

    // Clear previous errors
    form.querySelectorAll('.field__error').forEach((el) => el.classList.remove('is-visible'));

    let hasError = false;
    if (!userId) { form.querySelector(`[data-error-for="${idField}"]`)?.classList.add('is-visible'); hasError = true; }
    if (!password) { form.querySelector(`[data-error-for="${passwordField}"]`)?.classList.add('is-visible'); hasError = true; }
    if (!captchaAnswer) { form.querySelector(`[data-error-for="${prefix}-captcha"]`)?.classList.add('is-visible'); hasError = true; }
    if (hasError) return;

    submitBtn.disabled = true;
    statusEl.textContent = 'AUTHENTICATING WITH EDGE SERVER…';

    try {
      let session;
      if (GarudaConfig.BACKEND_ENABLED) {
        // Construct payload exactly matching your FastAPI LoginRequest BaseModel
        const payload = {
          username: userId,
          password: password,
          captcha_id: captchaId,
          captcha_answer: captchaAnswer
        };

        const res = await GarudaAPI.login(payload);

        // Store real user details returned by the FastAPI backend.
        session = {
          token: res.access_token,
          role: res.role || role,
          userId: userId,
          fullName: res.full_name || (role === 'admin' ? 'ADMIN ROOT' : 'OPERATOR')
        };
      } else {
        await new Promise((resolve) => setTimeout(resolve, 600));
        session = { token: 'demo-token', role, userId, fullName: role === 'admin' ? 'SUPERADMIN' : 'OPERATOR' };
      }

      GarudaAuthStore.setSession(session);
      statusEl.textContent = 'ACCESS GRANTED. REDIRECTING…';
      window.location.href = redirectTo;
    } catch (err) {
      statusEl.textContent = `ACCESS DENIED — ${err.message || 'Invalid credentials.'}`;
      submitBtn.disabled = false;
    }
  },

  async logout(redirectTo = 'login.html') {
    try {
      if (GarudaConfig.BACKEND_ENABLED) await GarudaAPI.logout();
    } catch {
      /* non-fatal: proceed with client-side logout regardless */
    } finally {
      GarudaAuthStore.clear();
      window.location.href = redirectTo;
    }
  },
};

/* ---------------------------------------------------------------------------
   5. ROUTE GUARD  (dashboard.html / admin.html)
   --------------------------------------------------------------------------- */
const GarudaGuard = {
  requireRole(expectedRole, redirectTo = 'login.html') {
    const session = GarudaAuthStore.getSession();
    if (!session || session.role !== expectedRole) {
      window.location.href = redirectTo;
      return null;
    }
    return session;
  },
};

/* ---------------------------------------------------------------------------
   6. REAL-TIME ALERT WEBSOCKET  (-> FastAPI /ws endpoint)
   --------------------------------------------------------------------------- */
const GarudaSocket = {
  _socket: null,
  _reconnectAttempts: 0,
  _onAlertCallback: null,

  connectAlertWebSocket(onAlert) {
    this._onAlertCallback = onAlert;

    if (!GarudaConfig.BACKEND_ENABLED) {
      // DEMO MODE: emit a synthetic alert periodically so the incident feed
      // and audit log feel alive without a live inference backend.
      this._startDemoAlertLoop();
      return;
    }

    const token = GarudaAuthStore.getToken();
    this._socket = new WebSocket(`${GarudaConfig.WS_BASE_URL}/alerts?token=${token}`);

    this._socket.addEventListener('open', () => {
      this._reconnectAttempts = 0;
      console.info('[GarudaSocket] connected to alert stream');
    });

    this._socket.addEventListener('message', (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // --- LISTEN FOR FORCE LOGOUT SIGNAL ---
        if (data.event === 'FORCE_LOGOUT') {
          alert('YOUR SESSION HAS BEEN TERMINATED BY AN ADMINISTRATOR.');
          GarudaAuthStore.clear();
          window.location.href = 'login.html';
          return;
        }

        this._onAlertCallback?.(data);
      } catch (err) {
        console.error('[GarudaSocket] malformed alert payload', err);
      }
    });

    this._socket.addEventListener('close', () => {
      const delay = Math.min(10000, 1000 * 2 ** this._reconnectAttempts);
      this._reconnectAttempts += 1;
      setTimeout(() => this.connectAlertWebSocket(onAlert), delay);
    });

    this._socket.addEventListener('error', (err) => {
      console.error('[GarudaSocket] socket error', err);
      this._socket.close();
    });
  },

  _startDemoAlertLoop() {
    const cameras = [
      { id: 'CAM-01', name: 'CHECKPOST SOUTH' },
      { id: 'CAM-02', name: 'WATCHTOWER NORTH' },
      { id: 'CAM-03', name: 'PATROL GATE 02' },
      { id: 'CAM-04', name: 'FORWARD OBS POST 09' },
    ];
    const entities = ['INTRUDER', 'UNIDENTIFIED VEHICLE', 'PERIMETER BREACH'];

    setInterval(() => {
      const cam = cameras[Math.floor(Math.random() * cameras.length)];
      const entity = entities[Math.floor(Math.random() * entities.length)];
      const confidence = (85 + Math.random() * 14).toFixed(1);
      const now = new Date();

      this._onAlertCallback?.({
        id: `INC-${Date.now()}`,
        title: `${entity} DETECTED`,
        time: now.toLocaleTimeString('en-IN', { hour12: false }) + ' IST',
        cameraId: cam.id,
        location: `${cam.id} · ${cam.name}`,
        confidence: `${confidence}%`,
      });
    }, 45000);
  },

  disconnect() {
    this._socket?.close();
    this._socket = null;
  },
};

/* ---------------------------------------------------------------------------
   7. CLIENT STATE
   --------------------------------------------------------------------------- */
const GarudaState = {
  incidents: [],
  unresolvedCount: 0,
};

/* ---------------------------------------------------------------------------
   8. TOAST HELPER
   --------------------------------------------------------------------------- */
const GarudaToast = {
  show(message, variant = 'default') {
    const stack = document.getElementById('toast-stack');
    if (!stack) return;
    const el = document.createElement('div');
    el.className = `toast ${variant === 'error' ? 'toast--error' : ''} ${variant === 'success' ? 'toast--success' : ''}`.trim();
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => el.remove(), 4200);
  },
};

/* ---------------------------------------------------------------------------
   9. DASHBOARD CONTROLLER  (dashboard.html)
   --------------------------------------------------------------------------- */
const GarudaDashboard = {
  init() {
    // Get the current session and reject only unauthenticated visitors.
    const session = GarudaAuthStore.getSession();
    if (!session) {
      window.location.href = 'login.html';
      return;
    }

    this._bindIdentity();
    this._bindGridLayout();
    this._bindVisionMode();
    this._bindIncidentDismiss();
    this._bindLogout();
    this._startClock();
    this._renderThreatChart();
    GarudaSocket.connectAlertWebSocket((alert) => this._prependIncident(alert));
  },

  _bindIdentity() {
    const session = GarudaAuthStore.getSession();
    if (!session) return;

    // Dynamic user name and ID.
    const nameEl = document.getElementById('user-name');
    const idEl = document.getElementById('user-id');
    if (nameEl && session.fullName) {
      nameEl.textContent = session.fullName.toUpperCase();
    }
    if (idEl && session.userId) idEl.textContent = session.userId;

    // Reveal admin navigation only for admin sessions.
    const adminNavGroup = document.getElementById('admin-nav-group');
    if (adminNavGroup && session.role === 'admin') {
      adminNavGroup.style.display = 'inline-flex';

      const adminConsoleBtn = document.getElementById('tab-admin-console');
      if (adminConsoleBtn) {
        adminConsoleBtn.addEventListener('click', () => {
          window.location.href = 'admin.html';
        });
      }
    }
  },

  _bindGridLayout() {
    const group = document.getElementById('grid-layout-group');
    const grid = document.getElementById('camera-grid');
    if (!group || !grid) return;
    group.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-layout]');
      if (!btn) return;
      group.querySelectorAll('button').forEach((b) => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      grid.dataset.layout = btn.dataset.layout;
    });
  },

  _bindVisionMode() {
    const group = document.getElementById('vision-mode-group');
    if (!group) return;
    group.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-vision]');
      if (!btn) return;
      group.querySelectorAll('button').forEach((b) => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      // CLAHE-style vision toggle is applied via CSS filters, see body[data-vision] rules
      document.body.dataset.vision = btn.dataset.vision;
    });
  },

  _bindIncidentDismiss() {
    const grid = document.getElementById('camera-grid');
    if (!grid) return;
    
    grid.addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-dismiss]');
      if (!btn) return;
      
      const row = btn.closest('.cam-incident-row');
      const cell = btn.closest('.camera-cell');
      const incidentId = row?.dataset.incidentId;
      const cameraId = cell?.dataset.camId;

      try {
        if (GarudaConfig.BACKEND_ENABLED && incidentId) {
          await GarudaAPI.dismissIncident(incidentId);
        }
        row.remove();
        if (cameraId) this._updateCameraBadge(cameraId, -1);
        GarudaToast.show('Incident dismissed.', 'success');
      } catch (err) {
        GarudaToast.show(`Could not dismiss incident: ${err.message}`, 'error');
      }
    });
  },

  _bindLogout() {
    document.getElementById('logout-btn')?.addEventListener('click', () => GarudaAuth.logout());
  },

  _startClock() {
    const tick = () => {
      const stamp = new Date().toLocaleTimeString('en-IN', { hour12: false }) + ' IST';
      document.querySelectorAll('[data-cam-clock]').forEach((el) => (el.textContent = stamp));
    };
    tick();
    setInterval(tick, 1000);
  },

  _prependIncident(alert) {
    const list = document.getElementById(`feed-${alert.cameraId}`);
    if (!list) return;

    // Remove "NO ACTIVE INCIDENTS" if present
    const emptyState = list.querySelector('.cam-incident-empty');
    if (emptyState) emptyState.remove();

    const row = document.createElement('div');
    row.className = 'cam-incident-row';
    row.dataset.incidentId = alert.id;
    row.innerHTML = `
      <span class="title"><span class="dot dot--alert"></span> ${alert.title.toUpperCase()}</span>
      <span class="meta">${alert.time} &nbsp;&nbsp; CONF: ${alert.confidence}</span>
      <button class="btn-dismiss" data-dismiss>DISMISS</button>
    `;
    list.prepend(row);
    this._updateCameraBadge(alert.cameraId, 1);
    GarudaToast.show(`New alert: ${alert.title} — ${alert.location}`);
  },

  _updateCameraBadge(cameraId, delta) {
    const badge = document.getElementById(`badge-${cameraId}`);
    if (!badge) return;
    const current = parseInt(badge.dataset.count, 10) || 0;
    const next = Math.max(0, current + delta);
    badge.dataset.count = next;
    badge.textContent = `${next} ACTIVE`;

    // Restore empty UI if zero
    if (next === 0) {
      const list = document.getElementById(`feed-${cameraId}`);
      if (list) list.innerHTML = `<div class="cam-incident-empty">NO ACTIVE INCIDENTS</div>`;
    }
  },

  _renderThreatChart() {
    const mount = document.getElementById('threat-chart');
    if (!mount) return;
    const data = [7, 9, 11, 9, 4, 3, 2, 1, 3, 5, 4, 6, 9];
    const w = 600, h = 150, pad = 8;
    const max = Math.max(...data);
    const stepX = (w - pad * 2) / (data.length - 1);
    const points = data
      .map((v, i) => `${pad + i * stepX},${h - pad - (v / max) * (h - pad * 2)}`)
      .join(' ');

    mount.innerHTML = `
      <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <polyline points="${points}" fill="none" stroke="#FFFFFF" stroke-width="2" />
      </svg>`;
  },
};

/* ---------------------------------------------------------------------------
   10. ADMIN CONTROLLER  (admin.html)
   --------------------------------------------------------------------------- */
const GarudaAdmin = {
  init() {
    const session = GarudaAuthStore.getSession();
    if (!session || session.role !== 'admin') {
      window.location.href = 'login.html';
      return;
    }

    this._bindIdentity();
    this._bindNavToggle();
    this._bindLogout();
    this._bindOperatorActions();
    this._bindProvisionModal();
    this._loadOperators();
  },

  async _loadOperators() {
    if (!GarudaConfig.BACKEND_ENABLED) return;
    try {
      const operators = await GarudaAPI.fetchOperators();
      const tbody = document.querySelector('#operator-table tbody');
      if (tbody) tbody.innerHTML = '';

      operators.forEach((operator) => {
        if (operator.role === 'admin') return;
        this._appendOperatorRow(operator);
      });
    } catch (err) {
      console.error('Failed to load operators:', err);
    }
  },

  _bindIdentity() {
    const session = GarudaAuthStore.getSession();
    if (!session) return;
    const nameEl = document.getElementById('admin-name');
    const idEl = document.getElementById('admin-id');
    if (nameEl && session.fullName) nameEl.textContent = session.fullName.toUpperCase();
    if (idEl && session.userId) idEl.textContent = session.userId;
  },

  _bindNavToggle() {
    document.getElementById('tab-launch-dashboard')?.addEventListener('click', () => {
      window.location.href = 'dashboard.html';
    });
  },

  _bindLogout() {
    document.getElementById('logout-btn')?.addEventListener('click', () => GarudaAuth.logout());
  },

  _bindOperatorActions() {
    const table = document.getElementById('operator-table');
    if (!table) return;

    table.addEventListener('click', async (e) => {
      const btn = e.target.closest('button[data-action]');
      if (!btn || btn.disabled) return;
      const row = btn.closest('tr');
      const userId = row.dataset.userId;

      if (btn.dataset.action === 'force-logout') {
        try {
          if (GarudaConfig.BACKEND_ENABLED) await GarudaAPI.forceLogoutUser(userId);
          row.dataset.status = 'offline';
          row.querySelector('.status-flag').className = 'status-flag status-flag--offline';
          row.querySelector('.status-flag').innerHTML = '<span class="dot dot--offline"></span>OFFLINE';
          row.querySelector('[data-action="force-logout"]').disabled = true;
          GarudaToast.show(`${userId} forced offline.`, 'success');
        } catch (err) {
          GarudaToast.show(`Force logout failed: ${err.message}`, 'error');
        }
      }

      if (btn.dataset.action === 'delete-account') {
        const confirmed = window.confirm(`Permanently delete operator ${userId}? This cannot be undone.`);
        if (!confirmed) return;
        try {
          if (GarudaConfig.BACKEND_ENABLED) await GarudaAPI.deleteUser(userId);
          row.remove();
          GarudaToast.show(`${userId} deleted.`, 'success');
        } catch (err) {
          GarudaToast.show(`Delete failed: ${err.message}`, 'error');
        }
      }
    });
  },

  _bindProvisionModal() {
    const overlay = document.getElementById('provision-modal');
    const openBtn = document.getElementById('open-provision-modal');
    const cancelBtn = document.getElementById('cancel-provision');
    const form = document.getElementById('provision-form');
    if (!overlay || !openBtn || !form) return;

    const open = () => overlay.classList.add('is-open');
    const close = () => { overlay.classList.remove('is-open'); form.reset(); };

    openBtn.addEventListener('click', open);
    cancelBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const clearanceVal = document.getElementById('new-clearance').value;
      const payload = {
        user_id: document.getElementById('new-user-id').value.trim(),
        full_name: document.getElementById('new-full-name').value.trim(),
        clearance_level: clearanceVal,
        password: document.getElementById('new-password').value,
        role: clearanceVal === 'ADMIN' ? 'admin' : 'user',
        status: 'offline',
      };
      if (!payload.user_id || !payload.full_name || !payload.password) return;

      try {
        if (GarudaConfig.BACKEND_ENABLED) {
          await GarudaAPI.provisionUser(payload);
        }
        this._appendOperatorRow(payload);
        GarudaToast.show(`Operator ${payload.user_id} provisioned.`, 'success');
        close();
      } catch (err) {
        GarudaToast.show(`Provisioning failed: ${err.message}`, 'error');
      }
    });
  },

  _appendOperatorRow({ user_id, full_name, clearance_level, status = 'offline' }) {
    const tbody = document.querySelector('#operator-table tbody');
    if (!tbody) return;
    const row = document.createElement('tr');
    row.dataset.userId = user_id;
    row.dataset.status = status;
    const statusHtml = status === 'online'
      ? '<span class="status-flag status-flag--online"><span class="dot dot--online"></span>ONLINE</span>'
      : '<span class="status-flag status-flag--offline"><span class="dot dot--offline"></span>OFFLINE</span>';

    row.innerHTML = `
      <td>${statusHtml}</td>
      <td class="is-primary">${user_id}</td>
      <td class="is-primary">${full_name.toUpperCase()}</td>
      <td>${clearance_level}</td>
      <td>
        <button type="button" class="btn-mini" data-action="force-logout" ${status === 'offline' ? 'disabled' : ''}>FORCE LOGOUT</button>
        <button type="button" class="btn-mini btn-mini--danger" data-action="delete-account">DELETE ACCOUNT</button>
      </td>`;
    tbody.appendChild(row);
  },
};
