/* ============================================================================
   GARUDA — Master Client Logic
   SIH PS 26187 — Team Nexus
   ============================================================================ */

const GarudaConfig = Object.freeze({
  API_BASE_URL: 'http://localhost:8000/api/v1',
  WS_BASE_URL: 'ws://localhost:8000/ws',
  TOKEN_STORAGE_KEY: 'garuda_auth_token',
  SESSION_STORAGE_KEY: 'garuda_session',
  BACKEND_ENABLED: true,
});

/* ---------------------------------------------------------------------------
   REST API WRAPPER
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
   AUTH STORE
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
   AUDIT LOG STORE (Max 100 entries)
   --------------------------------------------------------------------------- */
const GarudaAuditStore = {
  KEY: 'garuda_audit_logs',
  getLogs() {
    try {
      return JSON.parse(localStorage.getItem(this.KEY)) || [];
    } catch {
      return [];
    }
  },
  addLog(user, activity) {
    let logs = this.getLogs();
    const now = new Date();
    
    logs.unshift({
      date: now.toLocaleDateString('en-IN'),
      time: now.toLocaleTimeString('en-IN', { hour12: false }),
      user: user,
      activity: activity
    });

    if (logs.length > 100) {
      logs = logs.slice(0, 100); 
    }
    
    localStorage.setItem(this.KEY, JSON.stringify(logs));
  }
};

/* ---------------------------------------------------------------------------
   AUTH FLOWS
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
      GarudaAuditStore.addLog(userId, 'USER LOGGED IN');
      statusEl.textContent = 'ACCESS GRANTED. REDIRECTING…';
      window.location.href = redirectTo;
    } catch (err) {
      statusEl.textContent = `ACCESS DENIED — ${err.message || 'Invalid credentials.'}`;
      submitBtn.disabled = false;
      this.loadCaptcha(prefix);
    }
  },

  async logout(redirectTo = 'login.html') {
    const session = GarudaAuthStore.getSession();
    if (session) {
      GarudaAuditStore.addLog(session.userId, 'USER LOGGED OUT');
    }
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
   ROUTE GUARD
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
   REAL-TIME ALERT WEBSOCKET
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
   TOAST NOTIFICATIONS
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
   DASHBOARD CONTROLLER
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

    const isCriticalAudio = alert.title && (alert.title.includes('GUNSHOT') || alert.title.includes('EXPLOSION') || alert.siren);

    if (!isCriticalAudio && typeof GarudaCameraViewer !== 'undefined') {
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

    const rows = list.querySelectorAll('.incident-row');
    if (rows.length >= 200) {
      for (let i = 100; i < rows.length; i++) {
        rows[i].remove();
      }
    }

    if (badge) {
      const activeCount = list.querySelectorAll('.incident-row').length;
      badge.dataset.count = activeCount;
      badge.textContent = `${activeCount} ENTRIES`;
    }

    if (!alert.silent) {
      GarudaToast.show(`ALERT: ${alert.title} on ${alert.cameraId}`, alert.siren ? 'error' : 'default');
    }
  },
};

/* ---------------------------------------------------------------------------
   ADMIN CONTROLLER (OPERATORS, VAULT, AUDIT & FACE DETECTION BETA)
   --------------------------------------------------------------------------- */
