import './style.css';
import '@fontsource/open-runde/400.css';
import '@fontsource/open-runde/500.css';
import '@fontsource/open-runde/600.css';
import '@fontsource/open-runde/700.css';

import {
    GetAccountReport,
    GetAppState,
    GetMCPStatus,
    ListAccounts,
    ListActivity,
    LoginSession,
    OpenExternalURL,
    ReadScreenshot,
    SaveSettings,
    ScanAccount,
    SearchFormat,
    SetMCPPort,
    StartMCPServer,
    StopMCPServer,
    CopyMCPConfig,
} from '../wailsjs/go/main/App';

const state = {
    activeScreen: 'activity',
    appState: null,
    accounts: [],
    searchResults: [],
    report: null,
    scrapeBusy: false,
    mcpStatus: null,
    activity: [],
    activitySocket: null,
};

const numberFormatter = new Intl.NumberFormat();
const percentFormatter = new Intl.NumberFormat(undefined, {
    style: 'percent',
    maximumFractionDigits: 0,
});

const screenTitles = {
    activity: 'Activity',
    login: 'Session',
    search: 'Search',
    accounts: 'Accounts',
    report: 'Account report',
    mcp: 'MCP server',
    settings: 'Settings',
};

const elements = {
    error: document.querySelector('#app-error'),
    status: document.querySelector('#app-status'),
    queueDot: document.querySelector('#queue-dot'),
    queueLabel: document.querySelector('#queue-label'),
    workspaceTitle: document.querySelector('#workspace-title'),
    sessionBadge: document.querySelector('#session-badge'),
    sessionDescription: document.querySelector('#session-description'),
    sessionPath: document.querySelector('#session-path'),
    searchBody: document.querySelector('#search-results-body'),
    searchEmpty: document.querySelector('#search-empty'),
    searchTableWrap: document.querySelector('#search-table-wrap'),
    searchSummary: document.querySelector('#search-summary'),
    accountsBody: document.querySelector('#accounts-body'),
    accountsEmpty: document.querySelector('#accounts-empty'),
    accountsTableWrap: document.querySelector('#accounts-table-wrap'),
    accountsSummary: document.querySelector('#accounts-summary'),
    reportEmpty: document.querySelector('#report-empty'),
    reportContent: document.querySelector('#report-content'),
    reportUsername: document.querySelector('#report-username'),
    reportMetrics: document.querySelector('#report-metrics'),
    reportSummary: document.querySelector('#report-summary'),
    reportPostsBody: document.querySelector('#report-posts-body'),
    mcpTitle: document.querySelector('#mcp-status-title'),
    mcpBadge: document.querySelector('#mcp-status-badge'),
    mcpDescription: document.querySelector('#mcp-status-description'),
    mcpEndpoint: document.querySelector('#mcp-endpoint'),
    mcpOrb: document.querySelector('#mcp-orb'),
    mcpStart: document.querySelector('#mcp-start'),
    mcpStop: document.querySelector('#mcp-stop'),
    mcpPort: document.querySelector('#mcp-port'),
    mcpError: document.querySelector('#mcp-error'),
    codexConfig: document.querySelector('#codex-config'),
    claudeConfig: document.querySelector('#claude-config'),
    activityList: document.querySelector('#activity-list'),
    activityLiveDot: document.querySelector('#activity-live-dot'),
    activityLiveLabel: document.querySelector('#activity-live-label'),
};

function friendlyError(error) {
    if (typeof error === 'string') return error;
    return error?.message || String(error || 'Unknown error');
}

function setStatus(message) {
    elements.status.textContent = '';
    window.requestAnimationFrame(() => {
        elements.status.textContent = message;
    });
}

function showError(error) {
    elements.error.textContent = friendlyError(error);
    elements.error.hidden = false;
}

function clearError() {
    elements.error.textContent = '';
    elements.error.hidden = true;
    document.querySelectorAll('[aria-describedby="app-error"]').forEach((field) => {
        field.removeAttribute('aria-describedby');
    });
}

