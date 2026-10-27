(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = { rows: [], inputSource: '', result: null, health: null, requestId: 0, activeController: null, datasetId: null, manualMode: false, savedDatasets: [], savedForecasts: [], sortKey: 'timestamp', sortDirection: 1, toastTimer: null };
  const themeQuery = window.matchMedia('(prefers-color-scheme: light)');
  let themeChoice = localStorage.getItem('gridsense-theme') || 'system';

  function setTheme(choice, persist = true) {
    themeChoice = choice;
    const theme = choice === 'system' ? (themeQuery.matches ? 'light' : 'dark') : choice;
    document.documentElement.dataset.theme = theme;
    $('#theme-toggle').textContent = theme === 'dark' ? '☼' : '☾';
    $('#theme-toggle').setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`);
    $$('[data-theme-choice]').forEach(button => button.classList.toggle('selected', button.dataset.themeChoice === choice));
    if (persist) localStorage.setItem('gridsense-theme', choice);
  }
  setTheme(themeChoice, false);
  themeQuery.addEventListener('change', () => { if (themeChoice === 'system') setTheme('system', false); });
  $('#theme-toggle').addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
  $$('[data-theme-choice]').forEach(button => button.addEventListener('click', () => setTheme(button.dataset.themeChoice)));

  function updateClock() {
    const now = new Date();
    $('#clock-time').textContent = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(now);
    $('#clock-date').textContent = new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'short', day: 'numeric' }).format(now);
    $('#footer-time').textContent = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', timeZoneName: 'short' }).format(now);
    const weekday = new Intl.DateTimeFormat(undefined, { weekday: 'long' }).format(now).toUpperCase();
    const eyebrow = $('.view#view-overview .eyebrow');
    if (eyebrow) eyebrow.innerHTML = `<span class="eyebrow-bar"></span>${weekday} · MICROGRID OPERATIONS`;
  }
  updateClock();
  window.setInterval(updateClock, 30_000);

  const viewTitles = { overview: 'Overview', forecast: 'Demand forecast', controller: 'Grid controller', telemetry: 'Telemetry & data', alerts: 'Alerts & events', copilot: 'GridSense Copilot', model: 'Model health', settings: 'Settings & integrations' };
  function showView(view) {
    if (!viewTitles[view]) return;
    $$('.view').forEach(section => section.classList.toggle('active', section.id === `view-${view}`));
    $$('.nav-item[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
    $('#page-title').textContent = viewTitles[view];
    $('#sidebar').classList.remove('open');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  $$('.nav-item[data-view]').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
  $$('[data-nav]').forEach(button => button.addEventListener('click', () => showView(button.dataset.nav)));
  $('#menu-toggle').addEventListener('click', () => $('#sidebar').classList.toggle('open'));
  document.addEventListener('click', event => {
    if (window.innerWidth <= 900 && $('#sidebar').classList.contains('open') && !$('#sidebar').contains(event.target) && !$('#menu-toggle').contains(event.target)) $('#sidebar').classList.remove('open');
  });

  function notify(message, kind = '') {
    const toast = $('#toast');
    toast.textContent = message;
    toast.className = `toast show ${kind}`;
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => { toast.className = 'toast'; }, 3300);
  }
  function setNotice(message, kind = '') {
    const notice = $('#global-notice');
    notice.textContent = message;
    notice.className = `notice ${kind}`;
    notice.classList.remove('hidden');
  }
  function clearNotice() { $('#global-notice').classList.add('hidden'); }
  function loading(active) { $('#loading-overlay').classList.toggle('hidden', !active); }
  function invalidatePendingForecast() {
    state.requestId++;
    if (state.activeController) state.activeController.abort();
    state.activeController = null;
    loading(false);
  }
  function setRows(rows, source) {
    state.rows = rows.map(row => ({ ...row }));
    state.inputSource = source;
    state.datasetId = null;
    $('#row-count').textContent = `${state.rows.length} / 24 rows`;
    $('#run-data-forecast').disabled = state.rows.length !== 24;
    $('#save-dataset').disabled = state.rows.length !== 24;
    if (state.rows.length) renderPreview(state.rows);
  }
  function renderPreview(rows) {
    const shown = rows.slice(0, 5);
    $('#data-preview').innerHTML = `<div class="table-scroll"><table class="preview-table"><thead><tr><th>ROW</th><th>TIMESTAMP</th><th>TEMP °C</th><th>HUMIDITY %</th><th>SOLAR W/m²</th></tr></thead><tbody>${shown.map((row, index) => `<tr><td>${index + 1}</td><td>${escapeHtml(row.timestamp)}</td><td>${number(row.ambient_temp_c, 2)}</td><td>${number(row.humidity_pct, 2)}</td><td>${number(row.solar_irradiance_wm2, 1)}</td></tr>`).join('')}</tbody></table></div><span class="helper-text">${rows.length} rows accepted${rows.length > 5 ? ` · previewing first 5 of ${rows.length}` : ''}. Timestamps and input order are preserved.</span>`;
  }
  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
  }
  function number(value, digits = 1) { return Number(value).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits }); }
  function formatDemand(value, digits = 2) { const numeric = Number(value); return Math.min(Math.abs(numeric - 160), Math.abs(numeric - 200)) < 1 ? numeric.toString() : number(numeric, digits); }

  async function api(path, payload, signal, method = payload ? 'POST' : 'GET') {
    const options = { method, signal, cache: 'no-store' };
    if (payload !== undefined && payload !== null) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(payload);
    }
    const response = await fetch(path, options);
    let data;
    try { data = await response.json(); } catch { throw new Error(`Server returned an unreadable response (${response.status}).`); }
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
    return data;
  }

  async function checkHealth() {
    const dot = $('#connection-chip .status-dot');
    try {
      const health = await api('/api/health');
      state.health = health;
      const configured = health.model.quickml_configured;
      $('#connection-label').textContent = configured ? 'QuickML configured' : 'Demo model active';
      dot.className = `status-dot ${configured ? '' : 'warn'}`;
      $('#model-status-title').textContent = configured ? 'QuickML endpoint configured' : 'QuickML endpoint not configured';
      $('#model-status-description').textContent = configured ? 'Connection is checked during inference; endpoint was not probed on page load.' : 'Forecasts use a local model trained from official data and are labelled as demonstration output.';
      $('#model-source-value').textContent = health.model.prediction_source;
      $('#endpoint-state').textContent = configured ? 'Configured · verified on forecast' : 'Not configured';
      $('#token-state').textContent = health.model.api_token_configured ? 'Configured in backend' : 'Not configured';
      $('#quickml-detail').textContent = configured ? 'Endpoint URL is available to the backend. A successful model response is required before the forecast source is confirmed.' : 'No QuickML endpoint is configured. Set QUICKML_ENDPOINT_URL in the backend environment to use the published model.';
      $('#settings-quickml').textContent = configured ? 'Endpoint configured; awaiting inference verification' : 'No published endpoint configured';
      $('#settings-quickml-badge').textContent = configured ? 'Configured' : 'Unconfigured';
      $('#settings-quickml-badge').classList.toggle('quiet-state', !configured);
    } catch (error) {
      state.health = null;
      $('#connection-label').textContent = 'Backend unavailable';
      dot.className = 'status-dot bad';
      $('#model-status-title').textContent = 'Backend is unavailable';
      $('#model-status-description').textContent = 'Start the Python service and reload this page to check model status.';
      $('#model-source-value').textContent = 'Unavailable';
      $('#settings-quickml').textContent = error.message;
      $('#settings-quickml-badge').textContent = 'Offline';
      $('#settings-quickml-badge').classList.add('quiet-state');
    }
  }
  checkHealth();

  function selectInputTab(tabName) {
    $$('[data-input-tab]').forEach(button => {
      const selected = button.dataset.inputTab === tabName;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-selected', String(selected));
    });
    ['guided', 'import', 'sample'].forEach(name => $(`#panel-${name}`).classList.toggle('hidden', name !== tabName));
  }
  $$('[data-input-tab]').forEach(button => button.addEventListener('click', () => selectInputTab(button.dataset.inputTab)));

  const pad2 = value => String(value).padStart(2, '0');
  function displayDate(date) { return `${pad2(date.getDate())}-${pad2(date.getMonth() + 1)}-${date.getFullYear()}`; }
  function displayTimestamp(timestamp) {
    const [datePart, timePart = '00:00'] = String(timestamp).split(' ');
    const [year, month, day] = datePart.split('-');
    return `${day}-${month}-${year} ${timePart.slice(0, 5)}`;
  }
  function localTimestamp(date) {
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:00:00`;
  }
  const startingHour = new Date(); startingHour.setMinutes(0, 0, 0); startingHour.setHours(startingHour.getHours() + 1);
  $('#manual-date').value = displayDate(startingHour);
  $('#manual-time').value = `${pad2(startingHour.getHours())}:00`;

  function renderManualGrid(rows) {
    if (!rows.length) {
      $('#manual-grid').classList.add('empty-grid');
      $('#manual-grid').textContent = 'Set a start date and time, then create your table.';
      return;
    }
    $('#manual-grid').classList.remove('empty-grid');
    const columns = [
      ['ambient_temp_c', 'Temperature °C', '-80', '60', '0.1'],
      ['humidity_pct', 'Humidity %', '0', '100', '0.1'],
      ['solar_irradiance_wm2', 'Solar W/m²', '0', '2000', '0.1'],
    ];
    $('#manual-grid').innerHTML = `<div class="table-scroll"><table class="manual-entry-table"><thead><tr><th>HOUR</th>${columns.map(([, label]) => `<th>${label}</th>`).join('')}</tr></thead><tbody>${rows.map((row, rowIndex) => `<tr><td><strong>${rowIndex + 1}</strong><span>${escapeHtml(displayTimestamp(row.timestamp))}</span></td>${columns.map(([field, label, min, max, step]) => `<td><input class="manual-value" type="number" min="${min}" max="${max}" step="${step}" value="${escapeHtml(row[field])}" data-row-index="${rowIndex}" data-field="${field}" aria-label="${label}, hour ${rowIndex + 1}"></td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  }

  $('#build-manual-window').addEventListener('click', () => {
    clearNotice();
    const match = /^(\d{2})-(\d{2})-(\d{4})$/.exec($('#manual-date').value.trim());
    const time = $('#manual-time').value;
    if (!match) { setNotice('Enter the start date as DD-MM-YYYY, for example 26-10-2026.', 'error'); $('#manual-date').focus(); return; }
    if (!time || !/^\d{2}:00$/.test(time)) { setNotice('Choose a first hour on the hour, for example 13:00.', 'error'); $('#manual-time').focus(); return; }
    if (!$('#dataset-name').value.trim()) { setNotice('Give this data set a name before creating the hourly table.', 'error'); $('#dataset-name').focus(); return; }
    const [, dayText, monthText, yearText] = match;
    const hourText = Number(time.slice(0, 2));
    const start = new Date(Number(yearText), Number(monthText) - 1, Number(dayText), hourText, 0, 0, 0);
    if (start.getFullYear() !== Number(yearText) || start.getMonth() !== Number(monthText) - 1 || start.getDate() !== Number(dayText)) {
      setNotice('That date is not valid. Check the day, month, and year.', 'error'); $('#manual-date').focus(); return;
    }
    const defaults = {
      ambient_temp_c: Number($('#manual-temp').value),
      humidity_pct: Number($('#manual-humidity').value),
      solar_irradiance_wm2: Number($('#manual-solar').value),
    };
    if (!Object.values(defaults).every(Number.isFinite) || defaults.ambient_temp_c < -80 || defaults.ambient_temp_c > 60 || defaults.humidity_pct < 0 || defaults.humidity_pct > 100 || defaults.solar_irradiance_wm2 < 0 || defaults.solar_irradiance_wm2 > 2000) {
      setNotice('Check the default measurement fields: temperature −80–60 °C, humidity 0–100%, and solar 0–2,000 W/m².', 'error'); return;
    }
    invalidatePendingForecast();
    const rows = Array.from({ length: 24 }, (_, index) => {
      const timestamp = new Date(start.getTime() + index * 60 * 60 * 1000);
      return { timestamp: localTimestamp(timestamp), ...defaults };
    });
    setRows(rows, 'Guided manual entry');
    state.manualMode = true;
    renderManualGrid(state.rows);
    $('#dataset-save-status').textContent = 'This 24-hour table is not saved yet.';
    notify('Created 24 hourly rows. Edit any measurement before saving or forecasting.');
  });

  $('#manual-grid').addEventListener('input', event => {
    const input = event.target.closest('.manual-value');
    if (!input) return;
    const row = state.rows[Number(input.dataset.rowIndex)];
    if (!row) return;
    row[input.dataset.field] = input.value === '' ? '' : Number(input.value);
    state.datasetId = null;
    state.inputSource = 'Guided manual entry';
    $('#save-dataset').disabled = state.rows.length !== 24;
    $('#run-data-forecast').disabled = state.rows.length !== 24;
    $('#dataset-save-status').textContent = 'You changed this table; save it again to keep the updates.';
    renderPreview(state.rows);
  });

  async function loadImportedText(dataText, format, sourceName = '') {
    invalidatePendingForecast();
    clearNotice();
    if (!dataText.trim()) { setNotice('Choose a file or paste data before validating.', 'error'); return; }
    const checked = await api('/api/validate', { data_text: dataText, format });
    setRows(checked.rows, `Imported ${format.toUpperCase()}${sourceName ? ` · ${sourceName}` : ''}`);
    state.manualMode = false;
    $('#dataset-save-status').textContent = `Validated ${checked.accepted_rows} rows. Save this data set or generate a forecast.`;
    if (!$('#dataset-name').value.trim() || $('#dataset-name').value === 'My microgrid forecast') {
      $('#dataset-name').value = sourceName ? sourceName.replace(/\.[^.]+$/, '').slice(0, 100) : `Imported microgrid data · ${displayDate(new Date())}`;
    }
    selectInputTab('import');
    notify(`All ${checked.accepted_rows} hourly rows passed validation.`);
  }

  $('#data-file').addEventListener('change', async event => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    const format = file.name.split('.').pop().toLowerCase();
    if (!['csv', 'tsv', 'json'].includes(format)) { setNotice('Choose a .csv, .tsv, or .json file.', 'error'); event.target.value = ''; return; }
    if (file.size > 2_000_000) { setNotice('This file is larger than the 2 MB limit.', 'error'); event.target.value = ''; return; }
    try {
      await loadImportedText(await file.text(), format, file.name);
    } catch (error) {
      state.rows = []; state.datasetId = null; state.inputSource = '';
      $('#row-count').textContent = '0 / 24 rows'; $('#save-dataset').disabled = true; $('#run-data-forecast').disabled = true;
      $('#data-preview').textContent = error.message;
      setNotice(error.message, 'error');
    }
  });
  $('#load-pasted-data').addEventListener('click', async () => {
    try { await loadImportedText($('#data-text').value, $('#data-format').value, 'pasted data'); }
    catch (error) { setNotice(error.message, 'error'); $('#data-preview').textContent = error.message; }
  });

  function makeTemplateRows() {
    const start = new Date(); start.setMinutes(0, 0, 0); start.setHours(start.getHours() + 1);
    return Array.from({ length: 24 }, (_, index) => {
      const timestamp = new Date(start.getTime() + index * 60 * 60 * 1000);
      return { timestamp: localTimestamp(timestamp), ambient_temp_c: 24, humidity_pct: 50, solar_irradiance_wm2: 0 };
    });
  }
  function downloadTemplate(format) {
    const rows = makeTemplateRows();
    let content;
    let mime;
    if (format === 'json') {
      content = JSON.stringify(rows, null, 2); mime = 'application/json';
    } else {
      const delimiter = format === 'tsv' ? '\t' : ',';
      const columns = ['timestamp', 'ambient_temp_c', 'humidity_pct', 'solar_irradiance_wm2'];
      content = [columns.join(delimiter), ...rows.map(row => columns.map(column => String(row[column])).join(delimiter))].join('\r\n');
      mime = format === 'tsv' ? 'text/tab-separated-values' : 'text/csv';
    }
    const anchor = document.createElement('a'); anchor.href = URL.createObjectURL(new Blob([content], { type: `${mime};charset=utf-8` })); anchor.download = `gridsense_template.${format}`; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(anchor.href), 1000);
  }
  $('#download-csv-template').addEventListener('click', () => downloadTemplate('csv'));
  $('#download-tsv-template').addEventListener('click', () => downloadTemplate('tsv'));
  $('#download-json-template').addEventListener('click', () => downloadTemplate('json'));

  async function loadOfficialSample() {
    invalidatePendingForecast();
    clearNotice();
    try {
      const sample = await api('/api/sample');
      setRows(sample.rows, sample.source);
      state.manualMode = false;
      $('#dataset-name').value = `Official sample · ${displayDate(new Date())}`;
      $('#dataset-save-status').textContent = 'Review the sample, then save it or generate a forecast.';
      showView('telemetry'); selectInputTab('sample');
      notify('Loaded 24 official sample rows. Review them, then save or forecast.');
    } catch (error) {
      setNotice(error.message, 'error'); showView('telemetry');
    }
  }
  $('#load-sample').addEventListener('click', loadOfficialSample);

  async function persistCurrentDataset(signal) {
    if (!Array.isArray(state.rows) || state.rows.length !== 24) throw new Error('Prepare exactly 24 hourly rows before saving this data set.');
    if (state.datasetId) return { id: state.datasetId, name: $('#dataset-name').value.trim(), row_count: state.rows.length };
    const name = $('#dataset-name').value.trim();
    const checked = await api('/api/validate', { rows: state.rows, source: state.inputSource }, signal);
    state.rows = checked.rows;
    const saved = await api('/api/datasets', { name, source: state.inputSource || 'Manual entry', rows: state.rows }, signal);
    state.datasetId = saved.id;
    $('#dataset-save-status').textContent = `Saved “${saved.name}” with ${saved.row_count} validated hourly rows.`;
    await refreshSavedItems();
    return saved;
  }
  $('#save-dataset').addEventListener('click', async () => {
    clearNotice();
    try { const saved = await persistCurrentDataset(); notify(`Saved data set “${saved.name}”.`); }
    catch (error) { setNotice(error.message, 'error'); }
  });
  $('#dataset-name').addEventListener('input', () => {
    if (state.datasetId) {
      state.datasetId = null;
      $('#dataset-save-status').textContent = 'The name changed; save this data set again to keep the new name.';
    }
  });

  function renderSavedDatasets() {
    const container = $('#saved-datasets');
    if (!state.savedDatasets.length) { container.innerHTML = '<p class="helper-text">No saved data sets yet. Valid data is stored here when you save it or generate a forecast.</p>'; return; }
    container.innerHTML = state.savedDatasets.map(dataset => `<div class="saved-row"><div><strong>${escapeHtml(dataset.name)}</strong><small>${dataset.row_count} hourly rows · ${escapeHtml(dataset.source)} · ${new Date(dataset.created_at).toLocaleString()}</small></div><div class="saved-actions"><button class="button button-small button-secondary" data-load-dataset="${escapeHtml(dataset.id)}">Load</button><button class="button button-small button-quiet" data-delete-dataset="${escapeHtml(dataset.id)}">Delete</button></div></div>`).join('');
  }
  function renderSavedForecasts() {
    const container = $('#saved-forecasts');
    if (!state.savedForecasts.length) { container.innerHTML = '<p class="helper-text">No forecasts have been saved yet. Completed forecasts appear here and can be reopened later.</p>'; return; }
    container.innerHTML = state.savedForecasts.map(forecast => `<div class="saved-row"><div><strong>${escapeHtml(forecast.dataset_name)}</strong><small>${new Date(forecast.generated_at).toLocaleString()} · peak ${number(forecast.summary.peak_demand_kw, 1)} kW · ${escapeHtml(forecast.model_source)}</small></div><div class="saved-actions"><button class="button button-small button-secondary" data-open-forecast="${escapeHtml(forecast.id)}">Open forecast</button></div></div>`).join('');
  }
  async function refreshSavedItems() {
    try {
      const [datasets, forecasts] = await Promise.all([api('/api/datasets'), api('/api/forecasts')]);
      state.savedDatasets = datasets.datasets || [];
      state.savedForecasts = forecasts.forecasts || [];
      renderSavedDatasets(); renderSavedForecasts();
    } catch (error) {
      $('#saved-datasets').innerHTML = `<p class="helper-text">Saved data is unavailable: ${escapeHtml(error.message)}</p>`;
      $('#saved-forecasts').innerHTML = `<p class="helper-text">Forecast history is unavailable: ${escapeHtml(error.message)}</p>`;
    }
  }
  async function restoreLatestForecast() {
    if (state.result || !state.savedForecasts.length) return;
    try {
      const forecast = await api(`/api/forecasts/${encodeURIComponent(state.savedForecasts[0].id)}`);
      state.result = forecast;
      const rows = forecast.results.map(row => ({ timestamp: row.timestamp, ambient_temp_c: row.ambient_temp_c, humidity_pct: row.humidity_pct, solar_irradiance_wm2: row.solar_irradiance_wm2 }));
      setRows(rows, forecast.input_source || 'Saved forecast input');
      state.datasetId = forecast.dataset_id || null;
      $('#dataset-name').value = forecast.dataset_name || 'Restored forecast input';
      $('#dataset-save-status').textContent = `Restored the saved input for “${forecast.dataset_name}”.`;
      renderForecast(forecast);
      updateSourceBanner(forecast);
    } catch (error) {
      $('#saved-forecasts').insertAdjacentHTML('afterbegin', `<p class="helper-text">Could not restore the latest forecast: ${escapeHtml(error.message)}</p>`);
    }
  }
  $('#saved-datasets').addEventListener('click', async event => {
    const loadButton = event.target.closest('[data-load-dataset]');
    const deleteButton = event.target.closest('[data-delete-dataset]');
    try {
      if (loadButton) {
        const dataset = await api(`/api/datasets/${encodeURIComponent(loadButton.dataset.loadDataset)}`);
        setRows(dataset.rows, dataset.source); state.datasetId = dataset.id; state.manualMode = false;
        $('#dataset-name').value = dataset.name;
        $('#dataset-save-status').textContent = `Loaded saved data set “${dataset.name}”.`;
        showView('telemetry'); selectInputTab('import');
      } else if (deleteButton && window.confirm('Delete this saved data set? Saved forecasts remain available.')) {
        await api(`/api/datasets/${encodeURIComponent(deleteButton.dataset.deleteDataset)}`, null, undefined, 'DELETE');
        await refreshSavedItems();
      }
    } catch (error) { setNotice(error.message, 'error'); }
  });
  $('#saved-forecasts').addEventListener('click', async event => {
    const button = event.target.closest('[data-open-forecast]');
    if (!button) return;
    try {
      const forecast = await api(`/api/forecasts/${encodeURIComponent(button.dataset.openForecast)}`);
      state.result = forecast; renderForecast(forecast); showView('forecast');
      notify(`Opened saved forecast “${forecast.dataset_name}”.`);
    } catch (error) { setNotice(error.message, 'error'); }
  });
  refreshSavedItems().then(restoreLatestForecast);

  $('#clear-data').addEventListener('click', () => {
    invalidatePendingForecast();
    state.rows = []; state.inputSource = ''; state.datasetId = null; state.manualMode = false;
    $('#data-file').value = ''; $('#data-text').value = '';
    $('#row-count').textContent = '0 / 24 rows'; $('#run-data-forecast').disabled = true; $('#save-dataset').disabled = true;
    $('#data-preview').textContent = 'Choose Guided entry, Import data, or Official sample to begin. No forecast will run until a valid 24-hour window is ready.';
    $('#manual-grid').classList.add('empty-grid'); $('#manual-grid').textContent = 'Set a start date and time, then create your table.';
    $('#dataset-save-status').textContent = 'Inputs are saved to this local workspace when you save or generate a forecast.';
    clearNotice();
  });

  function updateSourceBanner(forecast) {
    const isDemo = forecast.model_source.toLowerCase().startsWith('local demo model');
    $('#source-banner').innerHTML = `<span class="banner-icon">i</span><div><strong>${isDemo ? 'Demonstration forecast' : 'QuickML forecast'}</strong><span>${escapeHtml(forecast.dataset_name || forecast.input_source)} · generated ${new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(new Date(forecast.generated_at))}. ${isDemo ? 'Local model trained on supplied official data; not a QuickML prediction.' : 'Inference returned successfully from the configured endpoint.'}</span></div><button class="text-button" data-nav="model">Model health <span>→</span></button>`;
    $('[data-nav="model"]', $('#source-banner')).addEventListener('click', () => showView('model'));
  }

  async function runForecast(sourceButton = null) {
    clearNotice();
    if (!Array.isArray(state.rows) || state.rows.length !== 24) {
      setNotice('No complete data set is ready. Choose Guided entry, Import CSV/TSV/JSON, or Official sample, then create a 24-hour window.', 'error');
      showView('telemetry'); selectInputTab('guided');
      return;
    }
    if (state.activeController) state.activeController.abort();
    const requestId = ++state.requestId;
    const controller = new AbortController();
    state.activeController = controller;
    const timeout = window.setTimeout(() => controller.abort(), 45_000);
    loading(true);
    if (sourceButton) sourceButton.disabled = true;
    try {
      const dataset = await persistCurrentDataset(controller.signal);
      if (requestId !== state.requestId) return;
      const forecast = await api('/api/forecast', { dataset_id: dataset.id }, controller.signal);
      if (requestId !== state.requestId) return;
      state.result = forecast;
      renderForecast(forecast);
      const isDemo = forecast.model_source.toLowerCase().startsWith('local demo model');
      setNotice(`Forecast ready · ${forecast.model_source}${forecast.evaluation ? ` · chronological holdout RMSE ${number(forecast.evaluation.rmse_kw, 2)} kW` : ''}.`, isDemo ? '' : 'success');
      updateSourceBanner(forecast);
      state.inputSource = forecast.input_source;
      await refreshSavedItems();
      showView(sourceButton === $('#run-main') ? 'overview' : 'forecast');
      notify(forecast.summary.forecast_status);
    } catch (error) {
      if (requestId !== state.requestId) return;
      const message = error.name === 'AbortError' ? 'Forecast request timed out. Check the backend or model endpoint and retry.' : error.message;
      const savedMessage = state.datasetId ? ` Your input is saved as “${$('#dataset-name').value.trim()}”.` : '';
      setNotice(`${message}${savedMessage}`, 'error');
      notify(message, 'error');
    } finally {
      window.clearTimeout(timeout);
      if (requestId === state.requestId) { state.activeController = null; loading(false); }
      if (sourceButton) sourceButton.disabled = false;
    }
  }
  $('#run-main').addEventListener('click', event => runForecast(event.currentTarget));
  $('#run-forecast').addEventListener('click', event => runForecast(event.currentTarget));
  $('#run-data-forecast').addEventListener('click', event => runForecast(event.currentTarget));

  function renderForecast(forecast) {
    const rows = forecast.results;
    const summary = forecast.summary;
    $('#metric-peak').textContent = formatDemand(summary.peak_demand_kw, 1);
    $('#metric-average').textContent = formatDemand(summary.average_demand_kw, 1);
    $('#metric-main').textContent = summary.main_grid_hours;
    $('#metric-renewable').textContent = summary.renewable_storage_hours;
    $('#metric-alerts').textContent = summary.critical_alert_count;
    $('#metric-peak-foot').textContent = `${summary.peak_timestamp} · local forecast time`;
    $('#nav-alert-count').textContent = summary.critical_alert_count;
    $('#nav-alert-count').classList.toggle('hidden', !summary.critical_alert_count);
    $('#chart-window-label').textContent = `${rows.length} hourly intervals · kW`;
    $('#forecast-generated-at').textContent = `Generated ${new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'short' }).format(new Date(forecast.generated_at))}`;
    renderChart($('#demand-chart'), rows, false);
    renderChart($('#forecast-chart'), rows, true);
    renderTimeline(rows);
    renderDistribution(rows);
    renderAttention(rows);
    renderTable(rows);
    renderController(rows);
    renderAlerts(rows);
    renderCopilotContext(forecast);
    if (forecast.evaluation) {
      $('#model-rmse').textContent = number(forecast.evaluation.rmse_kw, 2);
      $('#model-mae').textContent = number(forecast.evaluation.mae_kw, 2);
      $('#model-rows').textContent = `${forecast.evaluation.training_rows} / ${forecast.evaluation.holdout_rows}`;
      $('#model-source-value').textContent = `${forecast.evaluation.model_name} · local demo`;
    } else {
      $('#model-rmse').textContent = '—'; $('#model-mae').textContent = '—'; $('#model-rows').textContent = '—';
      $('#model-source-value').textContent = forecast.model_source;
    }
    $('#alert-summary-count').textContent = summary.critical_alert_count ? String(summary.critical_alert_count) : '0';
    $('#alert-summary-status').textContent = summary.forecast_status;
    $('#alert-summary-attention').textContent = String(summary.attention_hours);
    if (state.health && !state.health.model.quickml_configured) $('#connection-label').textContent = 'Demo model active';
  }

  function renderChart(container, rows, large) {
    if (!rows || !rows.length) return;
    const values = rows.map(row => Number(row.target_demand_kw));
    const width = 720, height = large ? 310 : 220;
    const margin = { top: 17, right: 43, bottom: 31, left: 41 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const low = Math.max(0, Math.floor((Math.min(...values, 160) - 20) / 20) * 20);
    const high = Math.ceil((Math.max(...values, 200) + 22) / 20) * 20;
    const x = index => margin.left + index * plotWidth / Math.max(1, rows.length - 1);
    const y = value => margin.top + (high - value) * plotHeight / (high - low || 1);
    const points = rows.map((row, index) => ({ ...row, x: x(index), y: y(Number(row.target_demand_kw)) }));
    const line = points.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ');
    const area = `${line} L${x(rows.length - 1)},${height - margin.bottom} L${x(0)},${height - margin.bottom} Z`;
    const tickValues = Array.from({ length: 5 }, (_, index) => Math.round((low + (high - low) * index / 4) / 10) * 10);
    const yGrid = tickValues.map(value => `<line class="chart-grid-line" x1="${margin.left}" y1="${y(value)}" x2="${width - margin.right}" y2="${y(value)}"/><text class="chart-label" x="${margin.left - 8}" y="${y(value) + 3}" text-anchor="end">${value}</text>`).join('');
    const showIndices = [...new Set([0, Math.floor((rows.length - 1) / 3), Math.floor((rows.length - 1) * 2 / 3), rows.length - 1])];
    const xLabels = showIndices.map(index => `<text class="chart-label" x="${x(index)}" y="${height - 9}" text-anchor="middle">${escapeHtml(rows[index].timestamp.slice(11, 16))}</text>`).join('');
    const threshold = 160 >= low && 160 <= high ? `<line class="chart-threshold" x1="${margin.left}" y1="${y(160)}" x2="${width - margin.right}" y2="${y(160)}"/><text class="chart-label" x="${width - margin.right + 5}" y="${y(160) + 3}">160</text>` : '';
    const critical = `<line class="chart-critical" x1="${margin.left}" y1="${y(200)}" x2="${width - margin.right}" y2="${y(200)}"/><text class="chart-label" x="${width - margin.right + 5}" y="${y(200) + 3}">200</text>`;
    const circles = points.map((point, index) => `<circle class="chart-point${point.critical_overload ? ' chart-alert-point' : ''}" cx="${point.x}" cy="${point.y}" r="${point.critical_overload ? 4 : 3}" tabindex="0" role="button" aria-label="${escapeHtml(point.timestamp)}, ${formatDemand(point.target_demand_kw, 1)} kilowatts, ${escapeHtml(point.power_mode)}${point.critical_overload ? ', critical overload' : ''}" data-index="${index}"/>`).join('');
    container.innerHTML = `<svg class="forecast-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Hourly demand forecast with switching and critical thresholds"><defs><linearGradient id="forecastArea" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="var(--green-strong)" stop-opacity=".19"/><stop offset="100%" stop-color="var(--green-strong)" stop-opacity="0"/></linearGradient></defs>${yGrid}${threshold}${critical}<path class="chart-area" d="${area}"/><path class="chart-line" d="${line}"/>${circles}${xLabels}<text class="chart-axis-title" transform="translate(11 ${height / 2}) rotate(-90)" text-anchor="middle">DEMAND · kW</text></svg><div class="chart-tooltip hidden"></div>`;
    const tooltip = $('.chart-tooltip', container);
    $$('.chart-point', container).forEach(point => {
      const showTip = () => {
        const row = rows[Number(point.dataset.index)];
        tooltip.innerHTML = `<strong>${escapeHtml(row.timestamp)}</strong><span>${formatDemand(row.target_demand_kw, 1)} kW · ${escapeHtml(row.power_mode)}</span>${row.critical_overload ? '<span class="tooltip-alert">Critical overload</span>' : ''}`;
        tooltip.classList.remove('hidden');
        const rect = container.getBoundingClientRect();
        const index = Number(point.dataset.index);
        const left = 41 + index * (rect.width - 84) / Math.max(1, rows.length - 1);
        tooltip.style.left = `${Math.max(0, Math.min(rect.width - 150, left - 55))}px`;
        tooltip.style.top = `${Math.max(0, Math.min(rect.height - 55, point.cy.baseVal.value / height * rect.height - 51))}px`;
      };
      point.addEventListener('pointerenter', showTip);
      point.addEventListener('focus', showTip);
      point.addEventListener('pointerleave', () => tooltip.classList.add('hidden'));
      point.addEventListener('blur', () => tooltip.classList.add('hidden'));
      point.addEventListener('click', showTip);
      point.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); showTip(); } });
    });
  }

  function renderTimeline(rows) {
    $('#mode-timeline').innerHTML = `<div class="timeline">${rows.map((row, index) => `<button class="timeline-cell${row.power_mode === 'Main Grid Mode' ? ' grid-mode' : ''}${row.critical_overload ? ' critical-cell' : ''}" title="${escapeHtml(row.timestamp)} · ${formatDemand(row.target_demand_kw, 1)} kW · ${escapeHtml(row.power_mode)}${row.critical_overload ? ' · Critical overload' : ''}" aria-label="Hour ${index + 1}: ${escapeHtml(row.power_mode)}${row.critical_overload ? ', critical overload' : ''}" data-hour-index="${index}"><span>${escapeHtml(row.timestamp.slice(11, 16))}</span>${row.critical_overload ? '<i></i>' : ''}</button>`).join('')}</div><div class="timeline-axis"><span>${escapeHtml(rows[0].timestamp.slice(11, 16))}</span><span>hourly controller decisions</span><span>${escapeHtml(rows[rows.length - 1].timestamp.slice(11, 16))}</span></div>`;
    $$('.timeline-cell').forEach(button => button.addEventListener('click', () => {
      const row = rows[Number(button.dataset.hourIndex)]; showView('controller');
      notify(`${row.timestamp}: ${row.power_mode}. ${row.reason}${row.critical_overload ? ' Critical overload alert.' : ''}`);
    }));
  }
  function renderDistribution(rows) {
    const values = rows.map(row => Number(row.target_demand_kw));
    const min = Math.floor(Math.min(...values) / 20) * 20;
    const max = Math.ceil(Math.max(...values) / 20) * 20;
    const binsCount = 6;
    const span = Math.max(1, max - min);
    const bins = Array.from({ length: binsCount }, (_, index) => ({ low: min + span * index / binsCount, high: min + span * (index + 1) / binsCount, count: 0 }));
    values.forEach(value => { const idx = Math.min(binsCount - 1, Math.floor((value - min) / span * binsCount)); bins[idx].count++; });
    const highest = Math.max(...bins.map(bin => bin.count), 1);
    $('#distribution-chart').innerHTML = `<div class="histogram">${bins.map(bin => `<div class="hist-bin" style="height:${Math.max(5, bin.count / highest * 100)}%" title="${Math.round(bin.low)}–${Math.round(bin.high)} kW · ${bin.count} hours"><span>${Math.round(bin.low)}</span></div>`).join('')}</div><div class="histogram-label"><span>Demand interval · kW</span><span>${values.length} forecast hours</span></div>`;
  }
  function renderAttention(rows) {
    const attention = rows.filter(row => row.critical_overload || Number(row.target_demand_kw) > 160).sort((a, b) => Number(b.critical_overload) - Number(a.critical_overload) || b.target_demand_kw - a.target_demand_kw).slice(0, 4);
    if (!attention.length) { $('#attention-list').textContent = 'No forecast hours exceed the switching threshold.'; return; }
    $('#attention-list').innerHTML = `<div class="attention-list">${attention.map(row => `<button class="attention-row" data-alert-hour="${escapeHtml(row.timestamp)}"><span class="attention-mark${row.critical_overload ? ' critical' : ''}"></span><div><strong>${escapeHtml(row.timestamp)}</strong><small>${row.critical_overload ? 'Critical overload' : 'Renewable threshold exceeded'}</small></div><span class="attention-value">${formatDemand(row.target_demand_kw, 1)} kW</span></button>`).join('')}</div>`;
    $$('[data-alert-hour]').forEach(button => button.addEventListener('click', () => { showView('forecast'); $('#forecast-search').value = button.dataset.alertHour; $('#forecast-search').dispatchEvent(new Event('input')); }));
  }
  function renderTable(rows) {
    const query = $('#forecast-search').value.trim().toLowerCase();
    const filtered = rows.filter(row => !query || row.timestamp.toLowerCase().includes(query) || String(row.target_demand_kw).includes(query) || row.power_mode.toLowerCase().includes(query));
    filtered.sort((a, b) => {
      const left = a[state.sortKey], right = b[state.sortKey];
      const comparison = state.sortKey === 'target_demand_kw' ? Number(left) - Number(right) : String(left).localeCompare(String(right));
      return comparison * state.sortDirection;
    });
    $('#forecast-rows').innerHTML = filtered.length ? filtered.map(row => `<tr><td>${escapeHtml(row.timestamp)}</td><td><strong>${formatDemand(row.target_demand_kw, 2)} kW</strong></td><td><span class="mode-pill ${row.power_mode === 'Main Grid Mode' ? 'main-grid' : 'renewable'}">${escapeHtml(row.power_mode)}</span></td><td><span class="overload-pill ${row.critical_overload ? 'critical' : 'clear'}">${row.critical_overload ? 'Critical alert' : 'Clear'}</span></td><td class="reason-cell">${escapeHtml(row.reason)}</td></tr>`).join('') : '<tr><td class="empty-cell" colspan="5">No forecast hours match this filter.</td></tr>';
  }
  $('#forecast-search').addEventListener('input', () => { if (state.result) renderTable(state.result.results); });
  $$('.sort-button').forEach(button => button.addEventListener('click', () => {
    const key = button.dataset.sort;
    state.sortDirection = state.sortKey === key ? -state.sortDirection : 1; state.sortKey = key;
    if (state.result) renderTable(state.result.results);
  }));
  $('#table-toggle').addEventListener('click', () => { showView('forecast'); $('#forecast-rows').scrollIntoView({ behavior: 'smooth', block: 'center' }); });

  function renderController(rows) {
    $('#controller-list').innerHTML = `<div class="controller-header"><span>FORECAST HOUR</span><span>DEMAND</span><span>DECISION REASON</span><span>OVERLOAD</span></div><div class="controller-list">${rows.map(row => `<div class="controller-row"><span class="controller-time">${escapeHtml(row.timestamp)}</span><span><strong class="controller-demand">${formatDemand(row.target_demand_kw, 2)} kW</strong><br><span class="mode-pill ${row.power_mode === 'Main Grid Mode' ? 'main-grid' : 'renewable'}">${escapeHtml(row.power_mode)}</span></span><span class="controller-reason">${escapeHtml(row.reason)}</span><span class="${row.critical_overload ? 'controller-alert' : 'muted-label'}">${row.critical_overload ? '● Critical alert' : '— Clear'}</span></div>`).join('')}</div>`;
  }
  function renderAlerts(rows) {
    const filter = $('#alert-filter').value;
    let list = rows;
    if (filter === 'critical') list = rows.filter(row => row.critical_overload);
    if (filter === 'attention') list = rows.filter(row => row.critical_overload || Number(row.target_demand_kw) > 160);
    if (!list.length) { $('#alert-list').textContent = filter === 'critical' ? 'No critical overloads in this forecast.' : 'No forecast hours match this filter.'; return; }
    $('#alert-list').innerHTML = `<div class="alert-events">${list.map(row => `<article class="alert-event"><span class="event-hour">${escapeHtml(row.timestamp.slice(11, 16))}</span><div class="event-body"><strong>${row.critical_overload ? 'Critical overload alert' : Number(row.target_demand_kw) > 160 ? 'Renewable threshold exceeded' : 'Main grid mode'}</strong><small>${escapeHtml(row.timestamp)} · ${escapeHtml(row.reason)}</small></div><span class="event-demand">${formatDemand(row.target_demand_kw, 2)} kW</span></article>`).join('')}</div>`;
  }
  $('#alert-filter').addEventListener('change', () => { if (state.result) renderAlerts(state.result.results); });

  function renderCopilotContext(forecast) {
    const s = forecast.summary;
    $('#copilot-context-content').innerHTML = `<div class="context-stat"><span>Forecast hours</span><strong>${s.row_count}</strong></div><div class="context-stat"><span>Peak demand</span><strong>${formatDemand(s.peak_demand_kw, 1)} kW</strong></div><div class="context-stat"><span>Peak timestamp</span><strong>${escapeHtml(s.peak_timestamp)}</strong></div><div class="context-stat"><span>Renewable mode</span><strong>${s.renewable_storage_hours} hours</strong></div><div class="context-stat"><span>Critical alerts</span><strong>${s.critical_alert_count}</strong></div><div class="context-stat"><span>Forecast source</span><strong>${escapeHtml(forecast.model_source)}</strong></div>`;
  }
  function copilotAnswer(question) {
    if (!state.result) return 'There is no forecast loaded yet. Add 24 hourly feature rows or load the official sample and generate a forecast first.';
    const { results, summary } = state.result;
    const lower = question.toLowerCase();
    const alerts = results.filter(row => row.critical_overload);
    const attention = results.filter(row => row.critical_overload || Number(row.target_demand_kw) > 160);
    if (lower.includes('summar') || lower.includes('overview') || lower.includes('forecast')) {
      return `Across ${summary.row_count} forecast hours, the peak is ${formatDemand(summary.peak_demand_kw, 1)} kW at ${summary.peak_timestamp}; average demand is ${formatDemand(summary.average_demand_kw, 1)} kW. The controller assigns ${summary.main_grid_hours} hours to Main Grid Mode and ${summary.renewable_storage_hours} to Renewable Storage Mode. ${summary.critical_alert_count ? `${summary.critical_alert_count} critical overload alert(s) need review.` : 'There are no critical overload alerts.'} These are point estimates; uncertainty is not quantified.`;
    }
    if (lower.includes('attention') || lower.includes('risk') || lower.includes('overload') || lower.includes('alert')) {
      if (alerts.length) return `${alerts.length} hour(s) meet the independent ≥200 kW critical-alert rule: ${alerts.map(row => `${row.timestamp} (${formatDemand(row.target_demand_kw, 1)} kW)`).join(', ')}. ${attention.length} hour(s) exceed 160 kW or trigger an overload, so review those forecast rows.`;
      if (attention.length) return `${attention.length} hour(s) are assigned Renewable Storage Mode because demand exceeds 160 kW or the timestamp is within 18:00–22:00. No row reaches the 200 kW critical-alert threshold.`;
      return 'No forecast hour exceeds 160 kW and none reaches the critical-alert threshold. Evening-window hours still use Renewable Storage Mode if present.';
    }
    if (lower.includes('why') || lower.includes('mode') || lower.includes('chang')) {
      const evening = results.filter(row => Number(row.timestamp.slice(11, 13)) >= 18 && Number(row.timestamp.slice(11, 13)) <= 22);
      const demandTriggers = results.filter(row => Number(row.target_demand_kw) > 160 && !(Number(row.timestamp.slice(11, 13)) >= 18 && Number(row.timestamp.slice(11, 13)) <= 22));
      const examples = [...demandTriggers.slice(0, 2), ...evening.slice(0, 2)];
      return examples.length ? `The controller selects Renewable Storage Mode when demand is strictly above 160 kW or the hour is 18:00–22:00 inclusive. For example: ${examples.map(row => `${row.timestamp} (${formatDemand(row.target_demand_kw, 1)} kW): ${row.reason}`).join('; ')} Main Grid Mode applies at ≤160 kW outside that window.` : 'All forecast hours meet the Main Grid Mode condition: demand is ≤160 kW and the timestamp is outside 18:00–22:00.';
    }
    if (lower.includes('peak') || lower.includes('highest')) return `The highest forecast demand is ${formatDemand(summary.peak_demand_kw, 1)} kW at ${summary.peak_timestamp}. It is a model estimate, not a measured reading.`;
    return 'I can summarize this forecast, list hours needing attention, explain the power-mode rules, or identify the peak. I only use the current forecast and the official thresholds; I do not infer weather causes or live infrastructure state.';
  }
  function addMessage(text, fromUser = false) {
    const message = document.createElement('div');
    message.className = fromUser ? 'user-message' : 'assistant-message';
    if (!fromUser) { const icon = document.createElement('span'); icon.className = 'message-avatar'; icon.textContent = '✳'; message.append(icon); }
    const paragraph = document.createElement('p'); paragraph.textContent = text; message.append(paragraph); $('#copilot-messages').append(message); $('#copilot-messages').scrollTop = $('#copilot-messages').scrollHeight;
  }
  $('#copilot-form').addEventListener('submit', event => {
    event.preventDefault(); const input = $('#copilot-input'); const question = input.value.trim(); if (!question) return;
    addMessage(question, true); addMessage(copilotAnswer(question)); input.value = '';
  });
  $$('.prompt-suggestions button').forEach(button => button.addEventListener('click', () => { $('#copilot-input').value = button.dataset.prompt; $('#copilot-form').requestSubmit(); }));

  function csvCell(value) { const text = String(value ?? ''); return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text; }
  function downloadCsv(filename, rows, columns) {
    const csv = [columns.join(','), ...rows.map(row => columns.map(column => csvCell(row[column])).join(','))].join('\r\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' }); const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  $('#export-forecast').addEventListener('click', () => {
    if (!state.result) { notify('Generate a forecast before exporting.'); return; }
    downloadCsv('gridsense_predictions.csv', state.result.results, ['timestamp', 'target_demand_kw']);
  });
  $('#export-details').addEventListener('click', () => {
    if (!state.result) { notify('Generate a forecast before exporting.'); return; }
    downloadCsv('gridsense_decision_report.csv', state.result.results, ['timestamp', 'target_demand_kw', 'power_mode', 'critical_overload', 'reason']);
  });
})();
