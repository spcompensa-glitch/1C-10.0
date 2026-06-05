(function() {
    const TriumphModal = ({ selectedHistoryLog, onClose }) => {
        if (!selectedHistoryLog) return null;

        const [visionReport, setVisionReport] = React.useState(null);
        const [loadingVision, setLoadingVision] = React.useState(true);
        const [isVisionOpen, setIsVisionOpen] = React.useState(true); // Abre por padrão para exibir toda a gênese
        const [expandedTriumphImage, setExpandedTriumphImage] = React.useState(null);

        React.useEffect(() => {
            const embeddedVision = selectedHistoryLog.vision_intel || selectedHistoryLog.data?.vision_intel;
            if (embeddedVision) {
                setVisionReport({ payload: embeddedVision });
                setLoadingVision(false);
                return;
            }

            const fetchVisionReport = async () => {
                try {
                    const res = await fetch(`${API_BASE}/api/vision/history`);
                    if (res.ok) {
                        const data = await res.json();
                        const match = data.find(ev => {
                            const sym = ev.payload?.symbol || "";
                            return sym.toUpperCase() === selectedHistoryLog.symbol.toUpperCase();
                        });
                        if (match) {
                            setVisionReport(match);
                        }
                    }
                } catch (e) {
                    console.error(e);
                } finally {
                    setLoadingVision(false);
                }
            };
            fetchVisionReport();
        }, [selectedHistoryLog]);

        let finalRoi = Number(selectedHistoryLog.final_roi || selectedHistoryLog.pnl_percent || selectedHistoryLog.roi || 0);
        const entry = Number(selectedHistoryLog.entry_price || 0);
        const exit = Number(selectedHistoryLog.exit_price || 0);
        const leverage = Number(selectedHistoryLog.leverage || 1);
        const margin = Number(selectedHistoryLog.margin || 0);
        const pnlUsd = Number(selectedHistoryLog.pnl || 0);

        // Fallback ROI: calcula sem multiplicar alavancagem (ROI já considera leverage via PnL)
        if (finalRoi === 0 && entry > 0 && exit > 0 && margin > 0) {
            const side = String(selectedHistoryLog.side || 'Buy').toUpperCase();
            const priceMove = (side === 'BUY' || side === 'LONG') ? (exit - entry) : (entry - exit);
            // ROI da posição = (move/entry) * leverage * 100
            finalRoi = (priceMove / entry) * leverage * 100;
        } else if (finalRoi === 0 && pnlUsd !== 0 && margin > 0) {
            // ROI simples sobre margem
            finalRoi = (pnlUsd / margin) * 100;
        }

        // ROI sobre entrada (banca risk): se tivermos margin e pnl
        const roiOnMargin = margin > 0 ? (pnlUsd / margin) * 100 : finalRoi;

        const isHighSuccess = finalRoi >= 100;
        const isAstronomical = finalRoi >= 500;
        const isProfit = pnlUsd >= 0;

        // Resolve global components
        const IntelIconComponent = window.IntelIcon || (() => null);
        const QualitySealComponent = window.QualitySeal || (() => null);

        return (
            <div className="fixed inset-0 z-[120] bg-black/90 backdrop-blur-2xl flex items-center justify-center p-6" onClick={onClose}>
                <div 
                    className={`premium-card w-full max-w-lg rounded-3xl border overflow-hidden animate-triumph ${isAstronomical ? 'victory-glow-prismatic' : isProfit ? 'victory-glow-emerald' : 'border-white/10'}`} 
                    style={{ display: 'flex', flexDirection: 'column', maxHeight: '85vh', boxSizing: 'border-box' }}
                    onClick={e => e.stopPropagation()}
                >
                    {/* Header de Triunfo */}
                    <div 
                        className={`triumph-modal-header ${isAstronomical ? 'bg-green-900/20' : isProfit ? 'bg-green-900/10' : 'bg-white/5'} border-b border-white/5 shrink-0`}
                    >
                        <div 
                            className={`triumph-modal-icon-container shrink-0 border ${isAstronomical ? 'bg-white/20 border-white/30' : 'bg-white/10 border-green-500/30'}`}
                        >
                            <span className={`material-icons-round text-white`} style={{ fontSize: '24px' }}>
                                {isAstronomical ? 'auto_awesome' : 'military_tech'}
                            </span>
                        </div>
                        <div className="min-w-0 flex-1" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            <h3 className={`font-black uppercase tracking-[0.15em] leading-tight truncate ${isAstronomical ? 'text-astronomical' : 'text-white'}`} style={{ fontSize: '14px', margin: 0, padding: 0 }}>
                                Briefing: <span className="text-primary">{selectedHistoryLog.symbol}</span>
                            </h3>
                            <span className="text-gray-400 uppercase font-bold tracking-widest leading-none" style={{ fontSize: '10px', margin: 0, padding: 0 }}>Protocolo Gênese-Vitória</span>
                        </div>
                        <button 
                            onClick={onClose} 
                            className="triumph-modal-close-btn shrink-0 rounded-full bg-white/5 hover:bg-white/10 transition-all group cursor-pointer"
                        >
                            <span className="material-icons-round text-gray-400 group-hover:text-white" style={{ fontSize: '18px' }}>close</span>
                        </button>
                    </div>

                    <div className="p-6 overflow-y-auto custom-scrollbar flex flex-col gap-6">
                        {/* BANNER DE RESULTADO */}
                        <div className="relative group p-5 rounded-2xl bg-white/[0.02] border border-white/5 flex flex-col items-center justify-center text-center overflow-hidden gap-2">
                            <div className="absolute inset-0 bg-gradient-to-b from-green-500/[0.03] to-transparent"></div>
                            
                            <span className="text-[9px] font-black text-gray-500 uppercase tracking-[0.3em]">Resultado Financeiro</span>

                            {/* PNL principal */}
                            <div className="flex items-center gap-3">
                                <p className={`text-4xl font-black font-mono tracking-tighter ${isAstronomical ? 'text-astronomical' : isProfit ? 'text-white' : 'text-red-400'}`}>
                                    {isProfit ? '+' : ''}${Math.abs(pnlUsd).toFixed(2)}
                                </p>
                                <div className={`px-2 py-1 rounded-lg border text-[11px] font-black font-mono ${isProfit ? 'bg-white/10 border-white/20 text-white' : 'bg-red-500/10 border-red-500/20 text-red-400'}`}>
                                    {roiOnMargin.toFixed(1)}% <span className="text-[8px] opacity-60">s/margem</span>
                                </div>
                            </div>

                            {/* Métricas secundárias */}
                            <div className="flex gap-4 mt-1">
                                {margin > 0 && (
                                    <div className="flex flex-col items-center">
                                        <span className="text-[8px] text-gray-600 uppercase tracking-widest">Margem</span>
                                        <span className="text-[10px] font-mono font-bold text-gray-400">${margin.toFixed(2)}</span>
                                    </div>
                                )}
                                {leverage > 1 && (
                                    <div className="flex flex-col items-center">
                                        <span className="text-[8px] text-gray-600 uppercase tracking-widest">Alavancagem</span>
                                        <span className="text-[10px] font-mono font-bold text-amber-400">{leverage}x</span>
                                    </div>
                                )}
                                {entry > 0 && exit > 0 && (
                                    <div className="flex flex-col items-center">
                                        <span className="text-[8px] text-gray-600 uppercase tracking-widest">Δ Preço</span>
                                        <span className={`text-[10px] font-mono font-bold ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                                            {isProfit ? '+' : ''}{((String(selectedHistoryLog.side || '').toUpperCase() === 'BUY' || String(selectedHistoryLog.side || '').toUpperCase() === 'LONG') ? (exit - entry) : (entry - exit)).toFixed(4)}
                                        </span>
                                    </div>
                                )}
                            </div>

                            {/* ROI BADGES */}
                            <div className="flex gap-2 mt-1 flex-wrap justify-center">
                                {roiOnMargin >= 20 && <span className="px-2 py-0.5 rounded-full bg-white/10 border border-green-500/30 text-[8px] font-black text-white uppercase tracking-widest">🌊 WAVE</span>}
                                {roiOnMargin >= 50 && <span className="px-2 py-0.5 rounded-full bg-white/10 border border-green-500/30 text-[8px] font-black text-white uppercase tracking-widest">⚡ VOLT</span>}
                                {roiOnMargin >= 100 && <span className="px-2 py-0.5 rounded-full bg-white/10 border border-green-500/30 text-[8px] font-black text-white uppercase tracking-widest">🚀 ROCKET</span>}
                                {roiOnMargin >= 300 && <span className="px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/30 text-[8px] font-black text-amber-300 uppercase tracking-widest">👑 CROWN</span>}
                                {isAstronomical && <span className="px-2 py-0.5 rounded-full bg-white/20 border border-white/30 text-[8px] font-black text-white uppercase tracking-widest animate-pulse">🌌 GOD MODE</span>}
                            </div>
                        </div>

                        {/* DNA DA VITÓRIA (GENESYS) */}
                        <div className="space-y-3">
                            <h4 className="text-[10px] font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                <span className="material-icons-round text-white text-sm">bolt</span>
                                DNA da Vitória (Gênese)
                            </h4>
                            
                            {selectedHistoryLog.fleet_intel && (
                                <div className="bg-black/40 rounded-2xl p-4 border border-white/5 flex items-center justify-between">
                                    <div className="flex gap-2">
                                        {selectedHistoryLog.fleet_intel.ignition ? (
                                            <>
                                                <IntelIconComponent type="micro" score={selectedHistoryLog.fleet_intel.micro || 50} icon="waves" label="WHL" />
                                                <IntelIconComponent type="mola" score={selectedHistoryLog.fleet_intel.ignition.breakdown?.mola || 0} icon="🌀" isEmoji={true} label="MOLA" />
                                                <IntelIconComponent type="pivo" score={selectedHistoryLog.fleet_intel.ignition.breakdown?.pivo || 0} icon="🔢" isEmoji={true} label="123" />
                                                <IntelIconComponent type="abcd" score={selectedHistoryLog.fleet_intel.ignition.breakdown?.abcd || 0} icon="📐" isEmoji={true} label="ABCD" />
                                            </>
                                        ) : (
                                            <>
                                                <IntelIconComponent type="macro" score={selectedHistoryLog.fleet_intel.macro || 50} icon="public" label="MAC" />
                                                <IntelIconComponent type="micro" score={selectedHistoryLog.fleet_intel.micro || 50} icon="waves" label="WHL" />
                                                <IntelIconComponent type="smc" score={selectedHistoryLog.fleet_intel.smc || 50} icon="bolt" label="SMC" />
                                            </>
                                        )}
                                    </div>
                                    <div className="flex flex-col items-end gap-1">
                                        {selectedHistoryLog.fleet_intel.nectar_seal && <QualitySealComponent seal={selectedHistoryLog.fleet_intel.nectar_seal} />}
                                        <div className="text-[8px] font-mono font-bold text-gray-500 uppercase">Score Original: {selectedHistoryLog.score} pts</div>
                                    </div>
                                </div>
                            )}

                            <div className="bg-black/60 p-5 rounded-2xl border border-white/10 relative">
                                <span className="absolute top-2 right-4 text-[7px] font-mono text-white/40 uppercase">Vincit Qui Patitur</span>
                                <p className="font-mono text-[10px] text-gray-300 leading-relaxed italic whitespace-pre-wrap">
                                    "{selectedHistoryLog.reasoning_report || selectedHistoryLog.pensamento || "A IA confirmou o padrão e executou o protocolo de elite com precisão cirúrgica."}"
                                </p>
                            </div>
                        </div>

                        {/* COMPLIANCE VISÃO - LAUDO E PRINT */}
                        <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/5 flex flex-col gap-3">
                            <button 
                                onClick={() => setIsVisionOpen(!isVisionOpen)}
                                className="w-full flex items-center justify-between p-3 rounded-xl bg-white/[0.04] border border-white/5 hover:bg-white/[0.08] transition-all group"
                            >
                                <div className="flex items-center gap-2">
                                    <span className="material-icons-round text-[16px] text-green-400">visibility</span>
                                    <span className="text-[10px] font-black text-white uppercase tracking-widest">Compliance Visão</span>
                                </div>
                                <span className="material-icons-round text-sm text-gray-500 group-hover:text-white transition-all">
                                    {isVisionOpen ? 'expand_less' : 'expand_more'}
                                </span>
                            </button>

                            {isVisionOpen && (
                                <div className="flex flex-col gap-4 animate-fade-in mt-2 border-t border-white/5 pt-3">
                                    {loadingVision ? (
                                        <div className="flex items-center justify-center p-4">
                                            <div className="w-5 h-5 border-2 border-green-500 border-t-transparent rounded-full animate-spin"></div>
                                        </div>
                                    ) : visionReport ? (
                                        <div className="flex flex-col gap-3">
                                            <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-2">
                                                <div className="flex justify-between items-center">
                                                    <span className="text-[8px] font-black text-green-400 uppercase tracking-widest">Resultado do Visão</span>
                                                    <span className="text-[9px] font-mono font-bold text-gray-400">{visionReport.payload?.decision}</span>
                                                </div>
                                                <p className="text-[10px] font-mono text-gray-300 leading-relaxed">
                                                    {visionReport.payload?.thoughts || visionReport.payload?.analysis}
                                                </p>
                                            </div>

                                            {(() => {
                                                // Prioriza a URL direta salva no log do trade ou na carga da visão
                                                const imgUrl = selectedHistoryLog.vision_url || visionReport.payload?.image_url || visionReport.payload?.screenshot_url;
                                                if (!imgUrl) return null;
                                                return (
                                                    <div className="p-2 bg-black/40 rounded-xl border border-white/5 flex flex-col gap-2">
                                                        <span className="text-[8px] font-black text-gray-500 uppercase tracking-widest">Print da Autorização</span>
                                                        <div 
                                                            className="rounded-lg overflow-hidden border border-white/10 relative cursor-pointer group"
                                                            onClick={() => setExpandedTriumphImage(imgUrl.startsWith('http') ? imgUrl : `${API_BASE}${imgUrl}`)}
                                                        >
                                                            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                                                                <span className="material-icons-round text-white">zoom_in</span>
                                                            </div>
                                                            <img 
                                                                src={imgUrl.startsWith('http') ? imgUrl : `${API_BASE}${imgUrl}`} 
                                                                alt="Análise Visão" 
                                                                className="w-full h-auto object-cover"
                                                            />
                                                        </div>
                                                    </div>
                                                );
                                            })()}
                                        </div>
                                    ) : (
                                        <div className="text-center p-4">
                                            <span className="text-[9px] font-mono text-gray-500 uppercase">Nenhum laudo visual arquivado para {selectedHistoryLog.symbol}</span>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* REGISTRO TÁTICO & TELEMETRIA */}
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-3">
                                <h5 className="text-[9px] font-black text-gray-500 uppercase tracking-widest flex items-center gap-1">
                                    <span className="material-icons-round text-[10px]">history_edu</span>
                                    Fatos da Missão
                                </h5>
                                <div className="space-y-2 p-3 rounded-xl bg-white/[0.02] border border-white/5">
                                    <div className="flex justify-between border-b border-white/5 pb-2">
                                        <span className="text-[8px] text-gray-600 uppercase font-bold">DNA Gênese</span>
                                        <span className="text-[9px] font-mono font-bold text-amber-500 truncate max-w-[120px]" title={selectedHistoryLog.genesis_id || 'RECOVERY-PROTO'}>{selectedHistoryLog.genesis_id || 'RECOVERY-PROTO'}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-white/5 pb-2">
                                        <span className="text-[8px] text-gray-600 uppercase font-bold">Lado</span>
                                        <span className={`text-[9px] font-black uppercase ${String(selectedHistoryLog.side).toUpperCase() === 'BUY' || String(selectedHistoryLog.side).toUpperCase() === 'LONG' ? 'text-green-400' : 'text-red-400'}`}>
                                            {selectedHistoryLog.side || 'LONG'}
                                        </span>
                                    </div>
                                    <div className="flex justify-between border-b border-white/5 pb-2">
                                        <span className="text-[8px] text-gray-600 uppercase font-bold">Preço Entrada</span>
                                        <span className="text-[9px] font-mono font-bold text-white">${Number(selectedHistoryLog.entry_price || 0).toFixed(5)}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-white/5 pb-2">
                                        <span className="text-[8px] text-gray-600 uppercase font-bold">Preço Saída</span>
                                        <span className="text-[9px] font-mono font-bold text-white">${Number(selectedHistoryLog.exit_price || 0).toFixed(5)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-[8px] text-gray-600 uppercase font-bold">Motivo</span>
                                        <span className="text-[9px] font-black text-white uppercase truncate ml-2 text-right" title={selectedHistoryLog.close_reason || "COLHEITA"}>{selectedHistoryLog.close_reason || "COLHEITA"}</span>
                                    </div>
                                </div>
                            </div>
                            <div className="space-y-3">
                                <h5 className="text-[9px] font-black text-gray-500 uppercase tracking-widest flex items-center gap-1">
                                    <span className="material-icons-round text-[10px]">analytics</span>
                                    Telemetria Gênese
                                </h5>
                                <div className="space-y-2 p-3 rounded-xl bg-white/[0.02] border border-white/5">
                                    <div className="flex justify-between border-b border-white/5 pb-2">
                                        <span className="text-[8px] text-gray-600 uppercase font-bold">Batalhão</span>
                                        <span className="text-[9px] font-black text-gray-300 uppercase">{selectedHistoryLog.slot_type || "BLITZ"}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-white/5 pb-2">
                                        <span className="text-[8px] text-gray-600 uppercase font-bold">BTC ADX (Entry)</span>
                                        <span className="text-[9px] font-mono font-bold text-blue-400">{selectedHistoryLog.btc_adx_at_entry || '---'}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-white/5 pb-2">
                                        <span className="text-[8px] text-gray-600 uppercase font-bold">Regime Mkt</span>
                                        <span className="text-[9px] font-mono font-bold text-amber-500 uppercase">{selectedHistoryLog.market_regime || 'TRENDING'}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-white/5 pb-2">
                                        <span className="text-[8px] text-gray-600 uppercase font-bold">Protocolo</span>
                                        <span className="text-[9px] font-mono font-bold text-white">{selectedHistoryLog.strategy || 'SNIPER'}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-[8px] text-gray-600 uppercase font-bold">Alavancagem</span>
                                        <span className="text-[9px] font-mono font-bold text-white">{selectedHistoryLog.leverage || '50'}x</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5 text-center">
                            <span className="text-[8px] font-bold text-gray-600 uppercase tracking-[0.2em]">Encerramento da Missão: {selectedHistoryLog.close_time ? new Date(selectedHistoryLog.close_time).toLocaleString('pt-BR') : "LOG Sincronizado"}</span>
                        </div>
                    </div>
                </div>
                
                {expandedTriumphImage && (
                    <div className="fixed inset-0 z-[300] bg-black/95 backdrop-blur-md flex items-center justify-center p-4" onClick={() => setExpandedTriumphImage(null)}>
                        <button className="absolute top-6 right-6 w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-white transition-colors">
                            <span className="material-icons-round">close</span>
                        </button>
                        <img src={expandedTriumphImage} className="max-w-full max-h-[90vh] object-contain rounded-xl border border-white/10" alt="Expanded Vision Print" onClick={e => e.stopPropagation()} />
                    </div>
                )}
            </div>
        );
    };

    window.TriumphModal = TriumphModal;
})();