function markFieldError(field, message) {
    field.setAttribute('aria-invalid', 'true');
    field.setAttribute('aria-describedby', 'app-error');
    showError(message);
    field.focus();
}

function escapeHTML(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function postLink(rawURL, accessibleLabel = 'Open post on TikTok') {
    try {
        const parsed = new URL(rawURL);
        if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') throw new Error('Unsupported protocol');
        return `<a class="external-link" href="${escapeHTML(parsed.href)}" target="_blank" rel="noreferrer" aria-label="${escapeHTML(accessibleLabel)}">Open post</a>`;
    } catch {
        return '<span class="unavailable">Unavailable</span>';
    }
}

function activateScreen(screenName, moveFocus = true) {
    clearError();
    state.activeScreen = screenName;
    elements.workspaceTitle.textContent = screenTitles[screenName] || 'Workspace';
    document.querySelectorAll('[data-screen-panel]').forEach((panel) => {
        panel.hidden = panel.dataset.screenPanel !== screenName;
    });
    document.querySelectorAll('[data-screen]').forEach((button) => {
        const active = button.dataset.screen === screenName;
        button.classList.toggle('is-active', active);
        if (active) button.setAttribute('aria-current', 'page');
        else button.removeAttribute('aria-current');
    });
    if (moveFocus) {
        document.querySelector(`#screen-${screenName} h1`)?.focus();
    }
    if (screenName === 'mcp') refreshMCPStatus();
    if (screenName === 'activity') {
        loadActivity();
        refreshMCPStatus();
    } else {
        closeActivitySocket();
    }
}

function renderMCPStatus() {
    const status = state.mcpStatus;
    if (!status) return;
    const running = Boolean(status.running);
    elements.mcpTitle.textContent = running ? 'Server running' : 'Server stopped';
    elements.mcpBadge.textContent = running ? 'Running' : 'Stopped';
    elements.mcpBadge.className = `badge ${running ? 'badge-active' : 'badge-neutral'}`;
    elements.mcpDescription.textContent = running
        ? `Ready for local agent connections${status.pid ? ` · PID ${status.pid}` : ''}. It will restart when the app opens.`
        : 'Start the server when you want an agent to use Comet.';
    elements.mcpEndpoint.textContent = status.url;
    elements.mcpOrb.classList.toggle('is-running', running);
    elements.mcpStart.disabled = running;
    elements.mcpStop.disabled = !running;
    elements.mcpPort.disabled = running;
    elements.mcpPort.value = status.port;
    elements.codexConfig.textContent = `[mcp_servers.comet]\nurl = "${status.url}"`;
    elements.claudeConfig.textContent = `claude mcp add --transport http --scope user comet ${status.url}`;
    elements.mcpError.textContent = status.error || '';
    elements.mcpError.hidden = !status.error;
}

function formatActivityTime(value) {
    if (!value) return '—';
    try { return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch { return value; }
}

function renderActivity() {
    if (!elements.activityList) return;
    if (!state.activity.length) {
        elements.activityList.innerHTML = '<div class="card empty-state activity-empty"><strong>No activity yet</strong><span>Start the MCP server, then run a tool from Codex or this app.</span></div>';
        return;
    }
    elements.activityList.innerHTML = state.activity.map((entry) => {
        const args = escapeHTML(JSON.stringify(entry.args || {}, null, 2));
        const reason = entry.reason ? `<p class="activity-reason">${escapeHTML(entry.reason)}</p>` : '';
        const screenshot = entry.screenshot_path ? `<div class="activity-screenshot" data-screenshot-path="${escapeHTML(entry.screenshot_path)}"><span>Loading evidence…</span></div>` : '';
        return `<details class="card activity-card ${escapeHTML(entry.status || '')}" data-activity-id="${entry.id}">
            <summary><span class="activity-tool">${escapeHTML(entry.tool_name)}</span><span class="activity-summary">${escapeHTML(entry.result_summary || 'Working…')}</span><span class="badge activity-badge ${escapeHTML(entry.status || '')}">${escapeHTML(entry.status || 'unknown')}</span><time>${formatActivityTime(entry.started_at)}</time></summary>
            <div class="activity-detail">${reason}${screenshot}<pre>${args}</pre>${entry.result_summary ? `<p>${escapeHTML(entry.result_summary)}</p>` : ''}</div>
        </details>`;
    }).join('');
    document.querySelectorAll('[data-screenshot-path]').forEach(async (element) => {
        try { element.innerHTML = `<img src="${await ReadScreenshot(element.dataset.screenshotPath)}" alt="TikTok page captured during scrape">`; } catch { element.textContent = 'Screenshot unavailable'; }
    });
}

async function loadActivity() {
    try { state.activity = await ListActivity(100); renderActivity(); } catch (error) { showError(error); }
}

function closeActivitySocket() {
    if (state.activitySocket) state.activitySocket.close();
    state.activitySocket = null;
}

function connectActivitySocket() {
    closeActivitySocket();
    const status = state.mcpStatus;
    if (!status?.running || !window.WebSocket) {
        elements.activityLiveLabel.textContent = status?.running ? 'WebSocket unavailable' : 'Start MCP to watch live';
        elements.activityLiveDot?.classList.remove('is-busy');
        return;
    }
    const endpoint = status.url.replace(/^http/, 'ws').replace(/\/mcp\/$/, '/events');
    const socket = new WebSocket(endpoint);
    state.activitySocket = socket;
    socket.onopen = () => { elements.activityLiveLabel.textContent = 'Live'; elements.activityLiveDot?.classList.add('is-busy'); };
    socket.onmessage = (event) => {
        try {
            const entry = JSON.parse(event.data);
            const index = state.activity.findIndex((item) => item.id === entry.id);
            if (index >= 0) state.activity[index] = entry; else state.activity.unshift(entry);
            state.activity.sort((a, b) => b.id - a.id);
            renderActivity();
        } catch { /* ignore malformed event */ }
    };
    socket.onclose = () => { elements.activityLiveLabel.textContent = 'Disconnected'; elements.activityLiveDot?.classList.remove('is-busy'); };
}

async function refreshMCPStatus() {
    try {
        state.mcpStatus = await GetMCPStatus();
        renderMCPStatus();
        if (state.activeScreen === 'activity') connectActivitySocket();
    } catch (error) {
        elements.mcpError.textContent = friendlyError(error);
        elements.mcpError.hidden = false;
    }
}

function setScrapeBusy(busy, label = '') {
    state.scrapeBusy = busy;
    document.querySelectorAll('.scrape-action').forEach((button) => {
        button.disabled = busy;
        button.setAttribute('aria-busy', String(busy));
    });
    elements.queueDot.classList.toggle('is-busy', busy);
    elements.queueLabel.textContent = busy ? label : 'Scrape queue ready';
}

async function runScrape(label, action) {
    if (state.scrapeBusy) {
        setStatus('A scrape is already running. Try again when it finishes.');
        return null;
    }
    clearError();
    setScrapeBusy(true, label);
    setStatus(label);
    try {
        return await action();
    } catch (error) {
        showError(error);
        setStatus(`Unable to complete scrape. ${friendlyError(error)}`);
        return null;
    } finally {
        setScrapeBusy(false);
    }
}

function updateSessionStatus() {
    if (!state.appState) return;
    const exists = state.appState.session_exists;
    elements.sessionBadge.textContent = exists ? 'Authenticated' : 'Anonymous';
    elements.sessionBadge.className = `badge ${exists ? 'badge-success' : 'badge-neutral'}`;
    elements.sessionDescription.textContent = exists
        ? 'Your saved storage state is ready and will be reused by future scrapes.'
        : 'No session is saved. Scrapes stay anonymous until you sign in.';
    elements.sessionPath.textContent = state.appState.settings.session_path;
}

function populateSettings() {
    if (!state.appState) return;
    const settings = state.appState.settings;
    document.querySelector('#min-delay').value = settings.min_delay_seconds;
    document.querySelector('#max-delay').value = settings.max_delay_seconds;
    document.querySelector('#cache-path').value = settings.cache_db_path;
    document.querySelector('#session-file-path').value = settings.session_path;
    document.querySelector('#settings-file-note').textContent = `Saved in ${state.appState.settings_path}`;
    document.querySelector('#project-root').textContent = state.appState.project_root;
    document.querySelector('#python-path').textContent = state.appState.python_path;
}

function renderSearchResults() {
    const posts = state.searchResults || [];
    elements.searchEmpty.hidden = posts.length > 0;
    elements.searchTableWrap.hidden = posts.length === 0;
    elements.searchSummary.textContent = posts.length
        ? `${numberFormatter.format(posts.length)} posts returned and cached.`
        : 'Run a search to see posts.';
    elements.searchBody.innerHTML = posts.map((post) => `
        <tr>
            <td><span class="account-name">@${escapeHTML(post.username || 'unknown')}</span></td>
            <td class="number-cell">${numberFormatter.format(post.view_count || 0)}</td>
            <td class="caption-cell">${escapeHTML(post.caption || 'No caption')}</td>
            <td>${postLink(post.url, `Open post by @${post.username || 'unknown'} on TikTok`)}</td>
        </tr>
    `).join('');
}

function thresholdValues() {
    return {
        minViews: Math.max(0, Number(document.querySelector('#min-views').value) || 0),
        minPosts: Math.max(0, Number(document.querySelector('#min-posts').value) || 0),
        maxShare: Math.min(1, Math.max(0, Number(document.querySelector('#max-share').value) || 0)),
        passingOnly: document.querySelector('#passing-only').checked,
    };
}

function accountPasses(account, thresholds) {
    if (account.posts_last_30d < thresholds.minPosts) return false;
    if (account.total_views_last_30d < thresholds.minViews) return false;
    return account.total_views_last_30d === 0 || account.max_single_post_share <= thresholds.maxShare;
}

function renderAccounts() {
    const thresholds = thresholdValues();
    const evaluated = (state.accounts || []).map((account) => ({
        ...account,
        passes: accountPasses(account, thresholds),
    }));
    const passingCount = evaluated.filter((account) => account.passes).length;
    const visible = thresholds.passingOnly
        ? evaluated.filter((account) => account.passes)
        : evaluated;

    elements.accountsSummary.textContent = `${numberFormatter.format(passingCount)} of ${numberFormatter.format(evaluated.length)} accounts pass the current thresholds.`;
    elements.accountsEmpty.hidden = visible.length > 0;
    elements.accountsTableWrap.hidden = visible.length === 0;
    if (!evaluated.length) {
        elements.accountsEmpty.querySelector('strong').textContent = 'No cached accounts yet';
        elements.accountsEmpty.querySelector('span').textContent = 'Search a keyword or scan an account to populate this table.';
    } else if (!visible.length) {
        elements.accountsEmpty.querySelector('strong').textContent = 'No accounts pass these thresholds';
        elements.accountsEmpty.querySelector('span').textContent = 'Adjust the filters or show all cached accounts.';
    }
    elements.accountsBody.innerHTML = visible.map((account) => `
        <tr>
            <td><button class="table-link account-report-link" type="button" data-username="${escapeHTML(account.username)}">@${escapeHTML(account.username)}</button></td>
            <td class="number-cell">${numberFormatter.format(account.posts_last_30d)}</td>
            <td class="number-cell">${numberFormatter.format(account.total_views_last_30d)}</td>
            <td class="number-cell">${percentFormatter.format(account.max_single_post_share || 0)}</td>
            <td><span class="badge ${account.passes ? 'badge-success' : 'badge-neutral'}">${account.passes ? 'Passes' : 'Does not pass'}</span></td>
        </tr>
    `).join('');
}

async function loadAccounts(announce = false) {
    try {
        state.accounts = await ListAccounts();
        renderAccounts();
        if (announce) setStatus(`Loaded ${state.accounts.length} cached accounts.`);
    } catch (error) {
        showError(error);
    }
}

function renderReport() {
    const report = state.report;
    elements.reportEmpty.hidden = Boolean(report);
    elements.reportContent.hidden = !report;
    if (!report) return;

    const account = report.account;
    const posts = report.top_posts || [];
    elements.reportUsername.textContent = `@${account.username}`;
    elements.reportMetrics.innerHTML = `
        <div class="metric"><span>Posts / 30d</span><strong>${numberFormatter.format(account.posts_last_30d)}</strong></div>
        <div class="metric"><span>Views / 30d</span><strong>${numberFormatter.format(account.total_views_last_30d)}</strong></div>
        <div class="metric"><span>Average views</span><strong>${numberFormatter.format(Math.round(account.avg_views_per_post || 0))}</strong></div>
        <div class="metric"><span>Max post share</span><strong>${percentFormatter.format(account.max_single_post_share || 0)}</strong></div>
    `;
    elements.reportSummary.textContent = `${numberFormatter.format(posts.length)} cached posts, sorted by views.`;
    elements.reportPostsBody.innerHTML = posts.map((post) => {
        const format = post.is_slideshow
            ? `Slideshow · ${numberFormatter.format(post.image_count || 0)} slides`
            : 'Video';
        return `
            <tr>
                <td class="number-cell">${numberFormatter.format(post.view_count || 0)}</td>
                <td>${escapeHTML(format)}</td>
                <td class="caption-cell">${escapeHTML(post.caption || 'No caption')}</td>
                <td>${postLink(post.url, `Open post by @${account.username} on TikTok`)}</td>
            </tr>
        `;
    }).join('');
}

async function openReport(username) {
    clearError();
    setStatus(`Loading report for @${username}.`);
    try {
        state.report = await GetAccountReport(username);
        renderReport();
        activateScreen('report');
        setStatus(`Loaded report for @${username}.`);
    } catch (error) {
        showError(error);
    }
}

async function initialise() {
    setStatus('Loading local settings and cache.');
    try {
        state.appState = await GetAppState();
        updateSessionStatus();
        populateSettings();
        await refreshMCPStatus();
        await loadAccounts();
        await loadActivity();
        setStatus('Comet is ready.');
    } catch (error) {
        showError(error);
        setStatus('Unable to load the application.');
    }
}

document.querySelectorAll('[data-screen]').forEach((button) => {
    button.addEventListener('click', () => activateScreen(button.dataset.screen));
});

document.querySelectorAll('[data-go-to]').forEach((button) => {
    button.addEventListener('click', () => activateScreen(button.dataset.goTo));
});

document.querySelector('#login-button').addEventListener('click', async () => {
    const result = await runScrape('Waiting for TikTok login in the browser', LoginSession);
    if (!result) return;
    state.appState = await GetAppState();
    updateSessionStatus();
    populateSettings();
    setStatus('TikTok session saved. Future scrapes will reuse it.');
});

document.querySelector('#search-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const keyword = document.querySelector('#search-keyword');
    if (!keyword.value.trim()) {
        markFieldError(keyword, 'Enter a keyword to search.');
        return;
    }
    keyword.removeAttribute('aria-invalid');
    const maxResults = Number(document.querySelector('#search-limit').value) || 20;
    const result = await runScrape(`Searching TikTok for ${keyword.value.trim()}`, () => SearchFormat(keyword.value.trim(), maxResults));
    if (!result) return;
    state.searchResults = result.posts || [];
    renderSearchResults();
    await loadAccounts();
    setStatus(`Search complete. ${result.count} posts were returned.`);
});

document.querySelector('#scan-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const username = document.querySelector('#scan-username');
    if (!username.value.trim()) {
        markFieldError(username, 'Enter an account username.');
        return;
    }
    username.removeAttribute('aria-invalid');
    const cleanUsername = username.value.trim().replace(/^@/, '');
    const maxResults = Number(document.querySelector('#scan-limit').value) || 30;
    const result = await runScrape(`Scanning @${cleanUsername}`, () => ScanAccount(cleanUsername, maxResults));
    if (!result) return;
    await loadAccounts();
    setStatus(`Account scan complete. ${result.count} posts were returned for @${cleanUsername}.`);
});

