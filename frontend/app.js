const API_BASE = 'http://localhost:8000';

// Global State
const state = {
  projectId: 'default',
  currentPlanSession: null,
  docsCount: 0,
};

// ─── View Management ───
const views = ['dashboard', 'ingest', 'generate', 'plans', 'chat', 'trace'];

function switchView(viewId) {
  views.forEach(v => {
    document.getElementById(`view${v.charAt(0).toUpperCase() + v.slice(1)}`).classList.remove('active');
    document.getElementById(`nav${v.charAt(0).toUpperCase() + v.slice(1)}`).classList.remove('active');
  });
  
  document.getElementById(`view${viewId.charAt(0).toUpperCase() + viewId.slice(1)}`).classList.add('active');
  document.getElementById(`nav${viewId.charAt(0).toUpperCase() + viewId.slice(1)}`).classList.add('active');
  
  logActivity(`Switched view to ${viewId.toUpperCase()}`);
}

// Attach nav listeners
views.forEach(v => {
  document.getElementById(`nav${v.charAt(0).toUpperCase() + v.slice(1)}`).addEventListener('click', () => switchView(v));
});

// Sync Project ID
document.getElementById('projectIdInput').addEventListener('input', (e) => {
  state.projectId = e.target.value || 'default';
  document.getElementById('genProject').value = state.projectId;
});
document.getElementById('genProject').value = state.projectId;

// Detail Toggle
document.querySelectorAll('#detailToggle .toggle-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('#detailToggle .toggle-btn').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
  });
});

// ─── API & Logic ───

function logActivity(msg, type = 'info') {
  const log = document.getElementById('activityLog');
  const entry = document.createElement('div');
  entry.className = `log-entry ${type}`;
  const now = new Date();
  const timeStr = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}:${now.getSeconds().toString().padStart(2,'0')}`;
  entry.innerHTML = `<span class="log-time">${timeStr}</span><span class="log-msg">${msg}</span>`;
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}

async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if(res.ok) {
      document.getElementById('apiStatusBadge').innerHTML = '●&nbsp;CONNECTED';
      document.getElementById('apiStatusBadge').style.color = 'var(--success)';
      document.querySelector('.status-dot').className = 'status-dot online';
      document.querySelector('.status-label').innerText = 'SYSTEM ONLINE';
    }
  } catch(e) {
    document.getElementById('apiStatusBadge').innerHTML = '○&nbsp;OFFLINE';
    document.getElementById('apiStatusBadge').style.color = 'var(--error)';
    document.querySelector('.status-dot').className = 'status-dot';
    document.querySelector('.status-dot').style.backgroundColor = 'var(--error)';
    document.querySelector('.status-label').innerText = 'SYSTEM OFFLINE';
    logActivity('API connection failed', 'error');
  }
}
setInterval(checkHealth, 10000);
checkHealth();

// Ingestion
const fileInput = document.getElementById('fileInput');
fileInput.addEventListener('change', async (e) => {
  if(!e.target.files.length) return;
  const file = e.target.files[0];
  
  document.getElementById('ingestProgress').classList.remove('hidden');
  document.getElementById('ingestResult').classList.add('hidden');
  document.getElementById('ingestProgressBar').style.width = '30%';
  
  logActivity(`Initiating upload: ${file.name}`);
  
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    const res = await fetch(`${API_BASE}/projects/${state.projectId}/ingest`, {
      method: 'POST',
      body: formData
    });
    
    document.getElementById('ingestProgressBar').style.width = '100%';
    
    if(!res.ok) throw new Error(await res.text());
    
    const data = await res.json();
    
    setTimeout(() => {
      document.getElementById('ingestProgress').classList.add('hidden');
      document.getElementById('ingestResult').classList.remove('hidden');
      
      const grid = document.getElementById('resultGrid');
      grid.innerHTML = `
        <div class="dash-card">
          <span class="meta-label">DOCUMENT ID</span>
          <div class="meta-value">${data.document_id}</div>
        </div>
        <div class="dash-card">
          <span class="meta-label">EXTRACTED REQS</span>
          <div class="meta-value">${data.requirements_extracted}</div>
        </div>
      `;
      
      state.docsCount++;
      document.getElementById('statDocsCount').innerText = state.docsCount;
      document.getElementById('statReqsCount').innerText = parseInt(document.getElementById('statReqsCount').innerText) + data.requirements_extracted;
      
      logActivity(`Ingestion successful: ${data.requirements_extracted} requirements extracted`);
    }, 500);
    
  } catch(e) {
    document.getElementById('ingestProgress').classList.add('hidden');
    logActivity(`Ingestion failed: ${e.message}`, 'error');
    alert(`Upload failed: ${e.message}`);
  }
});

// Generation
let pollInterval;
async function launchGeneration() {
  const goal = document.getElementById('genGoal').value;
  const detailLevel = document.querySelector('#detailToggle .active').dataset.value;
  const proj = document.getElementById('genProject').value || 'default';
  
  if(!goal) return alert("Enter a mission objective");
  
  document.getElementById('genProgress').classList.remove('hidden');
  document.getElementById('genEvents').innerHTML = '';
  document.getElementById('genStatusLabel').innerText = 'INITIALIZING';
  
  logActivity(`Triggered plan generation [${detailLevel}]`);
  
  try {
    const res = await fetch(`${API_BASE}/projects/${proj}/plans`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal, detail_level: detailLevel })
    });
    
    if(!res.ok) throw new Error(await res.text());
    const data = await res.json();
    
    state.currentPlanSession = data.session_id;
    document.getElementById('genSessionId').innerText = data.session_id;
    document.getElementById('genStatusLabel').innerText = 'RUNNING';
    
    // Poll for status
    if(pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(() => pollSession(data.session_id), 2000);
    
  } catch(e) {
    logActivity(`Generation launch failed: ${e.message}`, 'error');
    document.getElementById('genStatusLabel').innerText = 'ERROR';
  }
}

async function pollSession(sessionId) {
  try {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}`);
    if(!res.ok) return;
    const data = await res.json();
    
    const eventsDiv = document.getElementById('genEvents');
    eventsDiv.innerHTML = data.recent_events.map(ev => 
      `<div class="log-entry"><span class="log-time">${new Date(ev.ts).toLocaleTimeString()}</span><span class="log-msg">[${ev.actor}] ${ev.content}</span></div>`
    ).join('');
    
    if(data.state.status === 'completed' || data.state.status === 'error') {
      clearInterval(pollInterval);
      document.getElementById('genStatusLabel').innerText = data.state.status.toUpperCase();
      document.querySelector('.gen-status-indicator').classList.remove('running');
      if(data.state.status === 'completed') {
        logActivity(`Generation completed. Plan: ${data.state.plan_id}`);
        loadPlans(); // refresh plans view
      }
    }
  } catch(e) {
    console.error(e);
  }
}

