const BACKEND = window.location.origin;

const messagesDiv = document.getElementById('messages');
const questionInput = document.getElementById('question-input');
const welcomeDiv = document.getElementById('welcome');
const docList = document.getElementById('doc-list');

let currentChatId = null;
let currentUser = null; // Object { name, email, employee_id, role, department }
let sessionToken = null;

// ---- LOGIN ----
async function login() {
    var username = document.getElementById('username').value.trim();

    if (!username) {
        document.getElementById('login-error').innerText = 'Please enter your corporate email address.';
        return;
    }

    try {
        var res = await fetch(BACKEND + '/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username })
        });
        var data = await res.json();

        if (data.success) {
            currentUser = data.user;
            sessionToken = data.session_token;
            
            // Store session
            localStorage.setItem('auth_user', JSON.stringify(currentUser));
            localStorage.setItem('session_token', sessionToken);

            document.getElementById('login-screen').style.display = 'none';
            document.getElementById('chat-screen').style.display = 'flex';
            
            updateUserInterface();
            await startNewChat();
            await loadSidebar();
        } else {
            document.getElementById('login-error').innerText = data.error || 'Authentication failed.';
        }
    } catch (err) {
        document.getElementById('login-error').innerText = 'Cannot connect to backend server. Ensure Flask is running on port 8001.';
    }
}

// ---- UPDATE USER INTERFACE BY ROLE ----
function updateUserInterface() {
    if (!currentUser) return;

    document.getElementById('user-display-name').innerText = currentUser.name;
    document.getElementById('user-emp-id').innerText = `ID: ${currentUser.employee_id}`;
    document.getElementById('user-dept').innerText = `Dept: ${currentUser.department}`;

    const badge = document.getElementById('user-role-badge');
    badge.innerText = currentUser.role;
    badge.className = `role-badge ${currentUser.role.toLowerCase()}`;

    // Admin Link Visibility
    const adminLink = document.getElementById('admin-link');
    if (currentUser.role === 'Admin') {
        adminLink.style.display = 'inline-block';
    } else {
        adminLink.style.display = 'none';
    }

    // Role-specific quick query suggestions (No hardcoded employee names)
    const pillContainer = document.getElementById('query-pills');
    if (currentUser.role === 'Finance' || currentUser.role === 'Admin') {
        pillContainer.innerHTML = `
            <div class="query-card" onclick="sendQuickQuery('Show pending requisitions')">
                <span class="card-icon">⏳</span>
                <div class="card-text">
                    <span class="card-label">Show pending requisitions</span>
                    <span class="card-sub">Pending Approvals Tracker</span>
                </div>
            </div>
            <div class="query-card" onclick="sendQuickQuery('Department-wise approval summary')">
                <span class="card-icon">📊</span>
                <div class="card-text">
                    <span class="card-label">Department-wise summary</span>
                    <span class="card-sub">Organization Analytics</span>
                </div>
            </div>
            <div class="query-card" onclick="sendQuickQuery('Which employee has the highest approved value?')">
                <span class="card-icon">🏆</span>
                <div class="card-text">
                    <span class="card-label">Top approved employee</span>
                    <span class="card-sub">Metrics & Ranking</span>
                </div>
            </div>
            <div class="query-card" onclick="sendQuickQuery('Show all approved requisitions')">
                <span class="card-icon">📋</span>
                <div class="card-text">
                    <span class="card-label">All approved requisitions</span>
                    <span class="card-sub">Requisition Directory</span>
                </div>
            </div>
        `;
        document.getElementById('welcome-subtitle').innerText = "Finance & Admin View: Organization-wide requisition intelligence enabled.";
    } else {
        pillContainer.innerHTML = `
            <div class="query-card" onclick="sendQuickQuery('Show my pending requisitions')">
                <span class="card-icon">📋</span>
                <div class="card-text">
                    <span class="card-label">My pending requisitions</span>
                    <span class="card-sub">Track Approval Status</span>
                </div>
            </div>
            <div class="query-card" onclick="sendQuickQuery('Show my approved requisitions')">
                <span class="card-icon">✅</span>
                <div class="card-text">
                    <span class="card-label">My approved requisitions</span>
                    <span class="card-sub">View Approved Claims</span>
                </div>
            </div>
            <div class="query-card" onclick="sendQuickQuery('What is my total approved amount?')">
                <span class="card-icon">💰</span>
                <div class="card-text">
                    <span class="card-label">My total approved amount</span>
                    <span class="card-sub">Reimbursement Totals</span>
                </div>
            </div>
            <div class="query-card" onclick="sendQuickQuery('What is the status of my latest requisition?')">
                <span class="card-icon">⏱️</span>
                <div class="card-text">
                    <span class="card-label">What is the status of my latest requisition?</span>
                    <span class="card-sub">Track Latest Requisition</span>
                </div>
            </div>
        `;
        document.getElementById('welcome-subtitle').innerText = `Welcome ${currentUser.name}. You are authorized to query your personal requisitions.`;
    }
}