document.querySelector('#refresh-accounts').addEventListener('click', () => loadAccounts(true));

['#min-views', '#min-posts', '#max-share', '#passing-only'].forEach((selector) => {
    document.querySelector(selector).addEventListener('input', renderAccounts);
});

document.querySelector('#settings-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    clearError();
    const settings = {
        min_delay_seconds: Number(document.querySelector('#min-delay').value),
        max_delay_seconds: Number(document.querySelector('#max-delay').value),
        cache_db_path: document.querySelector('#cache-path').value.trim(),
        session_path: document.querySelector('#session-file-path').value.trim(),
    };
    if (settings.max_delay_seconds < settings.min_delay_seconds) {
        const maximum = document.querySelector('#max-delay');
        markFieldError(maximum, 'Set the maximum delay equal to or greater than the minimum delay.');
        return;
    }
    try {
        await SaveSettings(settings);
        state.appState = await GetAppState();
        populateSettings();
        updateSessionStatus();
        await loadAccounts();
        setStatus('Settings saved.');
    } catch (error) {
        showError(error);
    }
});

document.querySelector('#report-rescan').addEventListener('click', async () => {
    const username = state.report?.account?.username;
    if (!username) return;
    const result = await runScrape(`Scanning @${username}`, () => ScanAccount(username, 30));
    if (!result) return;
    await loadAccounts();
    await openReport(username);
});