// Chat
async function sendChat() {
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if(!msg) return;
  
  input.value = '';
  
  const chatDiv = document.getElementById('chatMessages');
  chatDiv.innerHTML += `
    <div class="chat-msg user">
      <div class="msg-avatar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>
      <div class="msg-content"><span class="msg-role">User</span><p>${msg}</p></div>
    </div>
  `;
  chatDiv.scrollTop = chatDiv.scrollHeight;
  
  try {
    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: state.projectId, session_id: state.currentPlanSession, message: msg })
    });
    
    if(!res.ok) throw new Error(await res.text());
    const data = await res.json();
    
    chatDiv.innerHTML += `
      <div class="chat-msg assistant">
        <div class="msg-avatar"><svg width="18" height="18" viewBox="0 0 28 28" fill="none"><path d="M14 2L2 8v12l12 6 12-6V8L14 2z" stroke="currentColor" stroke-width="1.5" fill="none"/><circle cx="14" cy="14" r="3" fill="currentColor"/></svg></div>
        <div class="msg-content"><span class="msg-role">AEGIS Copilot</span><p>${data.assistant_message}</p></div>
      </div>
    `;
    chatDiv.scrollTop = chatDiv.scrollHeight;
    
  } catch(e) {
    logActivity(`Chat error: ${e.message}`, 'error');
  }
}

// Traceability
async function runTrace() {
  const id = document.getElementById('traceInput').value.trim();
  if(!id) return;
  
  const resDiv = document.getElementById('traceResults');
  resDiv.classList.remove('hidden');
  resDiv.innerHTML = '<div class="progress-spinner"></div><p style="text-align:center">Tracing lineage...</p>';
  
  try {
    const res = await fetch(`${API_BASE}/trace/${id}`);
    if(!res.ok) throw new Error(await res.text());
    const data = await res.json();
    
    resDiv.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
    logActivity(`Traced artefact ${id}`);
    
  } catch(e) {
    resDiv.innerHTML = `<p style="color:var(--error)">Trace failed: ${e.message}</p>`;
  }
}

// Plans
async function loadPlans() {
  try {
    const res = await fetch(`${API_BASE}/projects/${state.projectId}/plans`);
    if(res.ok) {
      const plans = await res.json();
      document.getElementById('statPlansCount').innerText = plans.length;
      
      const list = document.getElementById('plansList');
      if(plans.length > 0) {
        list.innerHTML = plans.map(p => `
          <div class="dash-card" style="cursor:pointer" onclick="viewPlan('${p.id}')">
            <h3 style="margin-bottom:8px">${p.title}</h3>
            <p style="color:var(--text-muted);font-size:12px;font-family:var(--font-mono)">${p.id} · ${p.detail_level}</p>
          </div>
        `).join('');
      }
    }
  } catch(e) {
    console.error(e);
  }
}
// Load plans initially
loadPlans();

async function viewPlan(planId) {
  try {
    const res = await fetch(`${API_BASE}/projects/${state.projectId}/plans/${planId}`);
    if(!res.ok) throw new Error();
    const data = await res.json();
    
    document.getElementById('planDetail').classList.remove('hidden');
    document.getElementById('planDetail').innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px">
        <h2>${data.title}</h2>
        <button class="action-btn small" onclick="document.getElementById('planDetail').classList.add('hidden')">Close</button>
      </div>
      <div style="background:var(--bg-elevated);padding:16px;border:1px solid var(--border);margin-bottom:24px">
        <p style="color:var(--text-muted);margin-bottom:8px">STRATEGY</p>
        <p>${data.strategy}</p>
      </div>
      <h3>Test Cases (${data.test_cases.length})</h3>
      <div style="margin-top:16px;display:flex;flex-direction:column;gap:16px">
        ${data.test_cases.map(tc => `
          <div style="border:1px solid var(--border);padding:16px">
            <h4 style="color:var(--accent);margin-bottom:8px">${tc.title}</h4>
            <p style="font-size:12px;color:var(--text-muted)">Objective: ${tc.objective}</p>
            <p style="font-family:var(--font-mono);font-size:10px;margin-top:8px;color:var(--success)">ID: ${tc.id}</p>
          </div>
        `).join('')}
      </div>
    `;
    
    document.getElementById('statCasesCount').innerText = data.test_cases.length;
    
  } catch(e) {
    alert("Failed to load plan details");
  }
}