// ---- LOGOUT ----
function logout() {
    currentUser = null;
    sessionToken = null;
    localStorage.removeItem('auth_user');
    localStorage.removeItem('session_token');

    document.getElementById('chat-screen').style.display = 'none';
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('login-error').innerText = '';
    document.getElementById('username').value = '';
}

// ---- START NEW CHAT ----
async function startNewChat() {
    try {
        var res = await fetch(BACKEND + '/new_chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                session_token: sessionToken,
                username: currentUser ? currentUser.email : ''
            })
        });
        var data = await res.json();
        currentChatId = data.chat_id;
    } catch (err) {
        console.log('Could not create new chat:', err);
    }

    messagesDiv.innerHTML = '';
    messagesDiv.appendChild(welcomeDiv);
    welcomeDiv.style.display = 'flex';
    questionInput.value = '';
    questionInput.style.height = '44px';
}

// ---- LOAD SIDEBAR HISTORY ----
async function loadSidebar() {
    try {
        var res = await fetch(BACKEND + '/get_history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                session_token: sessionToken,
                username: currentUser ? currentUser.email : ''
            })
        });
        var history = await res.json();
        var chatIds = Object.keys(history).reverse();

        if (chatIds.length === 0) {
            docList.innerHTML = '<p class="muted">No previous chats.</p>';
            return;
        }

        docList.innerHTML = '';
        chatIds.forEach(function (chatId) {
            var chat = history[chatId];
            if (!chat.messages || chat.messages.length === 0) return;

            var item = document.createElement('div');
            item.className = 'chat-item' + (chatId === currentChatId ? ' active' : '');

            // Find first user message for clean title display
            var firstUserMsg = chat.messages.find(function(m) { return m.role === 'user'; });
            var rawTitle = firstUserMsg ? firstUserMsg.text : (chat.title || 'Chat Session');
            // Remove any leading artificial numbers like "1. ", "2. "
            var cleanTitle = rawTitle.replace(/^\d+[\.\)]\s*/, '').trim();

            var title = document.createElement('span');
            title.innerText = cleanTitle;
            title.className = 'chat-item-title';
            title.title = cleanTitle;
            title.onclick = function () { loadChat(chatId); };

            var deleteBtn = document.createElement('button');
            deleteBtn.innerText = '×';
            deleteBtn.className = 'delete-btn';
            deleteBtn.title = 'Delete Chat';
            deleteBtn.onclick = async function (e) {
                e.stopPropagation();
                await deleteChat(chatId);
            };

            item.appendChild(title);
            item.appendChild(deleteBtn);
            docList.appendChild(item);
        });

    } catch (err) {
        console.log('Could not load history:', err);
    }
}

// ---- LOAD OLD CHAT ----
async function loadChat(chatId) {
    try {
        var res = await fetch(BACKEND + '/get_chat/' + chatId, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                session_token: sessionToken,
                username: currentUser ? currentUser.email : ''
            })
        });
        var chat = await res.json();
        currentChatId = chatId;
        messagesDiv.innerHTML = '';
        if (welcomeDiv) welcomeDiv.style.display = 'none';

        // Render ALL messages belonging to this complete conversation
        if (chat.messages && chat.messages.length > 0) {
            chat.messages.forEach(function (msg) {
                addBubble(msg.role, msg.text);
            });
        }
        await loadSidebar();
    } catch (err) {
        console.log('Could not load chat:', err);
    }
}

// ---- DELETE CHAT ----
async function deleteChat(chatId) {
    try {
        await fetch(BACKEND + '/delete_chat/' + chatId, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                session_token: sessionToken,
                username: currentUser ? currentUser.email : ''
            })
        });
        if (chatId === currentChatId) {
            await startNewChat();
        }
        await loadSidebar();
    } catch (err) {
        console.log('Could not delete chat:', err);
    }
}

// ---- SEND QUICK QUERY FROM PILL ----
function sendQuickQuery(text) {
    questionInput.value = text;
    sendMessage();
}