elements.mcpStart.addEventListener('click', async () => {
    elements.mcpStart.disabled = true;
    elements.mcpStart.textContent = 'Starting…';
    elements.mcpError.hidden = true;
    try {
        state.mcpStatus = await StartMCPServer();
        renderMCPStatus();
        setStatus(`MCP server running on ${state.mcpStatus.url}.`);
    } catch (error) {
        elements.mcpError.textContent = friendlyError(error);
        elements.mcpError.hidden = false;
    } finally {
        elements.mcpStart.textContent = 'Start server';
        await refreshMCPStatus();
    }
});

elements.mcpStop.addEventListener('click', async () => {
    elements.mcpStop.disabled = true;
    elements.mcpStop.textContent = 'Stopping…';
    try {
        state.mcpStatus = await StopMCPServer();
        renderMCPStatus();
        setStatus('MCP server stopped.');
    } catch (error) {
        elements.mcpError.textContent = friendlyError(error);
        elements.mcpError.hidden = false;
    } finally {
        elements.mcpStop.textContent = 'Stop server';
        await refreshMCPStatus();
    }
});

document.querySelector('#mcp-port-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
        state.mcpStatus = await SetMCPPort(Number(elements.mcpPort.value));
        renderMCPStatus();
        setStatus(`MCP port saved as ${state.mcpStatus.port}.`);
    } catch (error) {
        elements.mcpError.textContent = friendlyError(error);
        elements.mcpError.hidden = false;
    }
});

