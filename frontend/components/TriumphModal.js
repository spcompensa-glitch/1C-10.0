(function() {
    const TriumphModal = ({ selectedHistoryLog, onClose }) => {
        if (!selectedHistoryLog) return null;

        const [isConsensusOpen, setIsConsensusOpen] = React.useState(true);
        const [marketStudy, setMarketStudy] = React.useState(null);
        const [isLoadingStudy, setIsLoadingStudy] = React.useState(false);

        let finalRoi = Number(selectedHistoryLog.final_roi || selectedHistoryLog.pnl_percent || selectedHistoryLog.roi || 0);
        const entry = Number(selectedHistoryLog.entry_price || 0);
        const exit = Number(selectedHistoryLog.exit_price || 0);
        const leverage = Number(selectedHistoryLog.leverage || 1);
        const margin = Number(selectedHistoryLog.margin || selectedHistoryLog.entry_margin || 0);
        const pnlUsd = Number(selectedHistoryLog.pnl || 0);

        // Fallback ROI: calcula sem multiplicar alavancagem (ROI já considera leverage via PnL)
        if (finalRoi === 0 && entry > 0 && exit > 0 && margin > 0) {
            const side = String(selectedHistoryLog.side || 'Buy').toUpperCase();
            const priceMove = (side === 'BUY' || side === 'LONG') ? (exit - entry) : (entry - exit);
            finalRoi = (priceMove / entry) * leverage * 100;
        } else if (finalRoi === 0 && pnlUsd !== 0 && margin > 0) {
            finalRoi = (pnlUsd / margin) * 100;
        }

        const roiOnMargin = margin > 0 ? (pnlUsd / margin) * 100 : finalRoi;
        const isHighSuccess = finalRoi >= 100;
        const isAstronomical = finalRoi >= 500;
        const isProfit = pnlUsd >= 0;
        const contractQuality = selectedHistoryLog.contract_quality || selectedHistoryLog.fleet_intel?.contract_quality || selectedHistoryLog.data?.contract_quality || {};
        const contractInfo = selectedHistoryLog.contract_info || selectedHistoryLog.contract || selectedHistoryLog.fleet_intel?.contract_info || contractQuality.contract_info || selectedHistoryLog.data?.contract_info || {};
        const contractCtVal = Number(contractInfo.ctVal || contractInfo.ct_val || 0);
        const contractTick = Number(contractInfo.tickSize || contractInfo.tick_size || 0);
        const contractLot = Number(contractInfo.lotSize || contractInfo.qtyStep || contractInfo.qty_step || 0);
        const contractMinQty = Number(contractInfo.minQty || contractInfo.min_qty || 0);
        const contractMaxLev = Number(contractInfo.maxLeverage || contractInfo.max_leverage || selectedHistoryLog.leverage || 50);
        const contractRiskImpact = Number(contractInfo.riskImpactPerContract || contractInfo.price_impact_per_contract || 0);
        const contractMinMargin = Number(contractInfo.minMarginRequired || contractInfo.min_margin_required || 0);
        const contractCurrentPrice = Number(contractInfo.currentPrice || contractInfo.current_price || selectedHistoryLog.entry_price_signal || 0);
        const contractQualityScore = Number(contractQuality.score || 0);
        const contractQualityReasons = Array.isArray(contractQuality.reasons) ? contractQuality.reasons : [];
        const hasContractInfo = selectedHistoryLog.is_signal && (
            contractCtVal > 0 || contractTick > 0 || contractLot > 0 || contractMinQty > 0
        );

        // Fetch dinâmico do estudo de mercado (Opção A)
        React.useEffect(() => {
            if (selectedHistoryLog && selectedHistoryLog.is_signal && selectedHistoryLog.symbol) {
                setIsLoadingStudy(true);
                const cleanSymbol = selectedHistoryLog.symbol.replace(".P", "").replace(".p", "").toUpperCase();
                fetch(`/api/market/study?symbol=${cleanSymbol}&interval=30`)
                    .then(r => r.json())
                    .then(data => {
                        setMarketStudy(data);
                        setIsLoadingStudy(false);
                    })
                    .catch(err => {
                        console.error("Erro ao carregar estudo do radar:", err);
                        setIsLoadingStudy(false);
                    });
            } else {
                setMarketStudy(null);
            }
        }, [selectedHistoryLog]);

        // Resolve global components
        const IntelIconComponent = window.IntelIcon || (() => null);
        const QualitySealComponent = window.QualitySeal || (() => null);
        const intel = selectedHistoryLog.fleet_intel || selectedHistoryLog.data?.fleet_intel || {};

        return (            <div className="fixed inset-0 z-[10500] bg-black/90 backdrop-blur-2xl flex items-center justify-center p-6" onClick={onClose}>
                <div 
                    className={`premium-card w-full max-w-lg rounded-3xl border overflow-hidden animate-triumph ${isAstronomical ? 'victory-glow-prismatic' : isProfit ? 'victory-glow-emerald' : 'border-white/10'}`} 
                    style={{ maxHeight: '85vh', boxSizing: 'border-box', position: 'relative', display: 'flex', flexDirection: 'column' }}
                    onClick={e => e.stopPropagation()}
                >
                    {/* Header de Triunfo Integrado */}
                    <div 
                        className={`border-b border-white/5 ${isAstronomical ? 'bg-green-950/20' : isProfit ? 'bg-green-950/10' : 'bg-red-950/10'}`}
                        style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '16px 24px', boxSizing: 'border-box', flexShrink: 0, zIndex: 100, backgroundColor: '#0a0a0f' }}
                    >
                        {/* Linha 1: Título e Botão Fechar */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyBetween: 'space-between', width: '100%' }}>
                            <div className="flex items-center gap-3">
                                <div 
                                    className={`triumph-modal-icon-container shrink-0 border ${isAstronomical ? 'bg-white/20 border-white/30' : 'bg-white/10 border-green-500/30'}`}
                                >
                                    <span className={`material-icons-round text-white`} style={{ fontSize: '24px' }}>
                                        {isAstronomical ? 'auto_awesome' : 'military_tech'}
                                    </span>
                                </div>
                                <div className="min-w-0 flex-1" style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                    <h3 className={`font-black uppercase tracking-[0.15em] leading-tight truncate ${isAstronomical ? 'text-astronomical' : 'text-white'}`} style={{ fontSize: '14px', margin: 0, padding: 0 }}>
                                        {selectedHistoryLog.is_signal ? 'Radar:' : 'Briefing:'} <span className="text-primary">{selectedHistoryLog.symbol}</span>
                                    </h3>
                                    <span className="text-gray-400 uppercase font-bold tracking-widest leading-none" style={{ fontSize: '10px', margin: 0, padding: 0 }}>
                                        {selectedHistoryLog.is_signal ? 'Análise de Sinal Ativo' : 'Protocolo Gênese-Vitória'}
                                    </span>
                                </div>
                            </div>
                            <button 
                                onClick={onClose} 
                                className="triumph-modal-close-btn shrink-0 rounded-full bg-white/5 hover:bg-white/10 transition-all group cursor-pointer"
                            >
                                <span className="material-icons-round text-gray-400 group-hover:text-white" style={{ fontSize: '18px' }}>close</span>
                            </button>
                        </div>

                        {/* Linha 2: Barra Financeira Fixa */}
                        {selectedHistoryLog.is_signal ? (
                            <div className="grid grid-cols-3 gap-2 bg-white/[0.02] border border-white/5 rounded-xl p-2.5">
                                <div className="flex flex-col items-center justify-center border-r border-white/5">
                                    <span className="text-[8px] text-gray-500 uppercase tracking-wider font-black">Score de Entrada</span>
                                    <span className="text-[11px] font-mono font-black text-amber-400">
                                        {Number(selectedHistoryLog.score || 0).toFixed(0)} pts
                                    </span>
                                </div>
                                <div className="flex flex-col items-center justify-center border-r border-white/5">
                                    <span className="text-[8px] text-gray-500 uppercase tracking-wider font-black">Direção</span>
                                    <span className={`text-[11px] font-mono font-bold ${(String(selectedHistoryLog.side).toUpperCase() === 'BUY' || String(selectedHistoryLog.side).toUpperCase() === 'LONG') ? 'text-green-400' : 'text-red-400'}`}>
                                        {String(selectedHistoryLog.side).toUpperCase()}
                                    </span>
                                </div>
                                <div className="flex flex-col items-center justify-center">
                                    <span className="text-[8px] text-gray-500 uppercase tracking-wider font-black">Estratégia</span>
                                    <span className="text-[11px] font-mono font-bold text-gray-300">
                                        {selectedHistoryLog.strategy || selectedHistoryLog.strategy_label || 'VELOCITY FLOW'}
                                    </span>
                                </div>
                            </div>
                        ) : (
                            <div className="grid grid-cols-4 gap-2 bg-white/[0.02] border border-white/5 rounded-xl p-2.5">
                                <div className="flex flex-col items-center justify-center border-r border-white/5">
                                    <span className="text-[8px] text-gray-500 uppercase tracking-wider font-black">Resultado</span>
                                    <span className={`text-[11px] font-mono font-black ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                                        {isProfit ? '+' : ''}${Math.abs(pnlUsd).toFixed(2)} ({roiOnMargin.toFixed(1)}%)
                                    </span>
                                </div>
                                <div className="flex flex-col items-center justify-center border-r border-white/5">
                                    <span className="text-[8px] text-gray-500 uppercase tracking-wider font-black">Margem</span>
                                    <span className="text-[11px] font-mono font-bold text-gray-300">${margin.toFixed(2)}</span>
                                </div>
                                <div className="flex flex-col items-center justify-center border-r border-white/5">
                                    <span className="text-[8px] text-gray-500 uppercase tracking-wider font-black">Alavancagem</span>
                                    <span className="text-[11px] font-mono font-bold text-amber-400">{leverage}x</span>
                                </div>
                                <div className="flex flex-col items-center justify-center">
                                    <span className="text-[8px] text-gray-500 uppercase tracking-wider font-black">Δ Preço</span>
                                    <span className={`text-[11px] font-mono font-bold ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                                        {isProfit ? '+' : ''}{((String(selectedHistoryLog.side || '').toUpperCase() === 'BUY' || String(selectedHistoryLog.side || '').toUpperCase() === 'LONG') ? (exit - entry) : (entry - exit)).toFixed(4)}
                                    </span>
                                </div>
                            </div>
                        )}

                        {/* ROI Badges compactos no cabeçalho */}
                        {!selectedHistoryLog.is_signal && (
                            <div className="flex gap-2 flex-wrap justify-center mt-1">
                                {roiOnMargin >= 20 && <span className="px-2 py-0.5 rounded-full bg-white/10 border border-green-500/30 text-[8px] font-black text-white uppercase tracking-widest">🌊 WAVE</span>}
                                {roiOnMargin >= 50 && <span className="px-2 py-0.5 rounded-full bg-white/10 border border-green-500/30 text-[8px] font-black text-white uppercase tracking-widest">⚡ VOLT</span>}
                                {roiOnMargin >= 100 && <span className="px-2 py-0.5 rounded-full bg-white/10 border border-green-500/30 text-[8px] font-black text-white uppercase tracking-widest">🚀 ROCKET</span>}
                                {roiOnMargin >= 300 && <span className="px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/30 text-[8px] font-black text-amber-300 uppercase tracking-widest">👑 CROWN</span>}
                                {isAstronomical && <span className="px-2 py-0.5 rounded-full bg-white/20 border border-white/30 text-[8px] font-black text-white uppercase tracking-widest animate-pulse">🌌 GOD MODE</span>}
                            </div>
                        )}
                    </div>

                    <div className="p-6 overflow-y-auto custom-scrollbar flex flex-col gap-6" style={{ flex: 1, boxSizing: 'border-box' }}>

                        {/* TELEMETRIA DINÂMICA (Apenas se for sinal ativo) */}
                        {selectedHistoryLog.is_signal && (
                            <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/5 space-y-4">
                                <h4 className="text-[10px] font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                    <span className="material-icons-round text-amber-400 text-sm">rocket_launch</span>
                                    Telemetria Técnica
                                </h4>

                                {isLoadingStudy ? (
                                    <div className="py-6 flex items-center justify-center gap-2">
                                        <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                                        <span className="text-[10px] font-mono text-gray-500 uppercase tracking-widest">Sintonizando Satélite...</span>
                                    </div>
                                ) : marketStudy ? (
                                    <div className="space-y-4">
                                        {/* Velocidade / Gás */}
                                        <div className="space-y-1">
                                            <div className="flex justify-between text-[9px] font-mono font-bold">
                                                <span className="text-gray-500 uppercase">GÁS DO ATIVO (VELOCIDADE)</span>
                                                <span className="text-amber-400">🔥 {(marketStudy.patterns_mola && marketStudy.patterns_mola.length > 0) ? (marketStudy.patterns_mola[0].compression * 100).toFixed(0) : "45"} km/h</span>
                                            </div>
                                            <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                                                <div 
                                                    className="h-full bg-gradient-to-r from-emerald-500 to-amber-500 transition-all duration-500"
                                                    style={{ width: `${(marketStudy.patterns_mola && marketStudy.patterns_mola.length > 0) ? marketStudy.patterns_mola[0].compression * 100 : 45}%` }}
                                                ></div>
                                            </div>
                                        </div>

                                        {/* RSI comparativo e Alinhamento SMA */}
                                        <div className="grid grid-cols-2 gap-3 pt-1">
                                            <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-1">
                                                <span className="text-[8px] font-black text-blue-400 uppercase tracking-widest">RSI (30M)</span>
                                                <div className="flex justify-between items-center mt-1">
                                                    <span className="text-[9px] text-gray-400 font-bold">Ativo:</span>
                                                    <span className="text-[10px] font-mono font-black text-white">{(marketStudy.rsi_2h || 50).toFixed(1)}</span>
                                                </div>
                                                <div className="flex justify-between items-center">
                                                    <span className="text-[9px] text-gray-400 font-bold">Status:</span>
                                                    <span className={`text-[9px] font-bold uppercase ${marketStudy.rsi_2h > 70 ? 'text-red-400' : marketStudy.rsi_2h < 30 ? 'text-green-400' : 'text-gray-400'}`}>
                                                        {marketStudy.rsi_2h > 70 ? 'Sobrequente' : marketStudy.rsi_2h < 30 ? 'Sobrefrio' : 'Estável'}
                                                    </span>
                                                </div>
                                            </div>

                                            <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-1">
                                                <span className="text-[8px] font-black text-purple-400 uppercase tracking-widest">Confluência SMA</span>
                                                <div className="flex justify-between items-center mt-1">
                                                    <span className="text-[9px] text-gray-400 font-bold">Médias:</span>
                                                    <span className="text-[10px] font-mono font-black text-white">8 vs 21</span>
                                                </div>
                                                <div className="flex justify-between items-center">
                                                    <span className="text-[9px] text-gray-400 font-bold">Tendência:</span>
                                                    <span className={`text-[9px] font-bold uppercase ${marketStudy.swing_alignment === 'BULLISH_CROSS' ? 'text-green-400' : 'text-red-400'}`}>
                                                        {marketStudy.swing_alignment === 'BULLISH_CROSS' ? 'Bullish (Cross)' : 'Bearish (Cross)'}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Detecção de Padrões Geométricos e DVAP */}
                                        <div className="flex flex-wrap gap-2">
                                            {marketStudy.is_dvap_active && <span className="px-2 py-0.5 rounded bg-green-500/10 border border-green-500/30 text-[8px] font-black text-green-400 uppercase tracking-widest">🧬 DVAP ATIVO</span>}
                                            {marketStudy.patterns_mola && marketStudy.patterns_mola.length > 0 && <span className="px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-[8px] font-black text-amber-400 uppercase tracking-widest">🌀 MOLA COMPRIMIDA</span>}
                                            {marketStudy.patterns_abcd && marketStudy.patterns_abcd.length > 0 && <span className="px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/30 text-[8px] font-black text-blue-400 uppercase tracking-widest">📐 ABCD DETECTADO</span>}
                                        </div>

                                        {/* Fib Targets se DVAP estiver ativo */}
                                        {marketStudy.is_dvap_active && marketStudy.dvap_data && (
                                            <div className="bg-black/60 p-3.5 rounded-xl border border-white/10 space-y-2">
                                                <div className="flex justify-between items-center text-[9px] font-black text-gray-400 uppercase tracking-wider">
                                                    <span>Fibonacci estrutural (Alvos)</span>
                                                    <span className="text-green-400 font-bold">{marketStudy.dvap_data.side}</span>
                                                </div>
                                                <div className="grid grid-cols-3 gap-2 font-mono text-[9px]">
                                                    <div className="flex flex-col bg-white/[0.02] border border-white/5 rounded p-1.5">
                                                        <span className="text-gray-500 text-[8px]">STOP LOSS</span>
                                                        <span className="text-red-400 font-bold">${Number(marketStudy.dvap_data.sl).toFixed(5)}</span>
                                                    </div>
                                                    <div className="flex flex-col bg-white/[0.02] border border-white/5 rounded p-1.5">
                                                        <span className="text-gray-500 text-[8px]">ALVO TP1</span>
                                                        <span className="text-green-400 font-bold">${Number(marketStudy.dvap_data.tp1).toFixed(5)}</span>
                                                    </div>
                                                    <div className="flex flex-col bg-white/[0.02] border border-white/5 rounded p-1.5">
                                                        <span className="text-gray-500 text-[8px]">ALVO TP2</span>
                                                        <span className="text-green-400 font-bold">${Number(marketStudy.dvap_data.tp2).toFixed(5)}</span>
                                                    </div>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <span className="text-[9px] font-mono text-gray-500 uppercase tracking-widest block text-center py-2">Sem resposta dos sensores</span>
                                )}
                            </div>
                        )}

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

                        {/* CONSENSO DA FROTA - GÊNESE DO SINAL */}
                        <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/5 flex flex-col gap-3">
                            <button 
                                onClick={() => setIsConsensusOpen(!isConsensusOpen)}
                                className="w-full flex items-center justify-between p-3 rounded-xl bg-white/[0.04] border border-white/5 hover:bg-white/[0.08] transition-all group"
                            >
                                <div className="flex items-center gap-2">
                                    <span className="material-icons-round text-[16px] text-green-400">analytics</span>
                                    <span className="text-[10px] font-black text-white uppercase tracking-widest">Consenso da Frota (Gênese)</span>
                                </div>
                                <span className="material-icons-round text-sm text-gray-500 group-hover:text-white transition-all">
                                    {isConsensusOpen ? 'expand_less' : 'expand_more'}
                                </span>
                            </button>

                            {isConsensusOpen && (
                                <div className="flex flex-col gap-4 animate-fade-in mt-2 border-t border-white/5 pt-3">
                                    {/* Grid de Agentes */}
                                    <div className="grid grid-cols-2 gap-3">
                                        {/* Bibliotecário */}
                                        <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-1">
                                            <span className="text-[8px] font-black text-amber-400 uppercase tracking-widest">📚 Bibliotecário</span>
                                            <div className="flex justify-between items-center mt-1">
                                                <span className="text-[9px] text-gray-400 font-bold">Selo:</span>
                                                <span className="text-[9px] font-black text-white bg-white/5 px-2 py-0.5 rounded uppercase tracking-wider">{intel.nectar_seal || '🛡️ VANGUARD'}</span>
                                            </div>
                                            <div className="flex justify-between items-center">
                                                <span className="text-[9px] text-gray-400 font-bold">Tendência H4:</span>
                                                <span className={`text-[9px] font-mono font-bold ${intel.dna?.trend_4h === 'UP' ? 'text-green-400' : intel.dna?.trend_4h === 'DOWN' ? 'text-red-400' : 'text-gray-400'}`}>
                                                    {intel.dna?.trend_4h || 'NEUTRAL'}
                                                </span>
                                            </div>
                                        </div>

                                        {/* Whale Tracker */}
                                        <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-1">
                                            <span className="text-[8px] font-black text-blue-400 uppercase tracking-widest">🐋 Whale Tracker</span>
                                            <div className="flex justify-between items-center mt-1">
                                                <span className="text-[9px] text-gray-400 font-bold">Fluxo:</span>
                                                <span className={`text-[9px] font-black bg-white/5 px-2 py-0.5 rounded uppercase tracking-wider ${intel.bias === 'ACCUMULATION' ? 'text-green-400' : intel.bias === 'DISTRIBUTION' ? 'text-amber-400' : 'text-gray-400'}`}>
                                                    {intel.bias || 'NEUTRAL'}
                                                </span>
                                            </div>
                                            <div className="flex justify-between items-center">
                                                <span className="text-[9px] text-gray-400 font-bold">Presença:</span>
                                                <span className="text-[9px] font-mono font-bold text-white uppercase">{intel.whale || 'NEUTRAL'}</span>
                                            </div>
                                        </div>

                                        {/* Macro Analyst */}
                                        <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-1">
                                            <span className="text-[8px] font-black text-purple-400 uppercase tracking-widest">🌐 Macro Analyst</span>
                                            <div className="flex justify-between items-center mt-1">
                                                <span className="text-[9px] text-gray-400 font-bold">Confiança:</span>
                                                <span className="text-[9px] font-mono font-bold text-white">{(intel.macro_score || intel.macro || 50)}%</span>
                                            </div>
                                            <div className="flex justify-between items-center">
                                                <span className="text-[9px] text-gray-400 font-bold">Risco:</span>
                                                <span className="text-[9px] font-mono font-bold text-white">{intel.dna?.trap_risk ? 'ALTO (TRAP)' : 'CONTROLADO'}</span>
                                            </div>
                                        </div>

                                        {/* Sentiment Specialist */}
                                        <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-1">
                                            <span className="text-[8px] font-black text-cyan-400 uppercase tracking-widest">🧠 Sentimento Retail</span>
                                            <div className="flex justify-between items-center mt-1">
                                                <span className="text-[9px] text-gray-400 font-bold">OnChain:</span>
                                                <span className="text-[9px] font-mono font-bold text-white">{(intel.onchain_score || intel.onchain || 50)}%</span>
                                            </div>
                                            <div className="flex justify-between items-center">
                                                <span className="text-[9px] text-gray-400 font-bold">Score Geral:</span>
                                                <span className="text-[9px] font-mono font-bold text-white">{(intel.sentiment_score || 50)}%</span>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Detalhes On-Chain / Ponto de Dor */}
                                    {intel.onchain_summary && intel.onchain_summary !== 'N/A' && (
                                        <div className="p-3 bg-black/40 rounded-xl border border-white/5">
                                            <span className="text-[8px] font-black text-gray-500 uppercase tracking-widest block mb-1">Resumo do Sentimento Técnico</span>
                                            <p className="text-[10px] font-mono text-gray-300 leading-relaxed">
                                                {intel.onchain_summary}
                                            </p>
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
                                    {selectedHistoryLog.is_signal ? 'Fatos do Sinal' : 'Fatos da Missão'}
                                </h5>
                                {selectedHistoryLog.is_signal ? (
                                    <div className="space-y-2 p-3 rounded-xl bg-white/[0.02] border border-white/5">
                                        <div className="flex justify-between border-b border-white/5 pb-2">
                                            <span className="text-[8px] text-gray-600 uppercase font-bold">DNA Gênese</span>
                                            <span className="text-[9px] font-mono font-bold text-amber-500 truncate max-w-[120px]">SINAL-ATIVO</span>
                                        </div>
                                        <div className="flex justify-between border-b border-white/5 pb-2">
                                            <span className="text-[8px] text-gray-600 uppercase font-bold">Lado</span>
                                            <span className={`text-[9px] font-black uppercase ${String(selectedHistoryLog.side).toUpperCase() === 'BUY' || String(selectedHistoryLog.side).toUpperCase() === 'LONG' ? 'text-green-400' : 'text-red-400'}`}>
                                                {selectedHistoryLog.side || 'LONG'}
                                            </span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-[8px] text-gray-600 uppercase font-bold">Score Radar</span>
                                            <span className="text-[9px] font-mono font-bold text-white">{(selectedHistoryLog.score || 0).toFixed(0)}</span>
                                        </div>
                                    </div>
                                ) : (
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
                                )}
                            </div>
                            <div className="space-y-3">
                                <h5 className="text-[9px] font-black text-gray-500 uppercase tracking-widest flex items-center gap-1">
                                    <span className="material-icons-round text-[10px]">analytics</span>
                                    {selectedHistoryLog.is_signal ? 'Telemetria do Sinal' : 'Telemetria Gênese'}
                                </h5>
                                {selectedHistoryLog.is_signal ? (
                                    <div className="space-y-2 p-3 rounded-xl bg-white/[0.02] border border-white/5">
                                        <div className="flex justify-between border-b border-white/5 pb-2">
                                            <span className="text-[8px] text-gray-600 uppercase font-bold">Batalhão</span>
                                            <span className="text-[9px] font-black text-gray-300 uppercase">{selectedHistoryLog.strategy_label || "BLITZ"}</span>
                                        </div>
                                        <div className="flex justify-between border-b border-white/5 pb-2">
                                            <span className="text-[8px] text-gray-600 uppercase font-bold">Status</span>
                                            <span className="text-[9px] font-mono font-bold text-blue-400">MONITORANDO</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-[8px] text-gray-600 uppercase font-bold">Alavancagem</span>
                                            <span className="text-[9px] font-mono font-bold text-white">50x</span>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="space-y-2 p-3 rounded-xl bg-white/[0.02] border border-white/5">
                                        <div className="flex justify-between border-b border-white/5 pb-2">
                                            <span className="text-[8px] text-gray-600 uppercase font-bold">Batalhão</span>
                                            <span className="text-[9px] font-black text-gray-300 uppercase">
                                                {(() => {
                                                    const raw_strat = selectedHistoryLog.strategy || selectedHistoryLog.slot_type || "VELOCITY FLOW";
                                                    const raw_strat_upper = String(raw_strat).toUpperCase();
                                                    if (raw_strat_upper in {"ALPHA SHIELD":1, "VELOCITY FLOW":1, "DECOR SHADOW":1}) return raw_strat_upper;
                                                    if (["DVAP", "MOLA", "FAS"].includes(raw_strat_upper)) return "ALPHA SHIELD";
                                                    if (["DECOR", "DECOR_HUNTER"].includes(raw_strat_upper)) return "DECOR SHADOW";
                                                    return "VELOCITY FLOW";
                                                })()}
                                            </span>
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
                                            <span className="text-[9px] font-mono font-bold text-white">{selectedHistoryLog.strategy || 'VELOCITY FLOW'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-[8px] text-gray-600 uppercase font-bold">Alavancagem</span>
                                            <span className="text-[9px] font-mono font-bold text-white">{selectedHistoryLog.leverage || '50'}x</span>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        {hasContractInfo && (
                            <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/5 flex flex-col gap-3">
                                <h4 className="text-[10px] font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                    <span className="material-icons-round text-cyan-400 text-sm">precision_manufacturing</span>
                                    Contrato OKX & Matemática do Preço
                                    {contractQualityScore > 0 && (
                                        <span className={`ml-auto text-[8px] font-mono font-black ${contractQualityScore >= 80 ? 'text-green-400' : contractQualityScore >= 60 ? 'text-amber-400' : 'text-red-400'}`}>
                                            Q {contractQualityScore.toFixed(0)}
                                        </span>
                                    )}
                                </h4>
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-1">
                                        <span className="text-[8px] font-black text-cyan-400 uppercase tracking-widest">Tamanho do Contrato</span>
                                        <div className="flex justify-between items-center mt-1">
                                            <span className="text-[9px] text-gray-400 font-bold">ctVal:</span>
                                            <span className="text-[9px] font-mono font-bold text-white">{contractCtVal || '---'}</span>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-[9px] text-gray-400 font-bold">Lote/Step:</span>
                                            <span className="text-[9px] font-mono font-bold text-white">{contractLot || '---'}</span>
                                        </div>
                                    </div>
                                    <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-1">
                                        <span className="text-[8px] font-black text-amber-400 uppercase tracking-widest">Precisão</span>
                                        <div className="flex justify-between items-center mt-1">
                                            <span className="text-[9px] text-gray-400 font-bold">Tick:</span>
                                            <span className="text-[9px] font-mono font-bold text-white">{contractTick || '---'}</span>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-[9px] text-gray-400 font-bold">Min Qty:</span>
                                            <span className="text-[9px] font-mono font-bold text-white">{contractMinQty || '---'}</span>
                                        </div>
                                    </div>
                                    <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-1">
                                        <span className="text-[8px] font-black text-purple-400 uppercase tracking-widest">Alavancagem</span>
                                        <div className="flex justify-between items-center mt-1">
                                            <span className="text-[9px] text-gray-400 font-bold">Máx OKX:</span>
                                            <span className="text-[9px] font-mono font-bold text-white">{contractMaxLev || 50}x</span>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-[9px] text-gray-400 font-bold">Preço Ref:</span>
                                            <span className="text-[9px] font-mono font-bold text-white">${contractCurrentPrice ? contractCurrentPrice.toFixed(6) : '---'}</span>
                                        </div>
                                    </div>
                                    <div className="p-3 bg-black/40 rounded-xl border border-white/5 space-y-1">
                                        <span className="text-[8px] font-black text-green-400 uppercase tracking-widest">Risco por Contrato</span>
                                        <div className="flex justify-between items-center mt-1">
                                            <span className="text-[9px] text-gray-400 font-bold">Impacto:</span>
                                            <span className="text-[9px] font-mono font-bold text-white">${contractRiskImpact ? contractRiskImpact.toFixed(6) : '---'}</span>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-[9px] text-gray-400 font-bold">Margem mín:</span>
                                            <span className="text-[9px] font-mono font-bold text-white">${contractMinMargin ? contractMinMargin.toFixed(6) : '---'}</span>
                                        </div>
                                    </div>
                                </div>
                                <div className="p-3 bg-black/60 rounded-xl border border-white/5">
                                    <span className="text-[8px] font-black text-gray-500 uppercase tracking-widest block mb-1">Fórmula operacional</span>
                                    <p className="text-[10px] font-mono text-gray-300 leading-relaxed">
                                        ROI = variação do preço x alavancagem. Com {contractMaxLev || 50}x, 30% ROI exige cerca de {(30 / ((contractMaxLev || 50) * 100) * 100).toFixed(3)}% de movimento real no preço; 150% ROI exige cerca de {(150 / ((contractMaxLev || 50) * 100) * 100).toFixed(3)}%.
                                    </p>
                                    {contractQualityReasons.length > 0 && (
                                        <p className="text-[9px] font-mono text-gray-500 leading-relaxed mt-2">
                                            Capitão: {contractQualityReasons.join(' | ')}
                                        </p>
                                    )}
                                </div>
                            </div>
                        )}

                        <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5 text-center">
                            <span className="text-[8px] font-bold text-gray-600 uppercase tracking-[0.2em]">{selectedHistoryLog.is_signal ? `Sinal Capturado às: ${selectedHistoryLog.timestamp ? new Date(selectedHistoryLog.timestamp).toLocaleString('pt-BR') : "Agora"}` : `Encerramento da Missão: ${selectedHistoryLog.close_time ? new Date(selectedHistoryLog.close_time).toLocaleString('pt-BR') : "LOG Sincronizado"}`}</span>
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    window.TriumphModal = TriumphModal;
})();