// ---- SEND MESSAGE ----
async function sendMessage() {
    var question = questionInput.value.trim();
    if (!question) return;

    if (welcomeDiv) welcomeDiv.style.display = 'none';
    addBubble('user', question);
    questionInput.value = '';
    questionInput.style.height = '44px';
    showTyping();

    try {
        var res = await fetch(BACKEND + '/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                chat_id: currentChatId,
                session_token: sessionToken,
                username: currentUser ? currentUser.email : ''
            })
        });
        var data = await res.json();
        removeTyping();
        
        if (data.unauthorized) {
            addBubble('assistant', '⚠️ ' + data.answer, data.sources, true, data.pagination);
        } else {
            addBubble('assistant', data.answer, data.sources, false, data.pagination);
        }
    } catch (err) {
        removeTyping();
        addBubble('assistant', 'Error: Could not reach backend server.');
    }
}

// ---- PAGINATION BUTTON REQUEST ----
async function requestPage(targetPage, label) {
    if (welcomeDiv) welcomeDiv.style.display = 'none';
    addBubble('user', label || `Page ${targetPage}`);
    showTyping();

    try {
        var res = await fetch(BACKEND + '/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: label || `Page ${targetPage}`,
                page: targetPage,
                chat_id: currentChatId,
                session_token: sessionToken,
                username: currentUser ? currentUser.email : ''
            })
        });
        var data = await res.json();
        removeTyping();
        
        if (data.unauthorized) {
            addBubble('assistant', '⚠️ ' + data.answer, data.sources, true, data.pagination);
        } else {
            addBubble('assistant', data.answer, data.sources, false, data.pagination);
        }
    } catch (err) {
        removeTyping();
        addBubble('assistant', 'Error: Could not reach backend server.');
    }
}

// ---- MARKDOWN TABLE NORMALIZATION AND PARSING HELPER ----
function normalizeMarkdownTables(text) {
    if (!text) return text;
    const lines = text.split('\n');
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();
        // Check if the line looks like a markdown table separator row: starts and ends with |, and contains only |, -, :, and whitespace
        if (line.startsWith('|') && line.endsWith('|') && /^[|:\-\s]+$/.test(line)) {
            const cells = line.split('|');
            for (let j = 1; j < cells.length - 1; j++) {
                cells[j] = ' --- ';
            }
            lines[i] = cells.join('|');
        }
    }
    return lines.join('\n');
}

function fallbackMarkdownParser(text) {
    // 1. Normalize markdown tables first
    text = normalizeMarkdownTables(text);

    // Escape HTML characters to prevent XSS (since we don't dangerouslySetInnerHTML raw LLM output)
    let escaped = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

    // 2. Parse tables
    const lines = escaped.split('\n');
    let inTable = false;
    let tableHtml = '';
    const outputLines = [];

    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();
        if (line.startsWith('|') && line.endsWith('|')) {
            if (!inTable) {
                inTable = true;
                tableHtml = '<div class="table-container"><table>';
                // Read headers
                const cells = line.split('|').slice(1, -1).map(c => c.trim());
                tableHtml += '<thead><tr>' + cells.map(c => `<th>${parseInline(c)}</th>`).join('') + '</tr></thead><tbody>';
                // Skip separator row if next line is separator
                if (i + 1 < lines.length && /^[|:\-\s]+$/.test(lines[i + 1].trim())) {
                    i++; // skip separator
                }
            } else {
                const cells = line.split('|').slice(1, -1).map(c => c.trim());
                tableHtml += '<tr>' + cells.map(c => `<td>${parseInline(c)}</td>`).join('') + '</tr>';
            }
        } else {
            if (inTable) {
                inTable = false;
                tableHtml += '</tbody></table></div>';
                outputLines.push(tableHtml);
            }
            outputLines.push(line);
        }
    }
    if (inTable) {
        tableHtml += '</tbody></table></div>';
        outputLines.push(tableHtml);
    }

    // 3. Process paragraphs and linebreaks
    let html = '';
    let inList = false;

    for (let line of outputLines) {
        if (line.startsWith('&lt;div class="table-container"&gt;') || line.startsWith('<div class="table-container">')) {
            // Already HTML table, don't wrap or escape
            if (inList) { html += '</ul>'; inList = false; }
            html += line.replace(/&lt;/g, '<').replace(/&gt;/g, '>');
            continue;
        }

        let trimmed = line.trim();
        if (!trimmed) {
            if (inList) { html += '</ul>'; inList = false; }
            html += '<br/>';
            continue;
        }

        // Bullet lists
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
            if (!inList) { html += '<ul>'; inList = true; }
            html += `<li>${parseInline(trimmed.substring(2))}</li>`;
        } else {
            if (inList) { html += '</ul>'; inList = false; }
            html += `<p>${parseInline(line)}</p>`;
        }
    }
    if (inList) { html += '</ul>'; }

    return html;

    function parseInline(str) {
        // Bold: **bold**
        str = str.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        // Code: `code`
        str = str.replace(/`(.*?)`/g, '<code>$1</code>');
        return str;
    }
}