document.querySelectorAll('.copy-config').forEach((button) => {
    button.addEventListener('click', async () => {
        const original = button.textContent;
        try {
            await CopyMCPConfig(button.dataset.client);
            button.textContent = 'Copied';
            setStatus(`${button.dataset.client === 'codex' ? 'Codex' : 'Claude Code'} configuration copied.`);
            window.setTimeout(() => { button.textContent = original; }, 1600);
        } catch (error) {
            elements.mcpError.textContent = friendlyError(error);
            elements.mcpError.hidden = false;
        }
    });
});

document.addEventListener('click', async (event) => {
    const reportButton = event.target.closest('.account-report-link');
    if (reportButton) {
        await openReport(reportButton.dataset.username);
        return;
    }
    const link = event.target.closest('.external-link');
    if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    try {
        await OpenExternalURL(link.href);
    } catch (error) {
        showError(error);
    }
});

['#search-keyword', '#scan-username', '#max-delay'].forEach((selector) => {
    document.querySelector(selector).addEventListener('input', (event) => {
        if (event.currentTarget.getAttribute('aria-invalid') !== 'true') return;
        event.currentTarget.removeAttribute('aria-invalid');
        clearError();
    });
});

renderSearchResults();
renderReport();
initialise();

window.setInterval(() => {
    if (state.activeScreen === 'mcp') refreshMCPStatus();
}, 2000);
