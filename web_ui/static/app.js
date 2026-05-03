const logFeed = document.getElementById('logFeed');
const logCount = document.getElementById('logCount');
const clearLogsBtn = document.getElementById('clearLogs');
const startRunBtn = document.getElementById('startRun');
const refreshOutputsBtn = document.getElementById('refreshOutputs');
const promptField = document.getElementById('prompt');
const systemStatus = document.getElementById('systemStatus');
const artifactMap = document.querySelector('.artifact-map');

let logEvents = 0;

function badgeText(level, source) {
  if (source === 'WEB_UI') return 'UI';
  if (level === 'llm_request') return 'LLM Request';
  if (level === 'llm_response') return 'LLM Response';
  if (level === 'warn') return 'Warning';
  if (level === 'error') return 'Error';
  if (level === 'agent') return source;
  return (level || 'info').toUpperCase();
}

function displaySource(source) {
  if (!source) return 'SYSTEM';
  return source;
}

function renderLogEntry(entry) {
  if (!entry || entry.skip) return;
  const level = (entry.level || 'info').toLowerCase();
  const source = displaySource(entry.source || 'SYSTEM');
  const message = entry.message || '';
  const time = entry.time || new Date().toLocaleTimeString();

  const row = document.createElement('div');
  row.className = `log-entry log-entry--${level}`;

  const meta = document.createElement('div');
  meta.className = 'log-entry__meta';

  const timeEl = document.createElement('div');
  timeEl.className = 'log-entry__time';
  timeEl.textContent = time;

  const badge = document.createElement('div');
  badge.className = 'log-badge';
  badge.textContent = badgeText(level, source);

  const sourceEl = document.createElement('div');
  sourceEl.className = 'log-source';
  sourceEl.textContent = source;

  meta.appendChild(timeEl);
  meta.appendChild(badge);
  meta.appendChild(sourceEl);

  const msg = document.createElement('div');
  msg.className = 'log-message';
  msg.textContent = message;

  row.appendChild(meta);
  row.appendChild(msg);
  logFeed.appendChild(row);
  logEvents += 1;
  logCount.textContent = `${logEvents} event${logEvents === 1 ? '' : 's'}`;
  logFeed.scrollTop = logFeed.scrollHeight;
}

function setSystemStatus(text, tone) {
  if (!systemStatus) return;
  systemStatus.textContent = text;
  systemStatus.className = `status-pill ${tone || 'live'}`.trim();
}

function resetLogFeed() {
  logFeed.innerHTML = '';
  logEvents = 0;
  logCount.textContent = '0 events';
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function renderArtifactMap(categories) {
  if (!artifactMap) return;
  if (!Array.isArray(categories) || !categories.length) {
    artifactMap.innerHTML = '<p class="empty-state">No Markdown files found in this folder.</p>';
    return;
  }

  artifactMap.innerHTML = categories.map(category => {
    const runs = Array.isArray(category.runs) ? category.runs : [];
    const runsHtml = runs.length
      ? `<div class="run-rail">${runs.map(run => {
          const files = Array.isArray(run.files) ? run.files : [];
          const filesHtml = files.map(file => `
            <a class="file-node kind-${escapeHtml(file.kind || 'file')}" href="/view/?path=${encodeURIComponent(file.path || '')}">
              <span class="node-dot"></span>
              <span class="file-node__body">
                <span class="file-node__name">${escapeHtml(file.name || 'file.md')}</span>
                <span class="file-node__kind">${escapeHtml(file.kind_label || 'Markdown')}</span>
              </span>
            </a>
          `).join('');

          return `
            <article class="run-card">
              <div class="run-card__head">
                <div>
                  <div class="run-card__title">${escapeHtml(run.run_name || 'run')}</div>
                  <div class="run-card__meta">${escapeHtml(run.file_count || 0)} files · ${escapeHtml(run.run_path || '')}</div>
                </div>
              </div>
              <div class="file-tree">${filesHtml}</div>
            </article>
          `;
        }).join('')}</div>`
      : '<p class="empty-state">No Markdown files found in this folder.</p>';

    return `
      <div class="artifact-group">
        <div class="artifact-group__head">
          <h3>${escapeHtml(category.name || 'outputs')}</h3>
          <span class="chip">${runs.length} runs</span>
        </div>
        ${runsHtml}
      </div>
    `;
  }).join('');
}

async function loadHistory() {
  try {
    const response = await fetch('/log-history');
    const payload = await response.json();
    resetLogFeed();
    (payload.entries || []).forEach(renderLogEntry);
    setSystemStatus('System live', 'live');
  } catch (error) {
    renderLogEntry({ level: 'warn', source: 'WEB_UI', message: 'Unable to load log history.' });
    setSystemStatus('History unavailable', '');
  }
}

async function refreshOutputs() {
  if (!artifactMap) return;
  try {
    const response = await fetch('/outputs-catalog');
    const payload = await response.json();
    renderArtifactMap(payload.categories || []);
    setSystemStatus('Outputs refreshed', 'live');
  } catch (error) {
    setSystemStatus('Refresh failed', '');
  }
}

function connectLogStream() {
  const source = new EventSource('/stream-logs');
  source.onopen = () => setSystemStatus('System live', 'live');
  source.onmessage = event => {
    try {
      const payload = JSON.parse(event.data);
      renderLogEntry(payload);
    } catch (error) {
      renderLogEntry({ level: 'warn', source: 'WEB_UI', message: 'Received malformed log event.' });
    }
  };
  source.onerror = () => {
    renderLogEntry({ level: 'warn', source: 'WEB_UI', message: 'Log stream disconnected.' });
    setSystemStatus('Reconnecting…', '');
  };
}

clearLogsBtn?.addEventListener('click', () => {
  resetLogFeed();
});

startRunBtn?.addEventListener('click', async () => {
  const prompt = promptField ? promptField.value : '';
  try {
    setSystemStatus('Starting run…', '');
    const response = await fetch('/start-run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `prompt=${encodeURIComponent(prompt)}`,
    });
    const payload = await response.json();
    renderLogEntry({ level: 'ui', source: 'WEB_UI', message: `Start run requested: ${payload.status || 'started'}` });
    setSystemStatus('System live', 'live');
  } catch (error) {
    renderLogEntry({ level: 'error', source: 'WEB_UI', message: 'Failed to start agent run.' });
    setSystemStatus('Run failed', '');
  }
});

refreshOutputsBtn?.addEventListener('click', () => {
  refreshOutputs();
});

loadHistory().then(connectLogStream);