// ---- ADD BUBBLE ----
function addBubble(role, text, sources, isWarning = false, pagination = null) {
    var row = document.createElement('div');
    row.className = 'msg-row ' + role;
    var bubble = document.createElement('div');
    bubble.className = 'bubble ' + role + (isWarning ? ' warning-bubble' : '');

    // Parse Markdown tables & formatting
    if (role === 'assistant') {
        var cleanText = normalizeMarkdownTables(text);
        if (typeof marked !== 'undefined') {
            bubble.innerHTML = marked.parse(cleanText);
        } else {
            bubble.innerHTML = fallbackMarkdownParser(text);
        }

        // Wrap rendered Markdown <table> elements in responsive .table-container wrappers
        var tables = bubble.querySelectorAll('table');
        tables.forEach(function (table) {
            var wrapper;
            if (!table.parentNode.classList.contains('table-container')) {
                wrapper = document.createElement('div');
                wrapper.className = 'table-container';
                table.parentNode.insertBefore(wrapper, table);
                wrapper.appendChild(table);
            } else {
                wrapper = table.parentNode;
            }
            // Guarantee new table horizontal scroll position starts at far left (0)!
            wrapper.scrollLeft = 0;
        });
    } else {
        bubble.innerText = text;
    }

    if (sources && sources.length > 0) {
        var sourcesDiv = document.createElement('div');
        sourcesDiv.className = 'sources';
        sourcesDiv.innerHTML = '<span class="source-label">Source Records:</span> ';
        var seen = [];
        sources.forEach(function (s) {
            if (seen.indexOf(s.source) === -1) {
                seen.push(s.source);
                var pill = document.createElement('span');
                pill.className = 'source-pill';
                pill.innerText = s.source;
                sourcesDiv.appendChild(pill);
            }
        });
        bubble.appendChild(sourcesDiv);
    }

    if (pagination && pagination.total_pages > 1 && role === 'assistant') {
        var pageDiv = document.createElement('div');
        pageDiv.className = 'pagination-bar';
        
        var infoSpan = document.createElement('span');
        infoSpan.className = 'pagination-info';
        infoSpan.innerHTML = `Page <b>${pagination.page}</b> of <b>${pagination.total_pages}</b> (${pagination.total_records} matching)`;
        pageDiv.appendChild(infoSpan);

        var btnGroup = document.createElement('div');
        btnGroup.className = 'pagination-buttons';

        var prevBtn = document.createElement('button');
        prevBtn.className = 'page-btn prev-btn';
        prevBtn.innerText = '← Previous';
        if (!pagination.has_previous) prevBtn.disabled = true;
        else prevBtn.onclick = function() { requestPage(pagination.page - 1, 'Previous page'); };

        var nextBtn = document.createElement('button');
        nextBtn.className = 'page-btn next-btn';
        nextBtn.innerText = 'Next →';
        if (!pagination.has_next) nextBtn.disabled = true;
        else nextBtn.onclick = function() { requestPage(pagination.page + 1, 'Next page'); };

        btnGroup.appendChild(prevBtn);
        btnGroup.appendChild(nextBtn);
        pageDiv.appendChild(btnGroup);
        bubble.appendChild(pageDiv);
    }

    row.appendChild(bubble);
    messagesDiv.appendChild(row);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// ---- TYPING ANIMATION ----
function showTyping() {
    var row = document.createElement('div');
    row.className = 'msg-row assistant';
    row.id = 'typing-row';
    row.innerHTML = '<div class="bubble assistant"><div class="typing"><span></span><span></span><span></span></div></div>';
    messagesDiv.appendChild(row);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function removeTyping() {
    var row = document.getElementById('typing-row');
    if (row) row.remove();
}

// ---- NEW CHAT BUTTON ----
async function newChat() {
    currentChatId = null;
    await startNewChat();
    await loadSidebar();
}

// ---- INPUT KEY EVENTS ----
questionInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

questionInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

// ---- INIT ON LOAD ----
window.onload = function () {
    const savedUser = localStorage.getItem('auth_user');
    const savedToken = localStorage.getItem('session_token');

    if (savedUser && savedToken) {
        currentUser = JSON.parse(savedUser);
        sessionToken = savedToken;
        document.getElementById('login-screen').style.display = 'none';
        document.getElementById('chat-screen').style.display = 'flex';
        updateUserInterface();
        startNewChat();
        loadSidebar();
    } else {
        document.getElementById('login-screen').style.display = 'flex';
        document.getElementById('chat-screen').style.display = 'none';
    }
};