(function() {
    const SettingsPage = ({ onLogout, theme, setTheme }) => {
        const themes = [
            { id: 'classic', label: 'Classic Gold', icon: 'auto_awesome', color: 'text-yellow-400' },
            { id: 'gemini', label: 'Gemini Dark', icon: 'blur_on', color: 'text-white' },
        ];

        const [customApi, setCustomApi] = React.useState(localStorage.getItem('BACKEND_API_URL') || '');

        // ─── OKX Credentials State ─────────────────────────────────
        const [okxApiKey, setOkxApiKey]         = React.useState('');
        const [okxSecret, setOkxSecret]         = React.useState('');
        const [okxPassphrase, setOkxPassphrase] = React.useState('');
        const [showApiKey, setShowApiKey]         = React.useState(false);
        const [showSecret, setShowSecret]         = React.useState(false);
        const [showPassphrase, setShowPassphrase] = React.useState(false);
        const [okxStatus, setOkxStatus]         = React.useState(null);
        const [testResult, setTestResult]       = React.useState(null);
        const [testing, setTesting]             = React.useState(false);
        const [saving, setSaving]               = React.useState(false);
        const [testPassed, setTestPassed]       = React.useState(false);

        const authHeader = () => ({
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('auth_token') || localStorage.getItem('sniper_token') || ''}`
        });

        React.useEffect(() => {
            const fetchStatus = async () => {
                try {
                    const res = await fetch(`${API_BASE}/api/account/okx-tokens/status`, { headers: authHeader() });
                    if (res.ok) setOkxStatus(await res.json());
                } catch (e) { console.warn('[OKX] status fetch error:', e); }
            };
            fetchStatus();
        }, []);

        // ─── User Management State (Admins only) ───────────────────
        const [usersList, setUsersList] = React.useState([]);
        const [loadingUsers, setLoadingUsers] = React.useState(false);
        const [usersError, setUsersError] = React.useState('');

        const currentUser = React.useMemo(() => {
            try {
                return JSON.parse(localStorage.getItem('user') || '{}');
            } catch (e) {
                return {};
            }
        }, []);
        const isAdmin = currentUser.role === 'admin';

        const fetchUsers = async () => {
            if (!isAdmin) return;
            setLoadingUsers(true);
            setUsersError('');
            try {
                const res = await fetch(`${API_BASE}/api/auth/users`, { headers: authHeader() });
                if (res.ok) {
                    const data = await res.json();
                    setUsersList(data.users || []);
                } else {
                    setUsersError('Erro ao carregar lista de usuários');
                }
            } catch (e) {
                setUsersError('Erro de rede ao carregar usuários: ' + e.message);
            } finally {
                setLoadingUsers(false);
            }
        };

        React.useEffect(() => {
            if (isAdmin) {
                fetchUsers();
            }
        }, [isAdmin]);

        const handleToggleUserStatus = async (userObj) => {
            const action = userObj.is_active ? 'block' : 'approve';
            try {
                const res = await fetch(`${API_BASE}/api/auth/users/${userObj.id}/${action}`, {
                    method: 'POST',
                    headers: authHeader()
                });
                if (res.ok) {
                    fetchUsers();
                } else {
                    const errData = await res.json();
                    alert(`Erro: ${errData.detail || errData.error || 'Falha ao alterar status'}`);
                }
            } catch (e) {
                alert('Erro de rede: ' + e.message);
            }
        };

        const handleDeleteUser = async (userId) => {
            if (!confirm('Deseja realmente excluir este usuário?')) return;
            try {
                const res = await fetch(`${API_BASE}/api/auth/users/${userId}`, {
                    method: 'DELETE',
                    headers: authHeader()
                });
                if (res.ok) {
                    fetchUsers();
                } else {
                    const errData = await res.json();
                    alert(`Erro: ${errData.detail || errData.error || 'Falha ao excluir'}`);
                }
            } catch (e) {
                alert('Erro de rede: ' + e.message);
            }
        };

        const handleTestOkx = async () => {
            if (!okxApiKey.trim() || !okxSecret.trim()) {
                setTestResult({ success: false, message: 'Preencha a API Key e a Secret Key.' });
                return;
            }
            setTesting(true); setTestResult(null); setTestPassed(false);
            try {
                const res = await fetch(`${API_BASE}/api/account/okx-tokens/test-live`, {
                    method: 'POST',
                    headers: authHeader(),
                    body: JSON.stringify({ api_key: okxApiKey.trim(), secret_key: okxSecret.trim(), passphrase: okxPassphrase.trim() || null })
                });
                const data = await res.json();
                if (res.ok && data.success) { setTestResult({ success: true, ...data }); setTestPassed(true); }
                else { setTestResult({ success: false, message: data.detail || data.message || 'Credenciais inválidas' }); }
            } catch (e) { setTestResult({ success: false, message: 'Erro de rede: ' + e.message }); }
            finally { setTesting(false); }
        };

        const handleSaveOkx = async () => {
            if (!testPassed) return;
            setSaving(true);
            try {
                const res = await fetch(`${API_BASE}/api/account/okx-tokens`, {
                    method: 'POST',
                    headers: authHeader(),
                    body: JSON.stringify({ api_key: okxApiKey.trim(), secret_key: okxSecret.trim(), passphrase: okxPassphrase.trim() || null })
                });
                const data = await res.json();
                if (res.ok && data.success) {
                    setOkxStatus({ configured: true, masked_api_key: data.masked_api_key, updated_at: new Date().toISOString() });
                    setOkxApiKey(''); setOkxSecret(''); setOkxPassphrase('');
                    setTestPassed(false);
                    setTestResult({ success: true, message: '✅ Credenciais salvas com segurança!', total_equity_usd: data.total_equity_usd, usdt_available: data.usdt_available });
                } else { setTestResult({ success: false, message: data.detail || 'Erro ao salvar' }); }
            } catch (e) { setTestResult({ success: false, message: 'Erro de rede: ' + e.message }); }
            finally { setSaving(false); }
        };

        const handleSaveApi = () => {
            if (customApi.trim()) {
                const sanitized = customApi.trim().replace(/\/$/, "");
                localStorage.setItem('BACKEND_API_URL', sanitized);
                alert(`✅ API definida com sucesso!\nO sistema irá recarregar para aplicar.`);
                window.location.reload();
            } else {
                localStorage.removeItem('BACKEND_API_URL');
                alert(`✅ API resetada para o padrão automático!\nO sistema irá recarregar para aplicar.`);
                window.location.reload();
            }
        };

        const handleResetApi = () => {
            localStorage.removeItem('BACKEND_API_URL');
            setCustomApi('');
            alert(`✅ API resetada para o padrão automático!\nO sistema irá recarregar para aplicar.`);
            window.location.reload();
        };

        const inputBase = "w-full bg-white/[0.02] border border-white/10 rounded-xl px-4 py-3 text-xs font-mono text-gray-300 focus:outline-none focus:border-white/30 transition-all pr-12";
        const eyeBtn = "absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white transition-colors cursor-pointer select-none";

        return (
            <div className="min-h-screen v5-bg-deep text-white lg:pl-[80px] overflow-y-auto">
                <div className="max-w-2xl mx-auto w-full px-4 sm:px-6 pb-[90px] lg:pb-10 flex flex-col gap-6 pt-8 lg:pt-12">

                    {/* Header */}
                    <div className="flex items-center gap-3 pb-4 border-b border-white/5">
                        <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
                            <span className="material-icons-round text-white">settings</span>
                        </div>
                        <div>
                            <h1 className="text-base font-black text-white uppercase tracking-widest">Configurações</h1>
                            <p className="text-[10px] text-gray-500 uppercase tracking-wider">Sistema 10D Sniper · V125.400 Elite</p>
                        </div>
                    </div>

                    {/* ════════ OKX CREDENCIAIS — CONTA REAL ════════ */}
                    <div className="rounded-2xl border flex flex-col gap-4 overflow-hidden"
                         style={{ background: 'rgba(13,13,20,0.65)', backdropFilter: 'blur(24px)', borderColor: okxStatus?.configured ? 'rgba(34,197,94,0.25)' : 'rgba(34,211,238,0.12)' }}>

                        <div className="px-5 pt-5 flex items-center justify-between">
                            <h2 className="text-xs font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                <span className="material-icons-round text-sm" style={{ color: '#22d3ee' }}>vpn_key</span>
                                OKX — Conta Real
                            </h2>
                            {okxStatus?.configured ? (
                                <div className="flex items-center gap-1.5 bg-green-500/10 border border-green-500/20 rounded-full px-3 py-1">
                                    <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></div>
                                    <span className="text-[9px] font-black text-green-400 uppercase tracking-widest">Ativa</span>
                                </div>
                            ) : (
                                <div className="flex items-center gap-1.5 bg-white/5 border border-white/8 rounded-full px-3 py-1">
                                    <div className="w-1.5 h-1.5 rounded-full bg-gray-600"></div>
                                    <span className="text-[9px] font-black text-gray-500 uppercase tracking-widest">Não configurada</span>
                                </div>
                            )}
                        </div>

                        {okxStatus?.configured && (
                            <div className="mx-5 flex items-center gap-3 rounded-xl px-4 py-3" style={{ background: 'rgba(34,197,94,0.05)', border: '1px solid rgba(34,197,94,0.15)' }}>
                                <span className="material-icons-round text-green-400 text-base">shield</span>
                                <div className="flex flex-col">
                                    <span className="text-[8px] text-gray-500 uppercase tracking-widest">API Key Ativa</span>
                                    <span className="text-xs font-mono text-green-300 font-bold tracking-wider">{okxStatus.masked_api_key}</span>
                                </div>
                                {okxStatus.updated_at && (
                                    <span className="text-[8px] text-gray-600 ml-auto whitespace-nowrap">
                                        {new Date(okxStatus.updated_at).toLocaleDateString('pt-BR')}
                                    </span>
                                )}
                            </div>
                        )}

                        <div className="px-5 pb-5 flex flex-col gap-3">
                            <p className="text-[9px] text-gray-600 uppercase tracking-widest">
                                {okxStatus?.configured ? '↓ Para substituir, preencha abaixo e teste:' : '↓ Insira suas credenciais da OKX:'}
                            </p>

                            {/* API Key */}
                            <div className="flex flex-col gap-1">
                                <label className="text-[9px] text-gray-500 uppercase tracking-widest font-black">API Key</label>
                                <div className="relative">
                                    <input id="okx-api-key" type={showApiKey ? 'text' : 'password'}
                                        value={okxApiKey}
                                        onChange={e => { setOkxApiKey(e.target.value); setTestPassed(false); setTestResult(null); }}
                                        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                                        className={inputBase} autoComplete="off" />
                                    <span className={`material-icons-round text-base ${eyeBtn}`} onClick={() => setShowApiKey(v => !v)}>
                                        {showApiKey ? 'visibility_off' : 'visibility'}
                                    </span>
                                </div>
                            </div>

                            {/* Secret Key */}
                            <div className="flex flex-col gap-1">
                                <label className="text-[9px] text-gray-500 uppercase tracking-widest font-black">Secret Key</label>
                                <div className="relative">
                                    <input id="okx-secret-key" type={showSecret ? 'text' : 'password'}
                                        value={okxSecret}
                                        onChange={e => { setOkxSecret(e.target.value); setTestPassed(false); setTestResult(null); }}
                                        placeholder="••••••••••••••••••••••••••••••••••••••••"
                                        className={inputBase} autoComplete="off" />
                                    <span className={`material-icons-round text-base ${eyeBtn}`} onClick={() => setShowSecret(v => !v)}>
                                        {showSecret ? 'visibility_off' : 'visibility'}
                                    </span>
                                </div>
                            </div>

                            {/* Passphrase */}
                            <div className="flex flex-col gap-1">
                                <label className="text-[9px] text-gray-500 uppercase tracking-widest font-black">
                                    Passphrase <span className="text-gray-700 font-normal normal-case tracking-normal">(senha criada na OKX)</span>
                                </label>
                                <div className="relative">
                                    <input id="okx-passphrase" type={showPassphrase ? 'text' : 'password'}
                                        value={okxPassphrase}
                                        onChange={e => { setOkxPassphrase(e.target.value); setTestPassed(false); setTestResult(null); }}
                                        placeholder="Sua passphrase"
                                        className={inputBase} autoComplete="off" />
                                    <span className={`material-icons-round text-base ${eyeBtn}`} onClick={() => setShowPassphrase(v => !v)}>
                                        {showPassphrase ? 'visibility_off' : 'visibility'}
                                    </span>
                                </div>
                            </div>

                            {/* Resultado do teste */}
                            {testResult && (
                                <div className={`rounded-xl px-4 py-3 border flex flex-col gap-2 transition-all ${
                                    testResult.success ? 'border-green-500/20' : 'border-red-500/20'
                                }`} style={{ background: testResult.success ? 'rgba(34,197,94,0.06)' : 'rgba(239,68,68,0.06)' }}>
                                    <div className="flex items-center gap-2">
                                        <span className={`material-icons-round text-base ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>
                                            {testResult.success ? 'check_circle' : 'error'}
                                        </span>
                                        <span className={`text-[10px] font-bold ${testResult.success ? 'text-green-300' : 'text-red-300'}`}>
                                            {testResult.message}
                                        </span>
                                    </div>
                                    {testResult.success && testResult.total_equity_usd != null && (
                                        <div className="flex gap-6 pl-6">
                                            <div>
                                                <p className="text-[8px] text-gray-500 uppercase tracking-widest">Equity Total</p>
                                                <p className="text-base font-black font-mono text-white">${Number(testResult.total_equity_usd).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
                                            </div>
                                            <div>
                                                <p className="text-[8px] text-gray-500 uppercase tracking-widest">USDT Disponível</p>
                                                <p className="text-base font-black font-mono text-green-300">${Number(testResult.usdt_available || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Botões */}
                            <div className="flex gap-2 mt-1">
                                <button id="btn-test-okx" onClick={handleTestOkx}
                                    disabled={testing || saving || !okxApiKey.trim() || !okxSecret.trim()}
                                    className="flex-1 py-2.5 rounded-xl border transition-all text-[10px] font-black uppercase tracking-widest flex items-center justify-center gap-1.5 disabled:opacity-35 disabled:cursor-not-allowed"
                                    style={{ background: 'rgba(34,211,238,0.07)', borderColor: 'rgba(34,211,238,0.2)', color: '#22d3ee' }}>
                                    {testing ? (
                                        <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"></div>Testando...</>
                                    ) : (
                                        <><span className="material-icons-round text-sm">wifi_tethering</span>Testar Conexão</>
                                    )}
                                </button>

                                <button id="btn-save-okx" onClick={handleSaveOkx}
                                    disabled={!testPassed || saving || testing}
                                    className="flex-1 py-2.5 rounded-xl border transition-all text-[10px] font-black uppercase tracking-widest flex items-center justify-center gap-1.5 disabled:opacity-25 disabled:cursor-not-allowed"
                                    style={{
                                        background: testPassed ? 'rgba(34,197,94,0.1)' : 'rgba(255,255,255,0.02)',
                                        borderColor: testPassed ? 'rgba(34,197,94,0.3)' : 'rgba(255,255,255,0.06)',
                                        color: testPassed ? '#4ade80' : '#374151'
                                    }}>
                                    {saving ? (
                                        <><div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"></div>Salvando...</>
                                    ) : (
                                        <><span className="material-icons-round text-sm">lock</span>Salvar Seguro</>
                                    )}
                                </button>
                            </div>

                            <p className="text-[8px] text-gray-700 text-center leading-relaxed">
                                🔐 AES-256 · Chave derivada via PBKDF2-SHA256 · Nunca exposta em texto plano
                            </p>
                        </div>
                    </div>

                    {/* Tema */}
                    <div className="glass-card p-5 rounded-2xl border border-white/5 flex flex-col gap-4">
                        <h2 className="text-xs font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
                            <span className="material-icons-round text-sm text-white/60">palette</span>
                            Tema Visual
                        </h2>
                        <div className="flex flex-col gap-2">
                            {themes.map(t => (
                                <button key={t.id} onClick={() => setTheme(t.id)}
                                    className={`flex items-center gap-3 p-3 rounded-xl border transition-all text-left ${theme === t.id
                                        ? 'bg-primary/10 border-primary/30 text-white'
                                        : 'bg-white/[0.02] border-white/5 text-gray-400 hover:border-white/10'}`}>
                                    <span className={`material-icons-round text-base ${t.color}`}>{t.icon}</span>
                                    <span className="text-xs font-bold">{t.label}</span>
                                    {theme === t.id && <span className="material-icons-round text-white text-sm ml-auto">check_circle</span>}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* API Endpoint Configuration */}
                    <div className="glass-card p-5 rounded-2xl border border-white/5 flex flex-col gap-4">
                        <h2 className="text-xs font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
                            <span className="material-icons-round text-sm text-white/60">api</span>
                            Endpoint da API do Backend
                        </h2>
                        <p className="text-[10px] text-gray-400 leading-relaxed uppercase tracking-wider">
                            Caso o backend esteja rodando desacoplado em outro serviço do Railway ou localmente, configure a URL abaixo.
                        </p>
                        <div className="flex flex-col gap-3">
                            <input type="text" value={customApi} onChange={(e) => setCustomApi(e.target.value)}
                                placeholder="Ex: https://10d50-backend.up.railway.app"
                                className="w-full bg-white/[0.02] border border-white/10 rounded-xl px-4 py-3 text-xs font-mono text-gray-300 focus:outline-none focus:border-primary/50 transition-all" />
                            <div className="flex gap-2">
                                <button onClick={handleSaveApi}
                                    className="flex-1 py-2.5 rounded-xl bg-primary/25 hover:bg-primary/40 border border-primary/45 hover:border-primary/60 transition-all text-xs font-bold uppercase tracking-widest flex items-center justify-center gap-1.5">
                                    <span className="material-icons-round text-sm">save</span>
                                    Salvar &amp; Conectar
                                </button>
                                {localStorage.getItem('BACKEND_API_URL') && (
                                    <button onClick={handleResetApi}
                                        className="px-4 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 hover:border-white/10 transition-all text-xs font-bold uppercase tracking-widest flex items-center justify-center"
                                        title="Resetar para automático">
                                        <span className="material-icons-round text-sm">restart_alt</span>
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* ════════ CONTROLE DE ACESSO — ADMINS ONLY ════════ */}
                    {isAdmin && (
                        <div className="glass-card p-5 rounded-2xl border border-white/5 flex flex-col gap-4">
                            <div className="flex items-center justify-between pb-3 border-b border-white/5">
                                <h2 className="text-xs font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                    <span className="material-icons-round text-sm text-cyan-400">group</span>
                                    Controle de Acesso de Usuários
                                </h2>
                                <button onClick={fetchUsers} disabled={loadingUsers} className="text-gray-500 hover:text-white transition-colors">
                                    <span className={`material-icons-round text-sm ${loadingUsers ? 'animate-spin' : ''}`}>refresh</span>
                                </button>
                            </div>

                            {usersError && (
                                <p className="text-[10px] text-red-500 font-bold uppercase tracking-widest">{usersError}</p>
                            )}

                            {loadingUsers && usersList.length === 0 ? (
                                <div className="py-4 text-center text-xs text-gray-600 uppercase tracking-widest animate-pulse">Carregando usuários...</div>
                            ) : usersList.length === 0 ? (
                                <div className="py-4 text-center text-xs text-gray-600 uppercase tracking-widest">Nenhum outro usuário cadastrado</div>
                            ) : (
                                <div className="flex flex-col gap-3">
                                    {usersList.map(u => (
                                        <div key={u.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-xl border border-white/5 bg-white/[0.01] hover:bg-white/[0.02] gap-3 transition-all">
                                            <div className="flex flex-col gap-1">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[10px] font-black text-white font-mono leading-none">ID #{u.id}</span>
                                                    <span className="text-xs font-bold text-white font-mono leading-none">{u.username}</span>
                                                    <span className={`text-[8px] font-black px-1.5 py-0.5 rounded uppercase tracking-wider ${
                                                        u.role === 'admin' ? 'bg-primary/20 text-primary border border-primary/20' : 'bg-white/5 text-gray-400 border border-white/5'
                                                    }`}>{u.role}</span>
                                                </div>
                                                <span className="text-[10px] text-gray-500 font-mono">{u.email || 'Sem e-mail'}</span>
                                            </div>

                                            <div className="flex items-center gap-2 self-end sm:self-center">
                                                {/* Status Badge */}
                                                <span className={`text-[8px] font-black px-2 py-0.5 rounded-full uppercase tracking-widest ${
                                                    u.is_active 
                                                        ? 'bg-green-500/10 text-green-400 border border-green-500/20' 
                                                        : 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
                                                }`}>
                                                    {u.is_active ? 'Aprovado' : 'Pendente/Bloqueado'}
                                                </span>

                                                {/* Toggle Button */}
                                                <button 
                                                    onClick={() => handleToggleUserStatus(u)}
                                                    className={`px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-wider border transition-all ${
                                                        u.is_active 
                                                            ? 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400 hover:bg-yellow-500/20 animate-triumph' 
                                                            : 'bg-green-500/10 border-green-500/20 text-green-400 hover:bg-green-500/20 animate-triumph'
                                                    }`}
                                                >
                                                    {u.is_active ? 'Bloquear' : 'Aprovar'}
                                                </button>

                                                {/* Delete Button */}
                                                <button 
                                                    onClick={() => handleDeleteUser(u.id)}
                                                    className="p-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-all"
                                                    title="Excluir usuário"
                                                >
                                                    <span className="material-icons-round text-xs">delete</span>
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* ════════ RESET DO SISTEMA (PAPER) — ADMINS ONLY ════════ */}
                    {isAdmin && (
                        <div className="glass-card p-5 rounded-2xl border border-red-500/15 flex flex-col gap-4 bg-red-950/5">
                            <h2 className="text-xs font-black text-red-400 uppercase tracking-widest flex items-center gap-2">
                                <span className="material-icons-round text-sm">restart_alt</span>
                                Resetar Motor Paper & Banca
                            </h2>
                            <p className="text-[10px] text-gray-400 leading-relaxed uppercase tracking-wider">
                                Esta ação limpa todos os slots ativos (LIVRE), remove ordens Moonbag, limpa o histórico de trades e reinicia o saldo Paper do Sniper para o valor inicial de $100.00.
                            </p>
                            <button
                                onClick={async () => {
                                    if (!confirm("⚠️ ATENÇÃO: Deseja realmente resetar todas as ordens, slots e a banca para $100.00? Esta ação não pode ser desfeita!")) return;
                                    try {
                                        const res = await fetch(`${API_BASE}/api/admin/reset-system`, {
                                            method: 'POST',
                                            headers: authHeader()
                                        });
                                        const data = await res.json();
                                        if (res.ok && data.status === 'SUCCESS') {
                                            alert(`✅ Sucesso:\n${data.message}`);
                                            window.location.reload();
                                        } else {
                                            alert(`❌ Erro: ${data.detail || data.message || 'Falha no reset'}`);
                                        }
                                    } catch (e) {
                                        alert('❌ Erro de rede: ' + e.message);
                                    }
                                }}
                                className="w-full py-3 rounded-xl bg-red-500/10 hover:bg-red-500/20 border border-red-500/25 hover:border-red-500/40 text-red-400 font-bold text-xs uppercase tracking-widest transition-all flex items-center justify-center gap-2 cursor-pointer"
                            >
                                <span className="material-icons-round text-sm">settings_backup_restore</span>
                                Resetar Completo (Banca $100.00)
                            </button>
                        </div>
                    )}

                    {/* Info do Sistema */}
                    <div className="glass-card p-5 rounded-2xl border border-white/5 flex flex-col gap-3">
                        <h2 className="text-xs font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
                            <span className="material-icons-round text-sm text-white/60">info</span>
                            Informações do Sistema
                        </h2>
                        <div className="flex flex-col gap-2 font-mono text-[10px]">
                            {[
                                { label: 'Versão UI', value: 'V125.400 Sentinel Protocol' },
                                { label: 'Endpoint', value: window.API_BASE || 'https://1crypten.space' },
                                { label: 'Modo', value: 'COCKPIT · Single Source of Truth' },
                                { label: 'Protocolo', value: 'Guardian Hedge + Escadinha Operacional' },
                            ].map((row, i) => (
                                <div key={i} className="flex justify-between items-center py-2 border-b border-white/5 last:border-0">
                                    <span className="text-gray-500 uppercase tracking-wider">{row.label}</span>
                                    <span className="text-gray-300 font-bold text-right max-w-[60%] truncate">{row.value}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Logout */}
                    <button
                        onClick={onLogout}
                        className="flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 hover:border-red-500/40 transition-all font-bold text-xs uppercase tracking-widest"
                    >
                        <span className="material-icons-round text-sm">power_settings_new</span>
                        Sair / Resetar Sessão
                    </button>

                </div>
            </div>
        );
    };

    window.SettingsPage = SettingsPage;
})();