const GarudaAdmin = {
  currentInspectingId: null,
  currentView: 'table',
  cachedIncidents: [],

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
    this._bindAuditModal();
    this._bindFaceModal();
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

  switchVaultView(mode) {
    this.currentView = mode;
    const tableBtn = document.getElementById('view-table-btn');
    const galleryBtn = document.getElementById('view-gallery-btn');
    const tableContainer = document.getElementById('dossier-table-container');
    const galleryGrid = document.getElementById('vault-grid');

    if (mode === 'table') {
      tableBtn?.classList.add('is-active');
      galleryBtn?.classList.remove('is-active');
      if (tableContainer) tableContainer.style.display = 'block';
      if (galleryGrid) galleryGrid.style.display = 'none';
    } else {
      galleryBtn?.classList.add('is-active');
      tableBtn?.classList.remove('is-active');
      if (tableContainer) tableContainer.style.display = 'none';
      if (galleryGrid) galleryGrid.style.display = 'grid';
    }
    this.renderDossier();
  },

  async loadEvidenceVault() {
    const tbody = document.getElementById('dossier-table-body');
    const grid = document.getElementById('vault-grid');
    if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #64748b; padding: 30px;">SEARCHING DATABASE FOR LOGS...</td></tr>';
    if (grid) grid.innerHTML = '<div style="grid-column: 1 / -1; padding: 30px; text-align: center; color: #64748b; font-family: var(--font-mono);">SEARCHING DATABASE FOR IMAGES...</div>';

    try {
      const res = await fetch(`${GarudaConfig.API_BASE_URL}/incidents/vault`);
      if (!res.ok) throw new Error("Could not load evidence vault");
      this.cachedIncidents = await res.json();
      this.renderDossier();
    } catch (err) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: #ef4444; padding: 30px;">FAILED TO LOAD DOSSIER: ${err.message}</td></tr>`;
      if (grid) grid.innerHTML = `<div style="grid-column: 1 / -1; padding: 30px; text-align: center; color: #ef4444; font-family: var(--font-mono);">FAILED TO LOAD EVIDENCE: ${err.message}</div>`;
    }
  },

  renderDossier() {
    const incidents = this.cachedIncidents;
    const tbody = document.getElementById('dossier-table-body');
    const grid = document.getElementById('vault-grid');

    if (!incidents || incidents.length === 0) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: rgba(255,255,255,0.3); padding: 35px;">NO THREAT BREACH INCIDENTS RECORDED IN DATABASE.</td></tr>';
      if (grid) grid.innerHTML = '<div style="grid-column: 1 / -1; padding: 40px; text-align: center; color: rgba(255,255,255,0.3); font-family: var(--font-mono);">NO EVIDENCE PHOTOS IN DATABASE.</div>';
      return;
    }

    if (tbody) {
      tbody.innerHTML = '';
      incidents.forEach((inc) => {
        const tr = document.createElement('tr');
        tr.dataset.incidentId = inc.id;

        let badgeClass = 'vault-badge--breach';
        if (inc.entity_type.includes('Group')) badgeClass = 'vault-badge--group';
        if (inc.entity_type.includes('Loiter')) badgeClass = 'vault-badge--loiter';

        const timestampStr = new Date(inc.timestamp).toLocaleString('en-IN', { hour12: false });
        const confPercent = (inc.confidence * 100).toFixed(1);

        tr.innerHTML = `
          <td>
            <img class="dossier-thumb" src="${inc.image_data}" alt="Evidence" onclick="GarudaAdmin.inspectImage('${inc.id}', '${inc.image_data}', '${inc.entity_type} (${inc.identifier})', '${inc.camera_id} · ${timestampStr}')" />
          </td>
          <td><span class="vault-badge ${badgeClass}">${inc.entity_type.toUpperCase()}</span></td>
          <td><strong style="color: #fff;">${inc.identifier || 'UNKNOWN'}</strong></td>
          <td><span style="color: #818cf8; font-weight: bold;">${inc.camera_id}</span></td>
          <td style="color: #94a3b8; font-size: 11px;">${timestampStr}</td>
          <td><span style="color: #4ade80;">${confPercent}%</span></td>
          <td>
            <button type="button" class="btn-mini" onclick="GarudaAdmin.inspectImage('${inc.id}', '${inc.image_data}', '${inc.entity_type} (${inc.identifier})', '${inc.camera_id} · ${timestampStr}')" style="margin-right: 6px; cursor: pointer;">INSPECT</button>
            <button type="button" class="btn-mini btn-mini--danger" onclick="GarudaAdmin.deleteBreachImage('${inc.id}')" style="cursor: pointer;">DELETE</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    if (grid) {
      grid.innerHTML = '';
      incidents.forEach((inc) => {
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
    const confirmed = window.confirm("Permanently delete this incident log & evidence image from the database?");
    if (!confirmed) return;

    try {
      if (GarudaConfig.BACKEND_ENABLED) {
        await GarudaAPI.deleteIncident(incidentId);
      }
      this.cachedIncidents = this.cachedIncidents.filter(i => i.id !== incidentId);
      document.querySelectorAll(`[data-incident-id="${incidentId}"]`).forEach(el => el.remove());
      GarudaToast.show("Incident record permanently removed from database.", "success");
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
          GarudaAuditStore.addLog(userId, 'FORCED OFFLINE BY ADMIN');
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
          GarudaAuditStore.addLog(userId, 'ACCOUNT DELETED BY ADMIN');
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
    const errorAlert = document.getElementById('provision-error-alert');
    const errorMsg = document.getElementById('provision-error-msg');

    if (!overlay || !openBtn || !form) return;

    openBtn.onclick = (e) => {
      e.preventDefault();
      if (errorAlert) errorAlert.style.display = 'none';
      overlay.classList.add('is-open');
    };

    if (cancelBtn) {
      cancelBtn.onclick = (e) => {
        e.preventDefault();
        overlay.classList.remove('is-open');
        if (errorAlert) errorAlert.style.display = 'none';
        form.reset();
      };
    }

    form.onsubmit = async (e) => {
      e.preventDefault();
      if (errorAlert) errorAlert.style.display = 'none';

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
        GarudaAuditStore.addLog(userIdVal, `PROVISIONED AS ${clearanceVal}`);
        GarudaToast.show(`Operator ${payload.user_id} provisioned.`, 'success');
        overlay.classList.remove('is-open');
        form.reset();
      } catch (err) {
        if (errorAlert && errorMsg) {
          errorMsg.textContent = err.message || `User ID '${userIdVal}' already exists!`;
          errorAlert.style.display = 'flex';
        }
        GarudaToast.show(`Provisioning failed: ${err.message}`, 'error');
      }
    };
  },

  _bindAuditModal() {
    const overlay = document.getElementById('audit-logs-modal');
    const openBtn = document.getElementById('open-audit-modal');
    const closeBtn = document.getElementById('close-audit-modal');

    if (!overlay || !openBtn) return;

    openBtn.onclick = (e) => {
      e.preventDefault();
      this._renderAuditLogs();
      overlay.classList.add('is-open');
    };

    if (closeBtn) {
      closeBtn.onclick = (e) => {
        e.preventDefault();
        overlay.classList.remove('is-open');
      };
    }
  },

  _renderAuditLogs() {
    const tbody = document.getElementById('audit-log-tbody');
    if (!tbody) return;

    const logs = GarudaAuditStore.getLogs();

    if (logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: rgba(255,255,255,0.3); padding: 30px;">NO AUDIT LOGS RECORDED.</td></tr>';
      return;
    }

    tbody.innerHTML = '';
    logs.forEach(log => {
      let activityColor = '#94a3b8';
      if (log.activity.includes('LOGGED IN')) activityColor = '#4ade80';
      if (log.activity.includes('LOGGED OUT')) activityColor = '#ef4444';
      if (log.activity.includes('PROVISIONED') || log.activity.includes('DELETED') || log.activity.includes('FORCED')) activityColor = '#f59e0b';

      tbody.innerHTML += `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.04);">
          <td style="padding: 10px 14px; color: #e2e8f0;">${log.date}</td>
          <td style="padding: 10px 14px; color: #94a3b8;">${log.time}</td>
          <td style="padding: 10px 14px; color: #818cf8; font-weight: bold;">${log.user}</td>
          <td style="padding: 10px 14px; color: ${activityColor}; font-weight: bold;">${log.activity}</td>
        </tr>
      `;
    });
  },

  _bindFaceModal() {
    const overlay = document.getElementById('face-detect-modal');
    const openBtn = document.getElementById('open-face-modal');
    const closeBtn = document.getElementById('close-face-modal');
    const tabUpload = document.getElementById('tab-face-upload');
    const tabCamera = document.getElementById('tab-face-camera');
    const uploadContainer = document.getElementById('face-upload-container');
    const cameraContainer = document.getElementById('face-camera-container');
    const fileInput = document.getElementById('face-file-input');
    const video = document.getElementById('face-webcam-video');
    const captureBtn = document.getElementById('btn-capture-face');
    const stopCamBtn = document.getElementById('btn-stop-cam');
    
    const resultsCard = document.getElementById('face-results-card');
    const resultPreview = document.getElementById('face-result-preview');
    const totalCountEl = document.getElementById('face-total-count');
    const identifiedCountEl = document.getElementById('face-identified-count');
    const unknownCountEl = document.getElementById('face-unknown-count');
    const rosterListEl = document.getElementById('face-roster-list');
    let localStream = null;

    if (!overlay || !openBtn) return;

    const stopWebcam = () => {
      if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
        localStream = null;
      }
    };

    openBtn.onclick = (e) => {
      e.preventDefault();
      overlay.classList.add('is-open');
    };

    closeBtn.onclick = (e) => {
      e.preventDefault();
      stopWebcam();
      overlay.classList.remove('is-open');
    };

    if (tabUpload && tabCamera) {
      tabUpload.onclick = () => {
        tabUpload.classList.add('is-active');
        tabCamera.classList.remove('is-active');
        uploadContainer.style.display = 'flex';
        cameraContainer.style.display = 'none';
        stopWebcam();
      };

      tabCamera.onclick = async () => {
        tabCamera.classList.add('is-active');
        tabUpload.classList.remove('is-active');
        uploadContainer.style.display = 'none';
        cameraContainer.style.display = 'flex';
        try {
          localStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
          video.srcObject = localStream;
        } catch (err) {
          GarudaToast.show('Webcam access denied or unavailable: ' + err.message, 'error');
        }
      };
    }

    if (stopCamBtn) stopCamBtn.onclick = () => stopWebcam();

      const processFaceImage = async (base64Img) => {
        GarudaToast.show('Running Neural Face Identification...', 'default');
        try {
          const res = await fetch(`${GarudaConfig.API_BASE_URL}/admin/face-detect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_base64: base64Img, threshold: 0.45 })
          });
          if (!res.ok) throw new Error('Face recognition API returned ' + res.status);
          const data = await res.json();

          if (resultsCard) resultsCard.style.display = 'block';
          if (resultPreview) resultPreview.src = data.annotated_image;
          
          // const totalFaces = data.faces ? data.faces.length : 0;
          // const identifiedFaces = data.faces ? data.faces.filter(f => f.name && f.name.toLowerCase() !== 'unknown') : [];
          // const unknownFacesCount = totalFaces - identifiedFaces.length;

          // if (totalCountEl) totalCountEl.textContent = totalFaces;
          // if (identifiedCountEl) identifiedCountEl.textContent = identifiedFaces.length;
          // if (unknownCountEl) unknownCountEl.textContent = unknownFacesCount;

          // if (rosterListEl) {
          //   rosterListEl.innerHTML = '';
          //   if (totalFaces === 0) {
          //     rosterListEl.innerHTML = '<span style="color: #64748b; font-size: 11px;">No faces detected in frame.</span>';
          //   } else {
          //     data.faces.forEach((face, idx) => {
          //       const isKnown = face.name && face.name.toLowerCase() !== 'unknown';
          //       const item = document.createElement('div');
          //       item.style.display = 'flex';
          //       item.style.justifyContent = 'space-between';
          //       item.style.alignItems = 'center';
          //       item.style.padding = '4px 8px';
          //       item.style.borderRadius = '3px';
          //       item.style.background = isKnown ? 'rgba(74, 222, 128, 0.08)' : 'rgba(239, 68, 68, 0.08)';
          //       item.style.border = isKnown ? '1px solid rgba(74, 222, 128, 0.2)' : '1px solid rgba(239, 68, 68, 0.2)';
          //       item.style.fontFamily = 'var(--font-mono)';

          //       item.innerHTML = `
          //         <div style="display: flex; align-items: center; gap: 6px;">
          //           <span style="color: ${isKnown ? '#4ade80' : '#f87171'}; font-weight: bold;">#${idx + 1}</span>
          //           <span style="color: #fff; font-weight: 600;">${face.name.toUpperCase()}</span>
          //         </div>
          //         <div style="color: #94a3b8; font-size: 10px;">
          //           Conf: <strong style="color: ${isKnown ? '#38bdf8' : '#94a3b8'};">${face.confidence}</strong> 
          //           ${face.similarity ? `(Sim: ${face.similarity})` : ''}
          //         </div>
          //       `;
          //       rosterListEl.appendChild(item);
          //     });
          //   }
          // }

          const totalFaces = data.faces ? data.faces.length : 0;
          const identifiedFaces = data.faces ? data.faces.filter(f => f.name && f.name.toLowerCase() !== 'unknown') : [];

          if (totalCountEl) totalCountEl.textContent = totalFaces;
          if (identifiedCountEl) identifiedCountEl.textContent = identifiedFaces.length;

          if (rosterListEl) {
            rosterListEl.innerHTML = '';
            if (totalFaces === 0) {
              rosterListEl.innerHTML = '<span style="color: #64748b; font-size: 11px;">No faces detected in frame.</span>';
            } else if (identifiedFaces.length === 0) {
              rosterListEl.innerHTML = '<span style="color: #d60606; font-size: 11px;">No registered persons identified (all unknown).</span>';
            } else {
              identifiedFaces.forEach((face, idx) => {
                const item = document.createElement('div');
                item.style.display = 'flex';
                item.style.justifyContent = 'space-between';
                item.style.alignItems = 'center';
                item.style.padding = '6px 10px';
                item.style.borderRadius = '4px';
                item.style.background = 'rgba(0, 0, 0, 0)';
                item.style.border = '1px solid rgba(0, 0, 0, 0)';
                item.style.fontFamily = 'var(--font-mono)';

                item.innerHTML = `
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="color: #ffffff; font-weight: bold; font-size: 12px;">${idx + 1}</span>
                    <span style="color: #ffffff; font-weight: 700; font-size: 12px; letter-spacing: 0.5px;">${face.name.toUpperCase()}</span>
                  </div>
                  <div style="display: flex; gap: 10px; font-size: 11px;">
                    <span style="color: #94a3b8;">CONF: <strong style="color: #38f868;">${face.confidence}</strong></span>
                    <span style="color: #94a3b8;">SIM: <strong style="color: #38f868;">${face.similarity || 'N/A'}</strong></span>
                  </div>
                `;
                rosterListEl.appendChild(item);
              });
            }
          }

          if (identifiedFaces.length > 0) {
            const names = identifiedFaces.map(f => f.name).join(', ');
            GarudaToast.show(`Identified ${identifiedFaces.length} of ${totalFaces} face(s): ${names}`, 'success');
          } else if (totalFaces > 0) {
            GarudaToast.show(`Detected ${totalFaces} face(s), but none matched enrolled roster.`, 'default');
          } else {
            GarudaToast.show('No faces detected in image.', 'default');
          }
        } catch (err) {
          GarudaToast.show('Face detection failed: ' + err.message, 'error');
        }
      };

    if (fileInput) {
      fileInput.onchange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (evt) => processFaceImage(evt.target.result);
        reader.readAsDataURL(file);
      };
    }

    if (captureBtn) {
      captureBtn.onclick = () => {
        if (!localStream) {
          GarudaToast.show('Camera stream not active', 'error');
          return;
        }
        const canvas = document.getElementById('face-capture-canvas');
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
        processFaceImage(dataUrl);
      };
    }
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
   DYNAMIC CAMERA ROTATION & NIGHT MODE
   --------------------------------------------------------------------------- */
