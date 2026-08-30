/* ============================================================================
   GARUDA — Master Client Logic
   SIH PS 26187 — Team Nexus
   ----------------------------------------------------------------------------
   Modules:
     GarudaConfig      -> Endpoint & storage configuration
     GarudaAPI         -> REST API wrapper for FastAPI
     GarudaAuthStore   -> Session & JWT persistence
     GarudaAuth        -> Login / Logout workflows & CAPTCHA handling
     GarudaGuard       -> Role-based route guard
     GarudaSocket      -> WebSocket real-time alerts & Force-Logout listener
     GarudaToast       -> Military HUD notifications
     GarudaDashboard   -> Dashboard controller & telemetry metrics
     GarudaAdmin       -> Admin operator provisioning, session control & Evidence Vault
     GarudaCameraViewer-> Active camera switcher, Night-mode toggle (Hot-key: N)
   ============================================================================ */

/* ---------------------------------------------------------------------------
   1. CONFIG
   --------------------------------------------------------------------------- */
const GarudaConfig = Object.freeze({
  API_BASE_URL: 'http://localhost:8000/api/v1',
  WS_BASE_URL: 'ws://localhost:8000/ws',
  TOKEN_STORAGE_KEY: 'garuda_auth_token',
  SESSION_STORAGE_KEY: 'garuda_session',
  BACKEND_ENABLED: true,
});

/* ---------------------------------------------------------------------------
   2. REST API WRAPPER
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

  login(payload) {
    return this._request('/auth/login', { method: 'POST', body: JSON.stringify(payload) });
  },
  logout() {
    return this._request('/auth/logout', { method: 'POST' });
  },
  fetchIncidents(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this._request(`/incidents${qs ? `?${qs}` : ''}`);
  },
  fetchEvidenceVault() {
    return this._request('/incidents/vault');
  },
  deleteIncident(incidentId) {
    return this._request(`/incidents/${incidentId}`, { method: 'DELETE' });
  },
  dismissIncident(incidentId) {
    return this._request(`/incidents/${incidentId}/dismiss`, { method: 'PATCH' });
  },
  fetchCameras() {
    return this._request('/cameras');
  },
  fetchOperators() {
    return this._request('/admin/operators');
  },
  provisionUser(payload) {
    return this._request('/admin/operators', { method: 'POST', body: JSON.stringify(payload) });
  },
  forceLogoutUser(userId) {
    return this._request(`/admin/operators/${userId}/force-logout`, { method: 'POST' });
  },
  deleteUser(userId) {
    return this._request(`/admin/operators/${userId}`, { method: 'DELETE' });
  },
};

/* ---------------------------------------------------------------------------
   3. AUTH STORE
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
   4. AUTH FLOWS
   --------------------------------------------------------------------------- */
const GarudaAuth = {
  async loadCaptcha(mode) {
    if (!GarudaConfig.BACKEND_ENABLED) return;
    try {
      const res = await fetch(`${GarudaConfig.API_BASE_URL}/auth/captcha/generate`);
      const data = await res.json();
      const captchaId = data.captcha_id;

      const idField = document.getElementById(`${mode}-captcha-id`);
      const imgField = document.getElementById(`${mode}-captcha-img`);
      const valField = document.getElementById(`${mode}-captcha`);

      if (idField) idField.value = captchaId;
      if (imgField) imgField.src = `${GarudaConfig.API_BASE_URL}/auth/captcha/image/${captchaId}`;
      if (valField) valField.value = '';
    } catch (err) {
      console.error('Failed to load CAPTCHA', err);
    }
  },

  async handleLoginSubmit({ form, role, idField, passwordField, statusEl, submitBtn, redirectTo }) {
    const userIdInput = document.getElementById(idField);
    const passwordInput = document.getElementById(passwordField);

    const prefix = role === 'admin' ? 'admin' : 'operator';
    const captchaInput = document.getElementById(`${prefix}-captcha`);
    const captchaIdInput = document.getElementById(`${prefix}-captcha-id`);

    const userId = userIdInput.value.trim();
    const password = passwordInput.value;
    const captchaAnswer = captchaInput ? captchaInput.value.trim() : '';
    const captchaId = captchaIdInput ? captchaIdInput.value : '';

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
        const payload = {
          username: userId,
          password: password,
          captcha_id: captchaId,
          captcha_answer: captchaAnswer
        };

        const res = await GarudaAPI.login(payload);
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
      this.loadCaptcha(prefix);
    }
  },

  async logout(redirectTo = 'login.html') {
    try {
      if (GarudaConfig.BACKEND_ENABLED) await GarudaAPI.logout();
    } catch {
    } finally {
      GarudaAuthStore.clear();
      window.location.href = redirectTo;
    }
  },
};

