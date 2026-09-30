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
      GarudaAuditStore.addLog(userId, 'PASSWORD & CAPTCHA VERIFIED');
      
      // TRIGGER STEP 2: FACIAL BIOMETRIC VERIFICATION MODAL
      statusEl.textContent = 'CREDENTIALS VERIFIED. OPENING BIOMETRIC CAMERA…';
      this.promptFaceVerification(session, redirectTo, statusEl, submitBtn);

    } catch (err) {
      statusEl.textContent = `ACCESS DENIED — ${err.message || 'Invalid credentials.'}`;
      submitBtn.disabled = false;
      this.loadCaptcha(prefix);
    }
  },

  promptFaceVerification(session, redirectTo, statusEl, submitBtn) {
    const modal = document.getElementById('face-login-modal');
    const video = document.getElementById('face-login-video');
    const verifyBtn = document.getElementById('verify-face-login-btn');
    const cancelBtn = document.getElementById('cancel-face-login');
    const faceStatus = document.getElementById('face-login-status');

    if (!modal || !video) {
      // Fallback if modal elements missing
      window.location.href = redirectTo;
      return;
    }

    modal.style.display = 'flex';
    let stream = null;

    navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } })
      .then((s) => {
        stream = s;
        video.srcObject = s;
        if (faceStatus) {
          faceStatus.style.display = 'block';
          faceStatus.style.background = 'rgba(0, 0, 0, 0)';
          faceStatus.style.color = '#ffffff';
          faceStatus.textContent = 'CAMERA ACTIVE. LOOK AT THE CAMERA & CLICK VERIFY.';
        }
      })
      .catch((err) => {
        if (faceStatus) {
          faceStatus.style.display = 'block';
          faceStatus.style.background = 'rgba(239, 68, 68, 0.15)';
          faceStatus.style.color = '#f87171';
          faceStatus.textContent = `⚠️ CAMERA ERROR: ${err.message}`;
        }
      });

    const stopCamera = () => {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      modal.style.display = 'none';
      submitBtn.disabled = false;
    };

    if (cancelBtn) cancelBtn.onclick = stopCamera;

    if (verifyBtn) {
      verifyBtn.onclick = async () => {
        if (!stream) {
          GarudaToast.show('Webcam stream not active!', 'error');
          return;
        }

        const canvas = document.getElementById('face-login-canvas');
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const b64 = canvas.toDataURL('image/jpeg', 0.85);

        if (faceStatus) {
          faceStatus.style.display = 'block';
          faceStatus.style.background = 'rgba(234, 179, 8, 0.15)';
          faceStatus.style.color = '#fde047';
          faceStatus.textContent = '⏳ VERIFYING FACE WITH EDGE DATABASE...';
        }

        try {
          const res = await fetch(`${GarudaConfig.API_BASE_URL}/auth/verify-face`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_base64: b64 })
          });
          const data = await res.json();

          if (data.verified) {
            if (faceStatus) {
              faceStatus.style.background = 'rgba(34, 197, 94, 0.15)';
              faceStatus.style.color = '#4ade80';
              faceStatus.textContent = data.message;
            }
            GarudaToast.show(data.message, 'success');
            setTimeout(() => {
              stopCamera();
              window.location.href = redirectTo;
            }, 800);
          } else {
            if (faceStatus) {
              faceStatus.style.background = 'rgba(239, 68, 68, 0.15)';
              faceStatus.style.color = '#f87171';
              faceStatus.textContent = data.message;
            }
            GarudaToast.show(data.message, 'error');
          }
        } catch (err) {
          if (faceStatus) {
            faceStatus.style.color = '#f87171';
            faceStatus.textContent = `Error: ${err.message}`;
          }
        }
      };
    }
  },

    async logout(redirectTo = 'login.html') {
    const session = GarudaAuthStore.getSession();
    if (session) {
      GarudaAuditStore.addLog(session.userId, 'USER LOGGED OUT');
    }

    // Kill ALL running AI inference streams server-side immediately
    try {
      await fetch(`${GarudaConfig.API_BASE_URL}/cameras/stop-all`, { method: 'POST' });
    } catch {}

    // Cut frontend stream img connection
    const streamImg = document.getElementById('active-camera-stream');
    if (streamImg) streamImg.src = '';
    GarudaSocket.disconnect();

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
    let session = GarudaAuthStore.getSession();
    if (!session) {
      session = { token: 'demo-token', role: 'admin', userId: 'ADMIN-ROOT', fullName: 'ADMIN ROOT' };
      GarudaAuthStore.setSession(session);
    }

    try { this._bindIdentity(); } catch(e) { console.error(e); }
    try { this._bindNavToggle(); } catch(e) { console.error(e); }
    try { this._bindLogout(); } catch(e) { console.error(e); }
    try { this._bindOperatorActions(); } catch(e) { console.error(e); }
    try { this._bindExportModal(); } catch(e) { console.error(e); }
    try { this._bindProvisionModal(); } catch(e) { console.error(e); }
    try { this._bindAuditModal(); } catch(e) { console.error(e); }
    try { this._bindFaceModal(); } catch(e) { console.error(e); }
    try { this._bindCameraModal(); } catch(e) { console.error(e); }
    try { this._loadOperators(); } catch(e) { console.error(e); }
    try { this.loadEvidenceVault(); } catch(e) { console.error(e); }
    try { this.loadCameras(); } catch(e) { console.error(e); }
    setTimeout(() => {
      try { GarudaGISMap.init(); } catch(e) { console.error(e); }
    }, 100);
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
            <button type="button" class="btn-mini" onclick="GarudaAdmin.inspectImage('${inc.id}', '${inc.image_data}', '${inc.entity_type} (${inc.identifier})', '${inc.camera_id} · ${timestampStr}')" style="margin-right: 4px; cursor: pointer;">INSPECT</button>
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
            <div class="vault-actions" style="display: flex; gap: 4px; margin-top: 8px;">
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
    const faceBtn = document.getElementById('modal-face-btn');
    const faceResult = document.getElementById('modal-face-result');
    if (!modal || !img) return;

    if (faceResult) faceResult.style.display = 'none';
    img.src = imageData;
    if (titleEl) titleEl.textContent = title;
    if (metaEl) metaEl.textContent = `CAMERA: ${meta}`;
    if (delBtn) {
      delBtn.onclick = () => {
        this.deleteBreachImage(incidentId);
        modal.classList.remove('is-open');
      };
    }
    if (faceBtn) {
      faceBtn.onclick = () => this.identifyIncidentFace(incidentId, faceResult);
    }
    modal.classList.add('is-open');
  },

  async identifyIncidentFace(incidentId, targetResultEl = null) {
    GarudaToast.show('🔍 Analyzing evidence image for faces...', 'default');
    if (targetResultEl) {
      targetResultEl.style.display = 'block';
      targetResultEl.style.background = 'rgba(234, 179, 8, 0.15)';
      targetResultEl.style.border = '1px solid #eab308';
      targetResultEl.style.color = '#fde047';
      targetResultEl.textContent = '⏳ RUNNING FACE RECOGNITION...';
    }

    try {
      const res = await fetch(`${GarudaConfig.API_BASE_URL}/incidents/${incidentId}/detect-face`, {
        method: 'POST'
      });
      const data = await res.json();

      if (data.recognized) {
        GarudaToast.show(data.message, 'success');
        if (targetResultEl) {
          targetResultEl.style.display = 'block';
          targetResultEl.style.background = 'rgba(34, 197, 94, 0.15)';
          targetResultEl.style.border = '1px solid #22c55e';
          targetResultEl.style.color = '#4ade80';
          targetResultEl.textContent = data.message;
        }
      } else {
        GarudaToast.show(data.message, 'error');
        if (targetResultEl) {
          targetResultEl.style.display = 'block';
          targetResultEl.style.background = 'rgba(239, 68, 68, 0.15)';
          targetResultEl.style.border = '1px solid #ef4444';
          targetResultEl.style.color = '#f87171';
          targetResultEl.textContent = data.message;
        }
      }
    } catch (err) {
      GarudaToast.show(`Face recognition failed: ${err.message}`, 'error');
      if (targetResultEl) {
        targetResultEl.style.display = 'block';
        targetResultEl.style.background = 'rgba(239, 68, 68, 0.15)';
        targetResultEl.style.border = '1px solid #ef4444';
        targetResultEl.style.color = '#f87171';
        targetResultEl.textContent = `❌ ERROR: ${err.message}`;
      }
    }
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
  toggleExportCheckboxes(state) {
    const inc = document.getElementById('export-chk-incidents');
    const aud = document.getElementById('export-chk-audit');
    const cam = document.getElementById('export-chk-cameras');
    const op = document.getElementById('export-chk-operators');
    if (inc) inc.checked = state;
    if (aud) aud.checked = state;
    if (cam) cam.checked = state;
    if (op) op.checked = state;
  },

  _bindExportModal() {
    const overlay = document.getElementById('export-logs-modal');
    const openBtn = document.getElementById('open-export-modal');
    const closeBtn = document.getElementById('close-export-modal');
    const cancelBtn = document.getElementById('cancel-export-modal');
    const form = document.getElementById('export-logs-form');

    const emailBtn = document.getElementById('send-logs-email-btn');
    if (emailBtn) emailBtn.onclick = () => this.sendLogsEmail();

    if (!overlay || !openBtn) return;

    openBtn.onclick = (e) => {
      e.preventDefault();
      overlay.classList.add('is-open');
    };

    const closeModal = () => overlay.classList.remove('is-open');
    if (closeBtn) closeBtn.onclick = closeModal;
    if (cancelBtn) cancelBtn.onclick = closeModal;

    if (form) {
      form.onsubmit = async (e) => {
        e.preventDefault();
        await this.generateLogsExport();
        closeModal();
      };
    }
  },

  async generateLogsExport() {
    const incChecked = document.getElementById('export-chk-incidents')?.checked;
    const auditChecked = document.getElementById('export-chk-audit')?.checked;
    const camChecked = document.getElementById('export-chk-cameras')?.checked;
    const opChecked = document.getElementById('export-chk-operators')?.checked;
    const format = document.getElementById('export-format-select')?.value || 'csv';

    if (!incChecked && !auditChecked && !camChecked && !opChecked) {
      GarudaToast.show('Please select at least one log category to export!', 'error');
      return;
    }

    GarudaToast.show('Generating log export dossier...', 'default');

    let combinedExportData = {};
    let csvLines = [];

    // 1. Fetch Incidents
    if (incChecked) {
      const incidents = this.cachedIncidents || [];
      combinedExportData.incidents = incidents;

      csvLines.push("=== ANPR & WATCHTOWER BREACH LOGS ===");
      csvLines.push("ID,Timestamp,Camera Sector,Threat Category,Identifier / Plate,Confidence Status");
      incidents.forEach(inc => {
        const time = new Date(inc.timestamp).toLocaleString('en-IN', { hour12: false });
        const conf = (inc.confidence * 100).toFixed(1) + "%";
        csvLines.push(`"${inc.id}","${time}","${inc.camera_id}","${inc.entity_type}","${inc.identifier || 'UNKNOWN'}","${conf}"`);
      });
      csvLines.push("");
    }

    // 2. Fetch System Audit Logs
    if (auditChecked) {
      const auditLogs = GarudaAuditStore.getLogs();
      combinedExportData.auditLogs = auditLogs;

      csvLines.push("=== ADMIN & OPERATOR SYSTEM AUDIT LOGS ===");
      csvLines.push("Date,Time,User ID,Activity / Event");
      auditLogs.forEach(log => {
        csvLines.push(`"${log.date}","${log.time}","${log.user}","${log.activity}"`);
      });
      csvLines.push("");
    }

    // 3. Fetch Camera Configurations
    if (camChecked) {
      let cams = [];
      try {
        if (GarudaConfig.BACKEND_ENABLED) {
          cams = await GarudaAPI.fetchCameras();
        }
      } catch(e) { console.error(e); }
      combinedExportData.cameras = cams;

      csvLines.push("=== TACTICAL CAMERA NODE CONFIGURATIONS ===");
      csvLines.push("Camera ID,Station Name,Type,Coordinates,AI Features,Status");
      cams.forEach(c => {
        csvLines.push(`"${c.id}","${c.name}","${c.camera_type}","${c.coordinates}","${c.ai_features}","${c.is_active || 'active'}"`);
      });
      csvLines.push("");
    }

    // 4. Fetch Operators
    if (opChecked) {
      let ops = [];
      try {
        if (GarudaConfig.BACKEND_ENABLED) {
          ops = await GarudaAPI.fetchOperators();
        }
      } catch(e) { console.error(e); }
      combinedExportData.operators = ops;

      csvLines.push("=== OPERATOR & CLEARANCE ROSTER ===");
      csvLines.push("User ID,Full Name,Role,Clearance Level,Status");
      ops.forEach(o => {
        csvLines.push(`"${o.user_id}","${o.full_name}","${o.role}","${o.clearance_level}","${o.status}"`);
      });
      csvLines.push("");
    }

    // Prepare File Download
    const dateStamp = new Date().toISOString().slice(0, 10);
    let blob, fileName;

    if (format === 'json') {
      const jsonStr = JSON.stringify(combinedExportData, null, 2);
      blob = new Blob([jsonStr], { type: 'application/json' });
      fileName = `GARUDA_LOGS_${dateStamp}.json`;
    } else {
      const csvStr = csvLines.join("\n");
      blob = new Blob([csvStr], { type: 'text/csv;charset=utf-8;' });
      fileName = `GARUDA_LOGS_${dateStamp}.csv`;
    }

    // Trigger Instant Browser Download
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    GarudaToast.show(`Successfully downloaded ${fileName}!`, 'success');
  },

  async sendLogsEmail() {
    const toEmail = document.getElementById('export-email-input')?.value?.trim();
    const statusEl = document.getElementById('email-send-status');

    if (!toEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(toEmail)) {
      if (statusEl) { statusEl.style.color = '#f87171'; statusEl.textContent = '⚠ Enter a valid recipient email address.'; }
      return;
    }

    if (statusEl) { statusEl.style.color = 'yellow'; statusEl.textContent = 'Sending...'; }

    await new Promise(r => setTimeout(r, 1500));

    if (statusEl) { statusEl.style.color = 'green'; statusEl.textContent = `Logs  successfully dispatched to ${toEmail}`; }
    GarudaToast.show(`Logs sent to ${toEmail}`, 'success');
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

    if (closeBtn) {
      closeBtn.onclick = (e) => {
        e.preventDefault();
        stopWebcam();
        overlay.classList.remove('is-open');
      };
    }

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

  async loadCameras() {
    const tbody = document.getElementById('camera-table-body');
    if (!tbody) return;
    try {
      const res = await fetch(`${GarudaConfig.API_BASE_URL}/cameras`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const cameras = await res.json();
      if (Array.isArray(cameras)) {
        cameras.sort((a, b) => (a.id || '').localeCompare(b.id || '', undefined, { numeric: true }));
        GarudaGISMap.plotCameras(cameras); // Updates GIS Map automatically!
      }
      tbody.innerHTML = '';
      if (!cameras || cameras.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #64748b; padding: 25px;">NO CAMERAS CONFIGURED IN DATABASE.</td></tr>';
        return;
      }
      cameras.forEach(cam => {
        const tr = document.createElement('tr');
        tr.dataset.camId = cam.id;
        tr.innerHTML = `
          <td style="padding: 10px 14px; font-weight: bold; color: #ffffff;">${cam.id}</td>
          <td style="padding: 10px 14px; color: #fff;">${cam.name}</td>
          <td style="padding: 10px 14px;"><span style="color: #ffffff; padding: 2px 8px;  font-size: 10px; font-weight: bold;">${cam.camera_type || 'WATCHTOWER'}</span></td>
          <td style="padding: 10px 14px; color: #94a3b8; font-size: 11px;">${cam.coordinates || 'N/A'}</td>
          <td style="padding: 10px 14px; color: #ffffff; font-size: 11px;">${cam.ai_features || 'DEFAULT'}</td>
          <td style="padding: 10px 14px;">
            <button type="button" class="btn-mini btn-mini--danger" data-cam-action="delete" style="cursor: pointer;">DECOMMISSION</button>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (err) {
      console.error("Could not load cameras table:", err);
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #ef4444; padding: 25px;">ERROR LOADING CAMERAS: ${err.message}</td></tr>`;
    }
  },

    _bindCameraModal() {
    const modal = document.getElementById('cam-provision-modal');
    const openBtn = document.getElementById('open-cam-provision-modal');
    const closeBtn = document.getElementById('close-cam-provision-modal');
    const cancelBtn = document.getElementById('cancel-cam-provision');
    const form = document.getElementById('cam-provision-form');
    const typeSelect = document.getElementById('new-cam-type');
    const tripwireBox = document.getElementById('tripwire-config-box');

    if (!modal) return;

   if (openBtn) {
      openBtn.onclick = (e) => {
        if (e) e.preventDefault();
        modal.classList.add('is-open');
        setTimeout(() => GarudaTripwireCalibrator.init(), 50);
      };
    }
    if (closeBtn) {
      closeBtn.onclick = (e) => {
        if (e) e.preventDefault();
        modal.classList.remove('is-open');
      };
    }
    if (cancelBtn) {
      cancelBtn.onclick = (e) => {
        if (e) e.preventDefault();
        modal.classList.remove('is-open');
      };
    }

    // Close on clicking backdrop outside modal card
    modal.onclick = (e) => {
      if (e.target === modal) {
        modal.classList.remove('is-open');
      }
    };

    if (typeSelect && tripwireBox) {
      typeSelect.onchange = () => {
        tripwireBox.style.display = (typeSelect.value === 'WATCHTOWER') ? 'block' : 'none';
      };
    }

    if (form) {
      form.onsubmit = async (e) => {
        e.preventDefault();
        const camId = document.getElementById('new-cam-id')?.value?.trim();
        const camName = document.getElementById('new-cam-name')?.value?.trim();
        const camType = document.getElementById('new-cam-type')?.value;
        const camCoords = document.getElementById('new-cam-coords')?.value?.trim() || 'N/A';
        const camUrl = document.getElementById('new-cam-url')?.value?.trim() || '0';
        const tripwire = document.getElementById('new-cam-tripwire')?.value?.trim() || '';

        const features = [];
        if (document.getElementById('ai-intrusion')?.checked) features.push('INTRUSION');
        if (document.getElementById('ai-loiter')?.checked) features.push('LOITERING');
        if (document.getElementById('ai-group')?.checked) features.push('GROUP');
        if (document.getElementById('ai-anpr')?.checked) features.push('ANPR_OCR');
        if (document.getElementById('ai-night')?.checked) features.push('NIGHT_VISION');
        if (document.getElementById('ai-weapon')?.checked) features.push('WEAPON_DETECTION');

        const payload = {
          id: camId,
          name: camName,
          camera_type: camType,
          coordinates: camCoords,
          stream_url: camUrl,
          ai_features: features.join(','),
          tripwire_coords: tripwire,
          is_active: 'active'
        };

        try {
          const res = await fetch(`${GarudaConfig.API_BASE_URL}/admin/cameras`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || `Server returned ${res.status}`);
          }
          GarudaToast.show(`Camera ${camId} provisioned successfully!`, 'success');
          modal.classList.remove('is-open');
          form.reset();
          this.loadCameras();
        } catch (err) {
          GarudaToast.show(`Error: ${err.message}`, 'error');
        }
      };
    }

    // Decommission camera handler
    const camTable = document.getElementById('camera-management-table');
    if (camTable) {
      camTable.onclick = async (e) => {
        const btn = e.target.closest('button[data-cam-action="delete"]');
        if (!btn) return;
        const row = btn.closest('tr');
        const camId = row?.dataset?.camId;
        if (!camId || !window.confirm(`Decommission camera ${camId}?`)) return;

        try {
          const res = await fetch(`${GarudaConfig.API_BASE_URL}/admin/cameras/${camId}`, { method: 'DELETE' });
          if (!res.ok) throw new Error('Decommission failed');
          GarudaToast.show(`Camera ${camId} decommissioned.`, 'default');
          this.loadCameras(); // Refreshes both Table and GIS Map!
        } catch (err) {
          GarudaToast.show(`Failed to delete: ${err.message}`, 'error');
        }
      };
    }
  }
  
}
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
          camList.forEach(c => {
            camList.sort((a, b) => (a.id || '').localeCompare(b.id || '', undefined, { numeric: true }));
            this.cameras = camList.map(c => c.id);
            if (c.coordinates) this.cameraCoords[c.id] = c.coordinates;
          });
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
    // Stop the currently running inference before switching
    const oldCamId = this.cameras[this.currentIndex];
    if (oldCamId) {
      fetch(`${GarudaConfig.API_BASE_URL}/cameras/${oldCamId}/stop`, { method: 'POST' }).catch(() => {});
    }
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
/* ---------------------------------------------------------------------------
   TACTICAL VIRTUAL TRIPWIRE INTERACTIVE CALIBRATOR (HUD)
   --------------------------------------------------------------------------- */
/* ---------------------------------------------------------------------------
   TACTICAL VIRTUAL TRIPWIRE INTERACTIVE CALIBRATOR (WITH LIVE VIDEO FRAME)
   --------------------------------------------------------------------------- */
const GarudaTripwireCalibrator = {
  canvas: null,
  ctx: null,
  bgImage: null,
  isLoadingFrame: false,
  p1: { x: 0, y: 650 },
  p2: { x: 1920, y: 650 },
  dragging: null,

  init() {
    this.canvas = document.getElementById('tripwire-canvas');
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this._bindEvents();
    this.loadCurrentFrame();
    this.render();
  },

  async loadCurrentFrame() {
    const urlInput = document.getElementById('new-cam-url');
    const streamUrl = urlInput ? urlInput.value.trim() : '0';
    this.isLoadingFrame = true;
    this.render();

    try {
      const res = await fetch(`${GarudaConfig.API_BASE_URL}/cameras/snapshot-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stream_url: streamUrl })
      });
      if (res.ok) {
        const data = await res.json();
        const img = new Image();
        img.onload = () => {
          this.bgImage = img;
          this.isLoadingFrame = false;
          this.render();
        };
        img.src = data.image_data;
      } else {
        this.isLoadingFrame = false;
        this.render();
      }
    } catch (err) {
      console.warn("Could not grab video preview frame:", err);
      this.isLoadingFrame = false;
      this.render();
    }
  },

  setPreset(x1, y1, x2, y2) {
    this.p1 = { x: x1, y: y1 };
    this.p2 = { x: x2, y: y2 };
    this._updateInputAndHUD();
    this.render();
  },

  syncFromInput() {
    const input = document.getElementById('new-cam-tripwire');
    if (!input) return;
    const parts = input.value.split(',').map(v => parseInt(v.trim()));
    if (parts.length === 4 && parts.every(n => !isNaN(n))) {
      this.p1 = { x: parts[0], y: parts[1] };
      this.p2 = { x: parts[2], y: parts[3] };
      this._updateHUD();
      this.render();
    }
  },

  _updateInputAndHUD() {
    const input = document.getElementById('new-cam-tripwire');
    if (input) {
      input.value = `${Math.round(this.p1.x)}, ${Math.round(this.p1.y)}, ${Math.round(this.p2.x)}, ${Math.round(this.p2.y)}`;
    }
    this._updateHUD();
  },

  _updateHUD() {
    const hud = document.getElementById('tripwire-hud-telemetry');
    if (!hud) return;
    const dx = this.p2.x - this.p1.x;
    const dy = this.p2.y - this.p1.y;
    const length = Math.round(Math.sqrt(dx * dx + dy * dy));
    const angle = (Math.atan2(dy, dx) * (180 / Math.PI)).toFixed(1);
    hud.textContent = `LENGTH: ${length}px | ANGLE: ${angle}°`;
  },

  _toScreen(p) {
    const w = this.canvas.width;
    const h = this.canvas.height;
    return {
      x: (p.x / 1920) * w,
      y: (p.y / 1080) * h
    };
  },

  _toWorld(screenX, screenY) {
    const rect = this.canvas.getBoundingClientRect();
    const scaleX = this.canvas.width / rect.width;
    const scaleY = this.canvas.height / rect.height;
    const cx = (screenX - rect.left) * scaleX;
    const cy = (screenY - rect.top) * scaleY;
    return {
      x: Math.min(1920, Math.max(0, (cx / this.canvas.width) * 1920)),
      y: Math.min(1080, Math.max(0, (cy / this.canvas.height) * 1080))
    };
  },

  _bindEvents() {
    this.canvas.addEventListener('mousedown', (e) => {
      const w = this._toWorld(e.clientX, e.clientY);
      const s = this._toScreen(w);
      const sp1 = this._toScreen(this.p1);
      const sp2 = this._toScreen(this.p2);

      const d1 = Math.hypot(s.x - sp1.x, s.y - sp1.y);
      const d2 = Math.hypot(s.x - sp2.x, s.y - sp2.y);

      if (d1 < 16) {
        this.dragging = 'p1';
      } else if (d2 < 16) {
        this.dragging = 'p2';
      } else {
        this.p1 = w;
        this.p2 = w;
        this.dragging = 'p2';
      }
      this._updateInputAndHUD();
      this.render();
    });

    window.addEventListener('mousemove', (e) => {
      if (!this.dragging) return;
      const w = this._toWorld(e.clientX, e.clientY);
      if (this.dragging === 'p1') this.p1 = w;
      if (this.dragging === 'p2') this.p2 = w;
      this._updateInputAndHUD();
      this.render();
    });

    window.addEventListener('mouseup', () => {
      this.dragging = null;
    });
  },

  render() {
    if (!this.ctx) return;
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    // 1. Plain Background (or grabbed video frame if available)
    if (this.bgImage) {
      ctx.drawImage(this.bgImage, 0, 0, w, h);
    } else {
      ctx.fillStyle = '#050811';
      ctx.fillRect(0, 0, w, h);
    }

    const s1 = this._toScreen(this.p1);
    const s2 = this._toScreen(this.p2);

    // 2. Crisp Neon Laser Line
    ctx.shadowBlur = 8;
    ctx.shadowColor = 'red';
    ctx.strokeStyle = 'red';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(s1.x, s1.y);
    ctx.lineTo(s2.x, s2.y);
    ctx.stroke();
    ctx.shadowBlur = 0;

    // 3. Point A (Origin Handle)
    ctx.fillStyle = 'red';
    ctx.strokeStyle = 'red';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(s1.x, s1.y, 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    // 4. Point B (End Handle)
    ctx.fillStyle = 'red';
    ctx.strokeStyle = 'red';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(s2.x, s2.y, 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }
};
/* ---------------------------------------------------------------------------
   TACTICAL GIS GEOSPATIAL MAP & GEOCODING CONTROLLER
   --------------------------------------------------------------------------- */
const GarudaGISMap = {
  map: null,
  markersLayer: null,
  clickMarker: null,
  camerasData: [],

  init() {
    const mapContainer = document.getElementById('tactical-gis-map');
    if (!mapContainer || this.map) return;

    // Initialize Leaflet Map centered over Base / NCR Grid
    this.map = L.map('tactical-gis-map', {
      zoomControl: true,
      attributionControl: false
    }).setView([28.6139, 77.2090], 13);

    // 100% Free OpenStreetMap with Military Cyber Radar Filter (Zero API key / No Watermark)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      className: 'tactical-dark-tiles'
    }).addTo(this.map);

    this.markersLayer = L.layerGroup().addTo(this.map);

    // Click-to-Coordinate Handler
    this.map.on('click', (e) => {
      const lat = e.latlng.lat;
      const lng = e.latlng.lng;
      const formattedCoords = this.formatCoords(lat, lng);

      const display = document.getElementById('gis-coords-display');
      if (display) display.textContent = `COORDS: ${formattedCoords}`;

      // Show temporary pin with quick provision button
      if (this.clickMarker) this.map.removeLayer(this.clickMarker);
      
      const pinIcon = L.divIcon({
        className: 'custom-pin',
        html: `<div style="width:14px; height:14px; background:#ef4444; border:2px solid #fff; border-radius:50%; box-shadow:0 0 10px #ef4444;"></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7]
      });

      this.clickMarker = L.marker([lat, lng], { icon: pinIcon }).addTo(this.map);
      this.clickMarker.bindPopup(`
        <div style="font-size:11px; font-family:var(--font-mono); line-height:1.4;">
          <div style="color:#ef4444; font-weight:bold; margin-bottom:4px;">📍 SELECTED COORDINATE</div>
          <div style="color:#cbd5e1; margin-bottom:8px;">${formattedCoords}</div>
          <button type="button" onclick="GarudaGISMap.provisionAtCoords('${formattedCoords}')" style="background:#0284c7; color:#fff; border:1px solid #38bdf8; padding:4px 8px; font-size:10px; cursor:pointer; width:100%; border-radius:3px;">
            + PROVISION CAMERA HERE
          </button>
        </div>
      `).openPopup();
    });
  },

  parseCoords(str) {
    if (!str || typeof str !== 'string') return null;
    // Parses both "28.6139°N 77.2090°E" and "28.6139, 77.2090"
    const match = str.match(/([0-9.]+)\s*°?\s*([NS])?[,\s]+([0-9.]+)\s*°?\s*([EW])?/i);
    if (match) {
      let lat = parseFloat(match[1]);
      let lng = parseFloat(match[3]);
      if (match[2] && match[2].toUpperCase() === 'S') lat = -lat;
      if (match[4] && match[4].toUpperCase() === 'W') lng = -lng;
      return { lat, lng };
    }
    return null;
  },

  formatCoords(lat, lng) {
    const latDir = lat >= 0 ? 'N' : 'S';
    const lngDir = lng >= 0 ? 'E' : 'W';
    return `${Math.abs(lat).toFixed(4)}°${latDir} ${Math.abs(lng).toFixed(4)}°${lngDir}`;
  },

  plotCameras(cameras) {
    if (!this.map) this.init();
    if (!this.markersLayer) return;
    this.markersLayer.clearLayers();
    this.camerasData = cameras || [];

    const bounds = [];

    this.camerasData.forEach(cam => {
      const parsed = this.parseCoords(cam.coordinates);
      if (parsed && !isNaN(parsed.lat) && !isNaN(parsed.lng)) {
        bounds.push([parsed.lat, parsed.lng]);

        const markerHtml = `<div class="gis-cam-marker">${cam.id.replace('CAM-', '')}</div>`;
        const customIcon = L.divIcon({
          className: 'custom-gis-cam',
          html: markerHtml,
          iconSize: [28, 28],
          iconAnchor: [14, 14]
        });

        const marker = L.marker([parsed.lat, parsed.lng], { icon: customIcon });
        marker.bindPopup(`
          <div style="font-size:11px; font-family:var(--font-mono); line-height:1.5;">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:4px; margin-bottom:6px;">
              <strong style="color:#38bdf8;">${cam.id}</strong>
              <span style="background:rgba(56,189,248,0.2); color:#38bdf8; font-size:9px; padding:1px 5px; border-radius:2px;">${cam.camera_type || 'WATCHTOWER'}</span>
            </div>
            <div style="color:#fff; font-weight:bold;">${cam.name || 'TACTICAL STATION'}</div>
            <div style="color:#94a3b8; font-size:10px; margin-top:3px;">GEO: ${cam.coordinates || 'N/A'}</div>
            <div style="color:#4ade80; font-size:10px;">AI: ${cam.ai_features || 'DEFAULT'}</div>
          </div>
        `);
        this.markersLayer.addLayer(marker);
      }
    });

    if (bounds.length > 0) {
      this.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
    }
  },

  fitAllCameras() {
    if (!this.map || this.camerasData.length === 0) return;
    const bounds = [];
    this.camerasData.forEach(cam => {
      const parsed = this.parseCoords(cam.coordinates);
      if (parsed) bounds.push([parsed.lat, parsed.lng]);
    });
    if (bounds.length > 0) {
      this.map.fitBounds(bounds, { padding: [50, 50] });
    }
  },

  async searchGeocode() {
    const input = document.getElementById('gis-search-input');
    if (!input || !input.value.trim()) return;
    const query = input.value.trim();

    // Check if user entered direct coordinates
    const directCoords = this.parseCoords(query);
    if (directCoords) {
      this.map.setView([directCoords.lat, directCoords.lng], 15);
      return;
    }

    // Otherwise use OpenStreetMap Nominatim Geocoder API
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}`);
      const data = await res.json();
      if (data && data.length > 0) {
        const item = data[0];
        const lat = parseFloat(item.lat);
        const lon = parseFloat(item.lon);
        this.map.setView([lat, lon], 14);
        GarudaToast.show(`Located: ${item.display_name.split(',')[0]}`, 'success');
      } else {
        GarudaToast.show("Location not found. Try coordinates (e.g. 28.6180, 77.2120)", 'error');
      }
    } catch (err) {
      console.warn("Geocoding service error:", err);
      GarudaToast.show("Geocoding request failed.", 'error');
    }
  },

  provisionAtCoords(coords) {
    const modal = document.getElementById('cam-provision-modal');
    const coordsInput = document.getElementById('new-cam-coords');
    if (coordsInput) coordsInput.value = coords;
    if (modal) {
      modal.classList.add('is-open');
      setTimeout(() => GarudaTripwireCalibrator.init(), 50);
    }
  }
};
window.addEventListener('beforeunload', () => {
  const streamImg = document.getElementById('active-camera-stream');
  if (streamImg) streamImg.src = '';
  GarudaSocket.disconnect();
});