const GarudaCameraViewer = {
  cameras: ['CAM-01', 'CAM-02', 'CAM-03', 'CAM-04', 'CAM-05'],
  cameraNames: {
    'CAM-01': 'CHECKPOST ANPR',
    'CAM-02': 'WATCHTOWER 01',
    'CAM-03': 'WATCHTOWER 02',
    'CAM-04': 'AUDIO-VISUAL THREAT STATION',
    'CAM-05': 'NIGHT VISION'
  },
  cameraCoords: {
    'CAM-01': '28.6139°N 77.2090°E',
    'CAM-02': '28.6200°N 77.2150°E',
    'CAM-03': '28.6100°N 77.2000°E',
    'CAM-04': '28.6050°N 77.1980°E',
    'CAM-05': '28.6000°N 77.1950°E'
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
    try {
      const res = await fetch(`${GarudaConfig.API_BASE_URL}/cameras/toggle-night-mode`, { method: 'POST' });
      const data = await res.json();
      this.nightModeStatus = data.status;
      this.nightModeEnabled = data.is_enabled;
      this._updateNightVisionUI();
      GarudaToast.show(`Night Vision: ${data.status}`, 'default');
    } catch (e) {
      console.error("Failed to toggle emergency night mode:", e);
    }
  },

  _updateNightVisionUI() {
    const btn = document.getElementById('night-vision-btn');
    const statusText = document.getElementById('night-mode-status');
    const currentCam = this.cameras[this.currentIndex];

    if (!btn) return;

    // Show button on all cameras except CAM-01
    if (currentCam === 'CAM-01') {
      btn.style.display = 'none';
      return;
    } else {
      btn.style.display = 'flex';
    }

    const label = this.nightModeStatus || 'AUTO';
    if (statusText) statusText.textContent = label;

    if (label === 'MANUAL ON') {
      btn.style.borderColor = '#22c55e';
      btn.style.background = 'rgba(20, 83, 45, 0.85)';
      btn.style.color = '#fff';
      if (statusText) statusText.style.color = '#4ade80';
    } else if (label === 'AUTO') {
      btn.style.borderColor = '#38bdf8';
      btn.style.background = 'rgba(14, 165, 233, 0.15)';
      btn.style.color = '#38bdf8';
      if (statusText) statusText.style.color = '#38bdf8';
    } else {
      // MANUAL OFF
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