/* ---------------------------------------------------------------------------
   5. ROUTE GUARD
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
   6. REAL-TIME ALERT WEBSOCKET
   --------------------------------------------------------------------------- */
const GarudaSocket = {
  _socket: null,
  _reconnectAttempts: 0,
  _onAlertCallback: null,

  connectAlertWebSocket(onAlert) {
    this._onAlertCallback = onAlert;
    if (!GarudaConfig.BACKEND_ENABLED) return;

    const token = GarudaAuthStore.getToken();
    this._socket = new WebSocket(`${GarudaConfig.WS_BASE_URL}/alerts?token=${token}`);

    this._socket.addEventListener('open', () => {
      this._reconnectAttempts = 0;
      console.info('[GarudaSocket] Connected to tactical alert stream');
    });

    this._socket.addEventListener('message', (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.event === 'FORCE_LOGOUT') {
          alert('YOUR SESSION HAS BEEN TERMINATED BY AN ADMINISTRATOR.');
          GarudaAuthStore.clear();
          window.location.href = 'login.html';
          return;
        }
        this._onAlertCallback?.(data);
      } catch (err) {
        console.error('[GarudaSocket] Malformed alert payload', err);
      }
    });

    this._socket.addEventListener('close', () => {
      const delay = Math.min(10000, 1000 * 2 ** this._reconnectAttempts);
      this._reconnectAttempts += 1;
      setTimeout(() => this.connectAlertWebSocket(onAlert), delay);
    });

    this._socket.addEventListener('error', () => {
      this._socket?.close();
    });
  },

  disconnect() {
    this._socket?.close();
    this._socket = null;
  },
};

/* ---------------------------------------------------------------------------
   7. TOAST NOTIFICATIONS
   --------------------------------------------------------------------------- */
const GarudaToast = {
  show(message, variant = 'default') {
    const stack = document.getElementById('toast-stack');
    if (!stack) return;
    const el = document.createElement('div');
    el.className = `toast ${variant === 'error' ? 'toast--error' : ''} ${variant === 'success' ? 'toast--success' : ''}`.trim();
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  },
};

/* ---------------------------------------------------------------------------
   8. DASHBOARD CONTROLLER
   --------------------------------------------------------------------------- */
