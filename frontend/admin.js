const BACKEND = window.location.origin;

let adminEmail = '';

// ---- ADMIN LOGIN ----
async function adminLogin() {
    var username = document.getElementById('username').value.trim();
    if (!username) {
        document.getElementById('login-error').innerText = 'Please enter admin email';
        return;
    }

    try {
        var res = await fetch(BACKEND + '/admin_login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username })
        });
        var data = await res.json();

        if (data.success) {
            adminEmail = username;
            document.getElementById('login-screen').style.display = 'none';
            document.getElementById('admin-panel').style.display = 'block';
            await loadSystemStatus();
        } else {
            document.getElementById('login-error').innerText = data.error || 'Wrong credentials';
            document.getElementById('login-error').style.color = 'red';
        }
    } catch (err) {
        document.getElementById('login-error').innerText = 'Cannot reach backend server. Is Flask running?';
    }
}

// ---- LOAD SYSTEM STATUS ----
async function loadSystemStatus() {
    try {
        var res = await fetch(BACKEND + '/admin/status');
        var data = await res.json();

        document.getElementById('stat-records').innerText = data.indexed_records;
        document.getElementById('stat-provider').innerText = data.data_provider_type.toUpperCase() === 'EXCEL' ? 'Excel Files' : data.data_provider_type.toUpperCase();
        document.getElementById('stat-llm').innerText = data.ollama_model || 'qwen2.5:3b';
        document.getElementById('stat-status').innerText = data.status;
    } catch (err) {
        console.log('Error fetching system status:', err);
    }
}

// ---- HANDLE 3 EXCEL UPLOAD ----
async function handleExcelUpload(e) {
    e.preventDefault();
    const reqInput = document.getElementById('req-file');
    const empInput = document.getElementById('emp-file');
    const finInput = document.getElementById('fin-file');
    const statusMsg = document.getElementById('upload-status');

    if (!reqInput.files[0] && !empInput.files[0] && !finInput.files[0]) {
        statusMsg.style.color = '#e74c3c';
        statusMsg.innerText = 'Please select at least one Excel file to upload.';
        return;
    }

    const formData = new FormData();
    formData.append('email', adminEmail);

    if (reqInput.files[0]) formData.append('requisition_file', reqInput.files[0]);
    if (empInput.files[0]) formData.append('employee_file', empInput.files[0]);
    if (finInput.files[0]) formData.append('finance_file', finInput.files[0]);

    statusMsg.style.color = '#2980b9';
    statusMsg.innerText = 'Uploading Excels, parsing records, and reloading dataset... Please wait.';

    try {
        var res = await fetch(BACKEND + '/admin/upload_excels', {
            method: 'POST',
            body: formData
        });
        var data = await res.json();

        if (data.success) {
            statusMsg.style.color = '#27ae60';
            statusMsg.innerText = '✅ ' + data.message;
            await loadSystemStatus();
            reqInput.value = '';
            empInput.value = '';
            finInput.value = '';
        } else {
            statusMsg.style.color = '#e74c3c';
            statusMsg.innerText = '❌ Upload failed: ' + data.error;
        }
    } catch (err) {
        statusMsg.style.color = '#e74c3c';
        statusMsg.innerText = '❌ Error uploading to backend server.';
    }
}

// ---- LOGOUT ----
function logout() {
    adminEmail = '';
    var input = document.getElementById('username');
    if (input) input.value = '';
    var err = document.getElementById('login-error');
    if (err) err.innerText = '';
    document.getElementById('admin-panel').style.display = 'none';
    document.getElementById('login-screen').style.display = 'flex';
}