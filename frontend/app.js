(function() {
    const { useState, useEffect, useRef, useMemo } = window.React;
    const { Link, Route, useLocation, useNavigate } = window.ReactRouterDOM;

    // =========================================================================
    // NavBar — 3 Botões: BANCA / HERMES / ADM (submenu: GALAXY, SANDBOX, CONFIG)
    // =========================================================================
    const NavBar = ({ onLogout }) => {
        const location = useLocation();
        const [admOpen, setAdmOpen] = React.useState(false);

        const NavBtn = ({ to, href, icon, label, isActive, targetSelf, isSpecial }) => {
            const base = `flex flex-col items-center justify-center gap-1 py-2 lg:py-3 px-2 rounded-xl transition-all duration-300 flex-1 lg:flex-none lg:w-full ${
                isActive 
                    ? (isSpecial 
                        ? 'text-primary bg-primary/20 border border-primary/50 shadow-[0_0_15px_rgba(34,197,94,0.3)] scale-105' 
                        : 'text-white bg-white/10 border border-white/20 shadow-[0_0_12px_rgba(255,255,255,0.1)]')
                    : (isSpecial
                        ? 'text-primary/80 hover:text-primary hover:bg-primary/10 border border-transparent hover:border-primary/20'
                        : 'text-gray-400 hover:text-white hover:bg-white/5 border border-transparent')
            }`;
            const content = (<>
                <span className={`material-icons-round transition-transform duration-300 ${isActive ? 'scale-110' : ''}`} style={{ fontSize: isSpecial ? '25px' : '22px' }}>{icon}</span>
                <span className="text-[9px] font-black tracking-widest uppercase mt-0.5 hidden lg:block">{label}</span>
                <span className="text-[7.5px] font-extrabold tracking-wider uppercase mt-0.5 lg:hidden">{label}</span>
            </>);
            if (href) return <a href={href} target={targetSelf ? "_self" : "_blank"} className={base} title={label}>{content}</a>;
            return <Link to={to} className={base} title={label}>{content}</Link>;
        };

        const isAdmActive = location.pathname === '/memory' || location.pathname === '/sandbox' || location.pathname === '/config' || location.pathname === '/adm';

        return (
            <nav className="fixed bottom-0 lg:bottom-auto lg:top-0 lg:left-0 lg:w-[80px] w-full lg:h-screen v5-bg-deep/95 backdrop-blur-xl z-[10000] pb-safe pt-2 lg:py-6 flex flex-col border-t lg:border-t-0 lg:border-r border-white/10 shadow-2xl" style={{ paddingBottom: 'max(env(safe-area-inset-bottom, 0px), 8px)' }}>
                <div className="mx-auto flex lg:flex-col items-center px-2 lg:px-2 w-full h-full gap-1 lg:gap-4">

                    {/* Logo — desktop apenas */}
                    <div className="hidden lg:flex flex-col items-center gap-2 mb-4">
                        <img src="/logo10DTrasp.png?v=4" alt="Logo" className="w-10 h-10 object-contain drop-shadow-[0_0_10px_rgba(255,215,0,0.3)]" />
                        <div className="h-[1px] w-8 bg-white/10"></div>
                    </div>

                    {/* ── 3 Botões: BANCA / HERMES / ADM ───────────────────────── */}
                    <div className="flex flex-row lg:flex-col items-center justify-around lg:justify-start gap-1 lg:gap-3 w-full flex-1">

                        {/* BANCA */}
                        <NavBtn
                            to="/"
                            icon="space_dashboard"
                            label="Banca"
                            isActive={location.pathname === '/' || location.pathname === '/10d'}
                        />

                        {/* HERMES (Oráculo AI - Destaque Central) */}
                        <NavBtn
                            to="/hermes"
                            icon="auto_awesome"
                            label="Hermes"
                            isActive={location.pathname === '/hermes'}
                            isSpecial={true}
                        />

                        {/* ADM (submenu) */}
                        <div className="relative flex-1 lg:flex-none lg:w-full flex justify-center">
                            <button
                                onClick={() => setAdmOpen(!admOpen)}
                                className={`flex flex-col items-center justify-center gap-1 py-2 lg:py-3 px-2 rounded-xl transition-all duration-300 flex-1 lg:flex-none lg:w-full ${
                                    admOpen || isAdmActive
                                        ? 'text-white bg-white/10 border border-white/20 shadow-[0_0_12px_rgba(255,255,255,0.1)]'
                                        : 'text-gray-400 hover:text-white hover:bg-white/5 border border-transparent'
                                }`}
                                title="ADM"
                            >
                                <span className={`material-icons-round transition-transform duration-300 ${admOpen ? 'rotate-45' : ''}`} style={{ fontSize: '22px' }}>admin_panel_settings</span>
                                <span className="text-[9px] font-black tracking-widest uppercase mt-0.5 hidden lg:block">ADM</span>
                                <span className="text-[7.5px] font-extrabold tracking-wider uppercase mt-0.5 lg:hidden">ADM</span>
                            </button>

                            {/* Submenu ADM — desktop: à direita / mobile: acima */}
                            {admOpen && (
                                <>
                                    <div className="fixed inset-0 z-[9999]" onClick={() => setAdmOpen(false)} />
                                    <div className="hidden lg:flex absolute left-[calc(100%+8px)] top-1/2 -translate-y-1/2 z-[10001] flex-col gap-1 p-2 rounded-2xl border border-white/10 bg-[rgba(8,8,12,0.97)] backdrop-blur-xl min-w-[180px] shadow-2xl">
                                        <span className="text-[8px] font-black text-primary/60 uppercase tracking-[0.2em] px-2 pb-1.5 border-b border-white/5 mb-1">ADM · Módulos</span>
                                        <a href="/memory" className={`flex items-center gap-2 px-3 py-2 rounded-xl text-[12px] font-semibold transition-all border border-transparent hover:bg-white/8 hover:text-white ${location.pathname === '/memory' ? 'text-white bg-white/8 border-white/15' : 'text-gray-300'}`}>
                                            <span className="material-icons-round text-[18px]">auto_awesome</span>
                                            <span>Galaxy</span>
                                        </a>
                                        <a href="/sandbox" className={`flex items-center gap-2 px-3 py-2 rounded-xl text-[12px] font-semibold transition-all border border-transparent hover:bg-white/8 hover:text-white ${location.pathname === '/sandbox' ? 'text-white bg-white/8 border-white/15' : 'text-gray-300'}`}>
                                            <span className="material-icons-round text-[18px]">science</span>
                                            <span>Sandbox</span>
                                        </a>
                                        <Link to="/config" onClick={() => setAdmOpen(false)} className={`flex items-center gap-2 px-3 py-2 rounded-xl text-[12px] font-semibold transition-all border border-transparent hover:bg-white/8 hover:text-white ${location.pathname === '/config' || location.pathname === '/adm' ? 'text-white bg-white/8 border-white/15' : 'text-gray-300'}`}>
                                            <span className="material-icons-round text-[18px]">settings</span>
                                            <span>Config</span>
                                        </Link>
                                    </div>
                                    <div className="lg:hidden fixed left-1/2 -translate-x-1/2 z-[10001] flex flex-col gap-1 p-2 rounded-2xl border border-white/10 bg-[rgba(8,8,12,0.97)] backdrop-blur-xl min-w-[200px] shadow-2xl" style={{ bottom: 'calc(100% + 8px)' }}>
                                        <span className="text-[8px] font-black text-primary/60 uppercase tracking-[0.2em] px-2 pb-1.5 border-b border-white/5 mb-1">ADM · Módulos</span>
                                        <a href="/memory" className={`flex items-center gap-2 px-3 py-2 rounded-xl text-[12px] font-semibold transition-all border border-transparent hover:bg-white/8 hover:text-white ${location.pathname === '/memory' ? 'text-white bg-white/8 border-white/15' : 'text-gray-300'}`}>
                                            <span className="material-icons-round text-[18px]">auto_awesome</span>
                                            <span>Galaxy</span>
                                        </a>
                                        <a href="/sandbox" className={`flex items-center gap-2 px-3 py-2 rounded-xl text-[12px] font-semibold transition-all border border-transparent hover:bg-white/8 hover:text-white ${location.pathname === '/sandbox' ? 'text-white bg-white/8 border-white/15' : 'text-gray-300'}`}>
                                            <span className="material-icons-round text-[18px]">science</span>
                                            <span>Sandbox</span>
                                        </a>
                                        <Link to="/config" onClick={() => setAdmOpen(false)} className={`flex items-center gap-2 px-3 py-2 rounded-xl text-[12px] font-semibold transition-all border border-transparent hover:bg-white/8 hover:text-white ${location.pathname === '/config' || location.pathname === '/adm' ? 'text-white bg-white/8 border-white/15' : 'text-gray-300'}`}>
                                            <span className="material-icons-round text-[18px]">settings</span>
                                            <span>Config</span>
                                        </Link>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Sair — desktop apenas, parte inferior */}
                    <div className="hidden lg:flex flex-col items-center gap-3 mt-auto">
                        <button onClick={onLogout} title="Sair do Sistema"
                            className="flex items-center justify-center p-3 rounded-xl bg-red-500/10 text-red-400 hover:bg-red-500/20 hover:text-red-300 transition-all border border-transparent hover:border-red-500/30">
                            <span className="material-icons-round" style={{ fontSize: '20px' }}>power_settings_new</span>
                        </button>
                    </div>

                </div>
            </nav>
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