const GarudaDashboard = {
  init() {
    const session = GarudaAuthStore.getSession();
    if (!session) {
      window.location.href = 'login.html';
      return;
    }

    this._bindIdentity();
    this._bindLogout();
    this._startClock();
    GarudaSocket.connectAlertWebSocket((alert) => this._prependIncident(alert));
  },

  _bindIdentity() {
    const session = GarudaAuthStore.getSession();
    if (!session) return;

    const nameEl = document.getElementById('user-name');
    const idEl = document.getElementById('user-id');
    if (nameEl && session.fullName) nameEl.textContent = session.fullName.toUpperCase();
    if (idEl && session.userId) idEl.textContent = session.userId;

    const adminNavGroup = document.getElementById('admin-nav-group');
    if (adminNavGroup && session.role === 'admin') {
      adminNavGroup.style.display = 'inline-flex';
      document.getElementById('tab-admin-console')?.addEventListener('click', () => {
        window.location.href = 'admin.html';
      });
    }
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
    const list = document.getElementById('active-incident-list');
    const badge = document.getElementById('active-incident-count');

    if (typeof GarudaCameraViewer !== 'undefined') {
      const currentCam = GarudaCameraViewer.cameras[GarudaCameraViewer.currentIndex];
      if (alert.cameraId && alert.cameraId !== currentCam) {
        return;
      }
    }

    if (!list) return;
    const emptyState = list.querySelector('.incident-empty');
    if (emptyState) emptyState.remove();

    const row = document.createElement('div');
    row.className = 'incident-row';
    row.dataset.incidentId = alert.id;
    row.innerHTML = `
      <span class="title"><span class="dot dot--alert"></span> ${alert.title.toUpperCase()}</span>
      <span class="meta">${alert.time} &nbsp;|&nbsp; CONF: ${alert.confidence}</span>
      <button class="btn-mini" onclick="this.closest('.incident-row').remove()">DISMISS</button>
    `;
    list.prepend(row);

    if (badge) {
      const current = parseInt(badge.dataset.count, 10) || 0;
      badge.dataset.count = current + 1;
      badge.textContent = `${current + 1} ENTRIES`;
    }

    if (!alert.silent) {
      GarudaToast.show(`ALERT: ${alert.title} on ${alert.cameraId}`, alert.siren ? 'error' : 'default');
    }
  },
};

/* ---------------------------------------------------------------------------
   9. ADMIN CONTROLLER (OPERATORS + EVIDENCE VAULT WITH DELETION)
   --------------------------------------------------------------------------- */
