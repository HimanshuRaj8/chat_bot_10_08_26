const BACKEND = window.location.origin;

let adminEmail = '';
let sessionToken = '';

// ---- ADMIN LOGIN ----
async function adminLogin() {
    var username = document.getElementById('username').value.trim();
    var password = document.getElementById('password').value;
    if (!username) {
        document.getElementById('login-error').innerText = 'Please enter admin email';
        return;
    }
    if (!password) {
        document.getElementById('login-error').innerText = 'Please enter password';
        return;
    }

    try {
        var res = await fetch(BACKEND + '/admin_login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username, password: password })
        });
        var data = await res.json();

        if (data.success) {
            adminEmail = username;
            sessionToken = data.session_token;
            localStorage.setItem('admin_session_token', sessionToken);
            document.getElementById('login-screen').style.display = 'none';
            document.getElementById('admin-panel').style.display = 'block';
            await loadSystemStatus();
            await loadUsers();
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
    sessionToken = '';
    localStorage.removeItem('admin_session_token');
    localStorage.removeItem('admin_email');
    var input = document.getElementById('username');
    if (input) input.value = '';
    var pwd = document.getElementById('password');
    if (pwd) pwd.value = '';
    var err = document.getElementById('login-error');
    if (err) err.innerText = '';
    document.getElementById('admin-panel').style.display = 'none';
    document.getElementById('login-screen').style.display = 'flex';
}

// ---- LOAD USERS ----
async function loadUsers() {
    const tbody = document.getElementById('employees-table-body');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;">Loading users...</td></tr>';
    
    try {
        var res = await fetch(BACKEND + '/admin/users', {
            headers: { 'Authorization': 'Bearer ' + sessionToken }
        });
        var data = await res.json();
        
        if (data.success) {
            tbody.innerHTML = '';
            if (data.users.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;">No users registered.</td></tr>';
                return;
            }
            data.users.forEach((user, index) => {
                var row = document.createElement('tr');
                row.innerHTML = `
                    <td>${index + 1}</td>
                    <td>${user.email}</td>
                    <td style="font-family: monospace; font-weight: bold; color: #c0392b;">${user.password}</td>
                `;
                tbody.appendChild(row);
            });
        } else {
            tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; color:red;">Error: ${data.error}</td></tr>`;
        }
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align:center; color:red;">Cannot connect to backend server.</td></tr>';
    }
}

// ---- CREATE USER ----
async function createUser() {
    const emailInput = document.getElementById('new-user-email');
    const statusMsg = document.getElementById('create-user-status');
    const email = emailInput.value.trim();
    
    if (!email) {
        statusMsg.style.color = '#e74c3c';
        statusMsg.innerText = 'Please enter employee email';
        return;
    }
    
    statusMsg.style.color = '#2980b9';
    statusMsg.innerText = 'Creating user...';
    
    try {
        var res = await fetch(BACKEND + '/admin/users/create', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + sessionToken 
            },
            body: JSON.stringify({ email: email })
        });
        var data = await res.json();
        
        if (data.success) {
            statusMsg.style.color = '#27ae60';
            statusMsg.innerText = `User created! Password: ${data.password}`;
            emailInput.value = '';
            await loadUsers();
        } else {
            statusMsg.style.color = '#e74c3c';
            statusMsg.innerText = data.error || 'Failed to create user.';
        }
    } catch (err) {
        statusMsg.style.color = '#e74c3c';
        statusMsg.innerText = 'Error connecting to server.';
    }
}

// ---- GENERATE NEW PASSWORD ----
async function generateNewPassword() {
    const emailInput = document.getElementById('change-user-email');
    const statusMsg = document.getElementById('change-password-status');
    const email = emailInput.value.trim();
    
    if (!email) {
        statusMsg.style.color = '#e74c3c';
        statusMsg.innerText = 'Please enter employee email';
        return;
    }
    if (email.toLowerCase() === 'admin@motherson.com') {
        statusMsg.style.color = '#e74c3c';
        statusMsg.innerText = '🔒 Access denied. Admin passwords cannot be modified.';
        return;
    }
    
    statusMsg.style.color = '#2980b9';
    statusMsg.innerText = 'Generating new password...';
    
    try {
        var res = await fetch(BACKEND + '/admin/users/change_password', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + sessionToken 
            },
            body: JSON.stringify({ email: email })
        });
        var data = await res.json();
        
        if (data.success) {
            statusMsg.style.color = '#27ae60';
            statusMsg.innerText = `New password: ${data.password}`;
            emailInput.value = '';
            await loadUsers();
        } else {
            statusMsg.style.color = '#e74c3c';
            statusMsg.innerText = data.error || 'Failed to change password.';
        }
    } catch (err) {
        statusMsg.style.color = '#e74c3c';
        statusMsg.innerText = 'Error connecting to server.';
    }
}

// ---- DELETE USER ----
async function deleteUser() {
    const emailInput = document.getElementById('delete-user-email');
    const statusMsg = document.getElementById('delete-user-status');
    const email = emailInput.value.trim();
    
    if (!email) {
        statusMsg.style.color = '#e74c3c';
        statusMsg.innerText = 'Please enter employee email';
        return;
    }
    if (email.toLowerCase() === 'admin@motherson.com') {
        statusMsg.style.color = '#e74c3c';
        statusMsg.innerText = '🔒 Access denied. Admin accounts cannot be deleted.';
        return;
    }
    
    statusMsg.style.color = '#2980b9';
    statusMsg.innerText = 'Deleting user...';
    
    try {
        var res = await fetch(BACKEND + '/admin/users/delete', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + sessionToken 
            },
            body: JSON.stringify({ email: email })
        });
        var data = await res.json();
        
        if (data.success) {
            statusMsg.style.color = '#27ae60';
            statusMsg.innerText = 'User deleted successfully';
            emailInput.value = '';
            await loadUsers();
        } else {
            statusMsg.style.color = '#e74c3c';
            statusMsg.innerText = data.error || 'Failed to delete user.';
        }
    } catch (err) {
        statusMsg.style.color = '#e74c3c';
        statusMsg.innerText = 'Error connecting to server.';
    }
}

// ---- DOWNLOAD CSV ----
function downloadCSV() {
    if (!sessionToken) return;
    window.open(`${BACKEND}/admin/users/download_csv?token=${encodeURIComponent(sessionToken)}`, '_blank');
}

// ---- WINDOW ONLOAD ----
window.onload = async function() {
    const savedToken = localStorage.getItem('admin_session_token');
    if (savedToken) {
        sessionToken = savedToken;
        try {
            var res = await fetch(BACKEND + '/admin/status');
            if (res.status === 200) {
                adminEmail = localStorage.getItem('admin_email') || 'admin@motherson.com';
                document.getElementById('login-screen').style.display = 'none';
                document.getElementById('admin-panel').style.display = 'block';
                await loadSystemStatus();
                await loadUsers();
                return;
            }
        } catch (e) {}
    }
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('admin-panel').style.display = 'none';
};