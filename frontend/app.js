(function() {
    const { useState, useEffect, useRef, useMemo } = window.React;
    const { Link, Route, useLocation, useNavigate } = window.ReactRouterDOM;

    // =========================================================================
    // NavBar — 3 Botões: BANCA / HERMES / ADM (submenu: GALAXY, SANDBOX, CONFIG)
    // Classe CSS PURO (app-nav / app-nav-btn / etc definidas em cockpit.css) — ZERO Tailwind
    // =========================================================================
    const NavBar = ({ onLogout }) => {
        const location = useLocation();
        const [admOpen, setAdmOpen] = React.useState(false);

        const isActive = (path) => location.pathname === path || (path === '/' && (location.pathname === '/10d'));
        const isAdmActive = location.pathname === '/memory' || location.pathname === '/sandbox' || location.pathname === '/config' || location.pathname === '/adm';

        const btnClass = (path, isSpecial) => {
            const active = isActive(path);
            let cls = 'app-nav-btn';
            if (isSpecial) cls += ' is-special';
            if (active) cls += ' active';
            return cls;
        };

        const mkContent = (icon, label, isSpecial) => (
            React.createElement(React.Fragment, null,
                React.createElement('span', { className: 'material-icons-round', style: { fontSize: isSpecial ? '25px' : '24px' } }, icon),
                React.createElement('span', { className: 'app-nav-label' }, label)
            )
        );

        return React.createElement('nav', { className: 'app-nav' },
            React.createElement('div', { className: 'app-nav-logo' },
                React.createElement('img', { src: '/logo10DTrasp.png?v=4', alt: 'Logo', style: { width: '40px', height: '40px', objectFit: 'contain', filter: 'drop-shadow(0 0 10px rgba(255,215,0,0.3))' } }),
                React.createElement('div', { style: { width: '32px', height: '1px', background: 'rgba(255,255,255,0.1)' } })
            ),
            React.createElement('div', { className: 'app-nav-inner' },
                React.createElement(Link, { to: '/', className: btnClass('/', false), title: 'Banca' }, mkContent('space_dashboard', 'Banca', false)),
                React.createElement(Link, { to: '/hermes', className: btnClass('/hermes', true), title: 'Hermes' }, mkContent('auto_awesome', 'Hermes', true)),
                React.createElement('div', { className: 'app-nav-adm-wrapper' },
                    React.createElement('button', {
                        onClick: () => setAdmOpen(!admOpen),
                        className: 'app-nav-btn app-nav-adm-btn' + (admOpen || isAdmActive ? ' adm-open' : ''),
                        title: 'ADM'
                    }, mkContent('admin_panel_settings', 'ADM', false)),
                    admOpen && React.createElement(React.Fragment, null,
                        React.createElement('div', { className: 'adm-overlay', style: { position: 'fixed', inset: 0, zIndex: 9999 }, onClick: () => setAdmOpen(false) }),
                        React.createElement('div', { className: 'adm-submenu' },
                            React.createElement('span', { className: 'adm-submenu-title' }, 'ADM \u00b7 M\u00f3dulos'),
                            React.createElement(Link, { to: '/memory', onClick: () => setAdmOpen(false), className: 'adm-item' + (location.pathname === '/memory' ? ' adm-item-active' : '') },
                                React.createElement('span', { className: 'material-icons-round', style: { fontSize: '18px' } }, 'auto_awesome'),
                                React.createElement('span', null, 'Galaxy')
                            ),
                            React.createElement(Link, { to: '/sandbox', onClick: () => setAdmOpen(false), className: 'adm-item' + (location.pathname === '/sandbox' ? ' adm-item-active' : '') },
                                React.createElement('span', { className: 'material-icons-round', style: { fontSize: '18px' } }, 'science'),
                                React.createElement('span', null, 'Sandbox')
                            ),
                            React.createElement(Link, { to: '/config', onClick: () => setAdmOpen(false), className: 'adm-item' + (location.pathname === '/config' || location.pathname === '/adm' ? ' adm-item-active' : '') },
                                React.createElement('span', { className: 'material-icons-round', style: { fontSize: '18px' } }, 'settings'),
                                React.createElement('span', null, 'Config')
                            )
                        )
                    )
                )
            ),
            React.createElement('div', { className: 'app-nav-logout' },
                React.createElement('button', {
                    onClick: onLogout,
                    title: 'Sair do Sistema',
                    style: { display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '12px', borderRadius: '12px', background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid transparent', cursor: 'pointer' }
                },
                    React.createElement('span', { className: 'material-icons-round', style: { fontSize: '20px' } }, 'power_settings_new')
                )
            )
        );
    };

    const App = () => {
        const [isAuthenticated, setIsAuthenticated] = useState(() => {
            return !!(localStorage.getItem('auth_token') || localStorage.getItem('sniper_token'));
        });
        const [theme, setTheme] = useState(() => {
            const saved = localStorage.getItem('v5_theme');
            return saved && saved !== 'classic' ? saved : 'gemini';
        });
        const [selectedAnalysisSymbol, setSelectedAnalysisSymbol] = useState(null);
        const [hermesNotifications, setHermesNotifications] = useState([]);
        const [hermesCompliance, setHermesCompliance] = useState(null);

        useEffect(() => {
            window.openDeepAnalysis = (sym) => setSelectedAnalysisSymbol(sym);
        }, []);

        useEffect(() => {
            localStorage.setItem('v5_theme', theme);
        }, [theme]);

        // [HERMES] Notification event listeners
        let hermesNotifCounter = 0;
        useEffect(() => {
            const handleNotif = (e) => {
                const notifId = ++hermesNotifCounter;
                setHermesNotifications(prev => {
                    const next = [...prev, { ...e.detail, id: notifId, timestamp: new Date().toISOString() }];
                    if (next.length > 10) next.shift();
                    return next;
                });
                setTimeout(() => {
                    setHermesNotifications(prev => prev.filter(n => n.id !== notifId));
                }, 8000);
            };
            const handleCompliance = (e) => {
                setHermesCompliance(e.detail);
            };
            window.addEventListener('hermes-notification', handleNotif);
            window.addEventListener('hermes-compliance', handleCompliance);
            return () => {
                window.removeEventListener('hermes-notification', handleNotif);
                window.removeEventListener('hermes-compliance', handleCompliance);
            };
        }, []);

        useEffect(() => {
            const shield = document.getElementById('boot-shield');
            if (shield) {
                // V110.171: Manter a tela de boot visível para a animação "Neural Interface"
                setTimeout(() => {
                    shield.style.opacity = '0';
                    setTimeout(() => {
                        shield.style.display = 'none';
                        shield.remove();
                    }, 1200); // 1.2s fade out
                }, 3500); // 3.5s tempo total de exibição
            }
        }, []);

        // [V110.150] PWA Registration & Update Protocol
        const [showUpdate, setShowUpdate] = useState(false);
        const [waitingWorker, setWaitingWorker] = useState(null);

        useEffect(() => {
            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.register('/sw.js?v=125.600').then(reg => {
                    // Detect updates
                    reg.addEventListener('updatefound', () => {
                        const newWorker = reg.installing;
                        newWorker.addEventListener('statechange', () => {
                            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                                setWaitingWorker(newWorker);
                                setShowUpdate(true);
                            }
                        });
                    });
                });
            }
        }, []);

        const updateApp = () => {
            if (waitingWorker) {
                waitingWorker.postMessage({ type: 'SKIP_WAITING' });
            }
            setShowUpdate(false);
        };

        const handleLogout = () => {
            localStorage.removeItem('auth_token');
            localStorage.removeItem('sniper_token');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('user');
            setIsAuthenticated(false);
        };

        if (!isAuthenticated) {
            window.location.replace('/login');
            return null;
        }

        // Resolves components globally
        const Page10DComponent = window.Page10D || (() => null);
        const SettingsPageComponent = window.SettingsPage || (() => null);
        const AdminUsersPageComponent = window.AdminUsersPage || (() => null);
        const DeepAnalysisModalComponent = window.DeepAnalysisModal || (() => null);

        return (
            <ReactRouterDOM.HashRouter>
                <div className={`h-full ${theme === 'gemini' ? 'theme-gemini' : 'theme-classic'}`}>
                    <ReactRouterDOM.Routes>
                        <Route path="/" element={<Page10DComponent />} />
                        <Route path="/10d" element={<Page10DComponent />} />
                        {/* [HERMES DASHBOARD v2] Hermes Dashboard - substitui Kanban e Neural Chat */}
                        <Route path="/hermes" element={<div className="w-full h-full lg:pl-[80px] pb-[70px] lg:pb-0 overflow-hidden"><iframe src="/hermes" className="w-full h-full border-none" title="Hermes Dashboard" /></div>} />
                        <Route path="/neural-chat" element={<div className="w-full h-full lg:pl-[80px] pb-[70px] lg:pb-0 overflow-hidden"><iframe src="/neural-chat.html" className="w-full h-full border-none" title="Neural Chat Interface (legado)" /></div>} />
                        <Route path="/kanban" element={<ReactRouterDOM.Navigate to="/hermes" replace />} />
                        <Route path="/sandbox" element={<div className="w-full h-full lg:pl-[80px] pb-[70px] lg:pb-0 overflow-hidden"><iframe src="/sandbox" className="w-full h-full border-none" title="Sandbox Lab" /></div>} />
                        <Route path="/memory" element={<div className="w-full h-full lg:pl-[80px] pb-[70px] lg:pb-0 overflow-hidden"><iframe src="/memory" className="w-full h-full border-none" title="Memory Galaxy" /></div>} />
                        <Route path="/config" element={<SettingsPageComponent onLogout={handleLogout} theme={theme} setTheme={setTheme} />} />
                        <Route path="/adm" element={<AdminUsersPageComponent />} />
                    </ReactRouterDOM.Routes>
                    <NavBar onLogout={handleLogout} />
                </div>
                
                {/* [V110.182.9] PWA Update Toast */}
                {showUpdate && (
                    <div className="fixed bottom-24 left-4 right-4 z-[100] animate-bounce">
                        <div className="glass border border-primary/40 p-4 rounded-2xl flex items-center justify-between shadow-2xl">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
                                    <span className="material-icons-round text-white text-sm">system_update</span>
                                </div>
                                <div>
                                    <h4 className="text-xs font-black text-white uppercase">Update Sniper V110.900</h4>
                                    <p className="text-[9px] text-gray-400 font-bold uppercase">Novas inteligências detectadas!</p>
                                </div>
                            </div>
                            <button 
                                onClick={updateApp}
                                className="bg-primary text-black text-[10px] font-black px-4 py-2 rounded-xl uppercase tracking-tighter"
                            >
                                Atualizar Agora
                            </button>
                        </div>
                    </div>
                )}

                {/* [HERMES] Notification Toasts */}
                {hermesNotifications.length > 0 && hermesNotifications.map((notif, i) => (
                    <div key={notif.id} className="fixed bottom-36 left-4 right-4 z-[110] transition-all duration-500 pointer-events-none"
                         style={{ transform: `translateY(-${i * 80}px)`, opacity: 1 }}>
                        <div className={"glass border rounded-2xl p-4 flex items-start gap-3 shadow-2xl pointer-events-auto " +
                            (notif.severity === 'CRITICAL' ? 'border-red-500/50' :
                             notif.severity === 'WARNING' ? 'border-amber-500/50' : 'border-green-500/30')}>
                            <div className={"w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 " +
                                (notif.severity === 'CRITICAL' ? 'bg-red-500/20' :
                                 notif.severity === 'WARNING' ? 'bg-amber-500/20' : 'bg-green-500/20')}>
                                <span className="material-icons-round text-sm">
                                    {notif.severity === 'CRITICAL' ? 'error' :
                                     notif.severity === 'WARNING' ? 'warning' : 'check_circle'}
                                </span>
                            </div>
                            <div className="flex-1 min-w-0">
                                <h4 className="text-[10px] font-black text-white uppercase tracking-wider">{notif.title || 'HERMES'}</h4>
                                <p className="text-[9px] text-gray-400 mt-0.5 leading-relaxed">{notif.message}</p>
                            </div>
                            <button onClick={() => setHermesNotifications(prev => prev.filter(n => n.id !== notif.id))}
                                    className="w-6 h-6 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center flex-shrink-0 pointer-events-auto">
                                <span className="material-icons-round text-[10px] text-gray-500">close</span>
                            </button>
                        </div>
                    </div>
                ))}

                <DeepAnalysisModalComponent 
                    symbol={selectedAnalysisSymbol} 
                    onClose={() => setSelectedAnalysisSymbol(null)} 
                />
            </ReactRouterDOM.HashRouter>
        );
    };

    window.App = App;

    const startApp = () => {
        try {
            const rootEl = document.getElementById('root');
            if (!rootEl) {
                setTimeout(startApp, 100);
                return;
            }
            const createRootFn = (window.ReactDOM && window.ReactDOM.createRoot) || window.createRoot || (typeof ReactDOM !== 'undefined' && ReactDOM.createRoot);
            if (!createRootFn) throw new Error("React DOM createRoot not found");
            const root = createRootFn(rootEl);
            root.render(<App />);
        } catch (err) {
            console.error("MOUNT FAILURE:", err);
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startApp);
    } else {
        startApp();
    }
})();