const GarudaAdmin = {
  currentInspectingId: null,

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
    this.loadEvidenceVault();
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

  async loadEvidenceVault() {
    const grid = document.getElementById('vault-grid');
    if (!grid) return;
    grid.innerHTML = '<div style="grid-column: 1 / -1; padding: 30px; text-align: center; color: #64748b; font-family: var(--font-mono);">QUERYING DATABASE EVIDENCE PHOTOS...</div>';

    try {
      const res = await fetch(`${GarudaConfig.API_BASE_URL}/incidents/vault`);
      if (!res.ok) throw new Error("Could not load evidence vault");
      const incidents = await res.json();

      if (!incidents || incidents.length === 0) {
        grid.innerHTML = '<div style="grid-column: 1 / -1; padding: 40px; text-align: center; color: rgba(255,255,255,0.3); font-family: var(--font-mono);">NO EVIDENCE PHOTOS IN DATABASE YET.</div>';
        return;
      }

      grid.innerHTML = '';
      incidents.forEach((inc) => {
        if (!inc.image_data) return;

        const card = document.createElement('div');
        card.className = 'vault-card';
        card.dataset.incidentId = inc.id;

        let badgeClass = 'vault-badge--breach';
        if (inc.entity_type.includes('Group')) badgeClass = 'vault-badge--group';
        if (inc.entity_type.includes('Loiter')) badgeClass = 'vault-badge--loiter';

        const timestampStr = new Date(inc.timestamp).toLocaleString('en-IN', { hour12: false });

        card.innerHTML = `
          <div class="vault-img-wrap" onclick="GarudaAdmin.inspectImage('${inc.id}', '${inc.image_data}', '${inc.entity_type} (${inc.identifier})', '${inc.camera_id} · ${timestampStr}')">
            <img src="${inc.image_data}" alt="${inc.entity_type}" loading="lazy" />
          </div>
          <div class="vault-meta">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span class="vault-badge ${badgeClass}">${inc.entity_type.toUpperCase()}</span>
              <span style="color: #94a3b8;">${inc.camera_id}</span>
            </div>
            <strong style="color: #fff; font-size: 12px; margin-top: 4px;">${inc.identifier || 'UNKNOWN'}</strong>
            <span style="color: #64748b; font-size: 10px;">${timestampStr} | CONF: ${(inc.confidence * 100).toFixed(0)}%</span>
            <div class="vault-actions">
              <button type="button" class="btn-mini" onclick="GarudaAdmin.inspectImage('${inc.id}', '${inc.image_data}', '${inc.entity_type} (${inc.identifier})', '${inc.camera_id} · ${timestampStr}')" style="background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: #fff; cursor: pointer;">INSPECT</button>
              <button type="button" class="btn-mini btn-mini--danger" onclick="GarudaAdmin.deleteBreachImage('${inc.id}')" style="background: rgba(239,68,68,0.2); border: 1px solid #ef4444; color: #ef4444; cursor: pointer;">DELETE</button>
            </div>
          </div>
        `;
        grid.appendChild(card);
      });

    } catch (err) {
      grid.innerHTML = `<div style="grid-column: 1 / -1; padding: 30px; text-align: center; color: #ef4444; font-family: var(--font-mono);">FAILED TO LOAD EVIDENCE: ${err.message}</div>`;
    }
  },

  inspectImage(incidentId, imageData, title, meta) {
    this.currentInspectingId = incidentId;
    const modal = document.getElementById('image-inspect-modal');
    const img = document.getElementById('modal-image-src');
    const titleEl = document.getElementById('modal-image-title');
    const metaEl = document.getElementById('modal-image-meta');
    const delBtn = document.getElementById('modal-delete-btn');
    if (!modal || !img) return;

    img.src = imageData;
    if (titleEl) titleEl.textContent = title;
    if (metaEl) metaEl.textContent = `CAMERA: ${meta}`;
    if (delBtn) {
      delBtn.onclick = () => {
        this.deleteBreachImage(incidentId);
        modal.classList.remove('is-open');
      };
    }
    modal.classList.add('is-open');
  },

  async deleteBreachImage(incidentId) {
    const confirmed = window.confirm("Are you sure you want to delete this breach record & image permanently from the database?");
    if (!confirmed) return;

    try {
      if (GarudaConfig.BACKEND_ENABLED) {
        await GarudaAPI.deleteIncident(incidentId);
      }
      document.querySelector(`.vault-card[data-incident-id="${incidentId}"]`)?.remove();
      GarudaToast.show("Breach record permanently deleted from database.", "success");
    } catch (err) {
      GarudaToast.show(`Delete failed: ${err.message}`, "error");
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
          btn.disabled = true;
          GarudaToast.show(`${userId} forced offline.`, 'success');
        } catch (err) {
          GarudaToast.show(`Force logout failed: ${err.message}`, 'error');
        }
      }

      if (btn.dataset.action === 'delete-account') {
        const confirmed = window.confirm(`Permanently delete operator ${userId}?`);
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

    if (!overlay || !openBtn || !form) {
      console.warn('[GarudaAdmin] Provision modal elements not found');
      return;
    }

    openBtn.onclick = (e) => {
      e.preventDefault();
      overlay.classList.add('is-open');
    };

    if (cancelBtn) {
      cancelBtn.onclick = (e) => {
        e.preventDefault();
        overlay.classList.remove('is-open');
        form.reset();
      };
    }

    form.onsubmit = async (e) => {
      e.preventDefault();
      const clearanceVal = document.getElementById('new-clearance').value;
      const userIdVal = document.getElementById('new-user-id').value.trim();
      const fullNameVal = document.getElementById('new-full-name').value.trim();
      const passwordVal = document.getElementById('new-password').value;

      const payload = {
        user_id: userIdVal,
        full_name: fullNameVal,
        clearance_level: clearanceVal,
        password: passwordVal,
        role: clearanceVal.toLowerCase().includes('admin') ? 'admin' : 'user',
        status: 'offline',
      };

      try {
        if (GarudaConfig.BACKEND_ENABLED) {
          await GarudaAPI.provisionUser(payload);
        }
        this._appendOperatorRow(payload);
        GarudaToast.show(`Operator ${payload.user_id} provisioned.`, 'success');
        overlay.classList.remove('is-open');
        form.reset();
      } catch (err) {
        GarudaToast.show(`Provisioning failed: ${err.message}`, 'error');
      }
    };
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
      <td style="padding: 10px 14px;">${statusHtml}</td>
      <td style="padding: 10px 14px; color: #fff; font-weight: bold;">${user_id}</td>
      <td style="padding: 10px 14px; color: #818cf8;">${full_name.toUpperCase()}</td>
      <td style="padding: 10px 14px; color: #94a3b8;">${clearance_level}</td>
      <td style="padding: 10px 14px;">
        <button type="button" class="btn-mini" data-action="force-logout" ${status === 'offline' ? 'disabled' : ''} style="margin-right: 6px;">FORCE LOGOUT</button>
        <button type="button" class="btn-mini btn-mini--danger" data-action="delete-account">DELETE ACCOUNT</button>
      </td>`;
    tbody.appendChild(row);
  },
};

/* ---------------------------------------------------------------------------
   10. DYNAMIC CAMERA ROTATION & NIGHT MODE (HOT-KEY: 'N')
   --------------------------------------------------------------------------- */
const GarudaCameraViewer = {
  cameras: ['CAM-01', 'CAM-02', 'CAM-03', 'CAM-04'],
  cameraNames: {
    'CAM-01': 'CHECKPOST ANPR SECTOR',
    'CAM-02': 'WATCHTOWER NORTH PERIMETER',
    'CAM-03': 'PATROL GATE 02',
    'CAM-04': 'FORWARD OBS POST 09'
  },
  cameraCoords: {
    'CAM-01': '28.6139°N 77.2090°E',
    'CAM-02': '28.6200°N 77.2150°E',
    'CAM-03': '28.6100°N 77.2000°E',
    'CAM-04': '28.6050°N 77.1980°E'
  },
  currentIndex: 0,
  nightModeEnabled: false,

  async init() {
    try {
      const res = await fetch(`${GarudaConfig.API_BASE_URL}/cameras/list`);
      if (res.ok) {
        const camList = await res.json();
        if (camList && camList.length > 0) {
          this.cameras = camList.map(c => c.id);
        }
      }
    } catch {
      console.warn("Using default camera list:", this.cameras);
    }

    this._renderIndicators();
    this._bindControls();
    this.switchCamera(0);
  },

  _renderIndicators() {
    const container = document.getElementById('cam-selector-tray') || document.getElementById('cam-indicators');
    if (!container) return;
    container.innerHTML = '';

    this.cameras.forEach((camId, idx) => {
      const chip = document.createElement('button');
      chip.className = `cam-chip ${idx === this.currentIndex ? 'is-active' : ''}`;
      chip.dataset.cam = camId;
      chip.textContent = camId;
      chip.addEventListener('click', (e) => {
        e.preventDefault();
        this.switchCamera(idx);
      });
      container.appendChild(chip);
    });
  },

  async toggleNightVision() {
    const currentCam = this.cameras[this.currentIndex];
    if (currentCam === 'CAM-01') {
      GarudaToast.show('Night Vision CLAHE is active on Watchtower cameras only.', 'default');
      return;
    }

    try {
      const res = await fetch(`${GarudaConfig.API_BASE_URL}/cameras/toggle-night-mode`, { method: 'POST' });
      const data = await res.json();
      this.nightModeStatus = data.status;
      this.nightModeEnabled = data.is_enabled;
      this._updateNightVisionUI();
      GarudaToast.show(`Emergency Override: Night Vision ${data.status}`, this.nightModeEnabled ? 'success' : 'default');
    } catch (e) {
      console.error("Failed to toggle emergency night mode:", e);
    }
  },

  _updateNightVisionUI() {
    const btn = document.getElementById('night-vision-btn');
    const statusText = document.getElementById('night-mode-status');
    const currentCam = this.cameras[this.currentIndex];

    if (!btn) return;

    if (currentCam === 'CAM-01') {
      btn.style.display = 'none';
      return;
    } else {
      btn.style.display = 'flex';
    }

    const label = this.nightModeStatus || 'AUTO';
    if (statusText) statusText.textContent = label;

    if (this.nightModeEnabled) {
      btn.style.borderColor = '#22c55e';
      btn.style.background = 'rgba(20, 83, 45, 0.85)';
      btn.style.color = '#fff';
      if (statusText) statusText.style.color = '#4ade80';
    } else {
      btn.style.borderColor = 'rgba(255,255,255,0.25)';
      btn.style.background = 'rgba(5,8,17,0.85)';
      btn.style.color = '#94a3b8';
      if (statusText) statusText.style.color = '#64748b';
    }
  },

  switchCamera(index) {
    if (index < 0) index = this.cameras.length - 1;
    if (index >= this.cameras.length) index = 0;
    this.currentIndex = index;

    const camId = this.cameras[this.currentIndex];
    const streamImg = document.getElementById('active-camera-stream');
    const overlay = document.getElementById('no-network-overlay');
    const titleEl = document.getElementById('active-cam-title');
    const headerEl = document.getElementById('active-incident-heading') || document.getElementById('active-incident-header');
    const coordsEl = document.getElementById('active-cam-coords');

    if (overlay) overlay.style.display = 'none';

    fetch(`${GarudaConfig.API_BASE_URL}/cameras/silence`, { method: 'POST' }).catch(() => {});

    if (streamImg) {
      streamImg.src = `${GarudaConfig.API_BASE_URL}/cameras/${camId}/stream?t=${Date.now()}`;
    }

    const camName = this.cameraNames[camId] || `STATION ${camId}`;
    if (titleEl) titleEl.textContent = `${camId}: ${camName}`;
    if (headerEl) headerEl.textContent = `${camId} · SURVEILLANCE & THREAT TELEMETRY LOG`;
    if (coordsEl && this.cameraCoords[camId]) coordsEl.textContent = this.cameraCoords[camId];

    const incidentList = document.getElementById('active-incident-list');
    const incidentCount = document.getElementById('active-incident-count');
    if (incidentList) {
      incidentList.innerHTML = '<div class="incident-empty">LOG CLEAR — SYSTEM SCANNING ACTIVE SECTOR</div>';
    }
    if (incidentCount) {
      incidentCount.dataset.count = '0';
      incidentCount.textContent = '0 ENTRIES';
    }

    const container = document.getElementById('cam-selector-tray') || document.getElementById('cam-indicators');
    if (container) {
      const chips = container.querySelectorAll('.cam-chip, button');
      chips.forEach((c, i) => {
        if (i === index) c.classList.add('is-active');
        else c.classList.remove('is-active');
      });
    }

    this._updateNightVisionUI();
    console.info(`[GarudaViewer] Switched active camera to ${camId}`);
  },

  _bindControls() {
    const prevBtn = document.getElementById('cam-prev-btn');
    const nextBtn = document.getElementById('cam-next-btn');
    const nightBtn = document.getElementById('night-vision-btn');

    if (prevBtn) prevBtn.onclick = (e) => { e.preventDefault(); this.switchCamera(this.currentIndex - 1); };
    if (nextBtn) nextBtn.onclick = (e) => { e.preventDefault(); this.switchCamera(this.currentIndex + 1); };
    if (nightBtn) nightBtn.onclick = (e) => { e.preventDefault(); this.toggleNightVision(); };

    window.addEventListener('keydown', (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;

      if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        this.toggleNightVision();
      }
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        this.switchCamera(this.currentIndex - 1);
      }
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        this.switchCamera(this.currentIndex + 1);
      }
    });
  }
};