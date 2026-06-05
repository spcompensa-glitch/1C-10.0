(function() {
    const AdminUsersPage = () => {
        const [usersList, setUsersList] = React.useState([]);
        const [loadingUsers, setLoadingUsers] = React.useState(false);
        const [usersError, setUsersError] = React.useState('');

        const authHeader = () => ({
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('auth_token') || localStorage.getItem('sniper_token') || ''}`
        });

        const fetchUsers = async () => {
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
            fetchUsers();
        }, []);

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

        return (
            <div className="min-h-screen v5-bg-deep text-white lg:pl-[80px] overflow-y-auto">
                <div className="max-w-2xl mx-auto w-full px-4 sm:px-6 pb-[90px] lg:pb-10 flex flex-col gap-6 pt-8 lg:pt-12">
                    {/* Header */}
                    <div className="flex items-center gap-3 pb-4 border-b border-white/5">
                        <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
                            <span className="material-icons-round text-white">admin_panel_settings</span>
                        </div>
                        <div>
                            <h1 className="text-base font-black text-white uppercase tracking-widest">Controle de Usuários</h1>
                            <p className="text-[10px] text-gray-500 uppercase tracking-wider">Painel Administrativo 1Crypten</p>
                        </div>
                    </div>

                    <div className="glass-card p-5 rounded-2xl border border-white/5 flex flex-col gap-4">
                        <div className="flex items-center justify-between pb-3 border-b border-white/5">
                            <h2 className="text-xs font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                <span className="material-icons-round text-sm text-cyan-400">group</span>
                                Usuários Cadastrados
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
                </div>
            </div>
        );
    };

    window.AdminUsersPage = AdminUsersPage;
})();
