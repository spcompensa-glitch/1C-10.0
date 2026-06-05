(function() {
    // =========================================================================
    // [V110.115] InteractiveBacktestChart — Motor Eagle Vision v110.41 PRO
    // =========================================================================
    const InteractiveBacktestChart = ({ klines, trades, ghostInsights, qualitySeal, dnaTags, equityCurve, srZones, height = 450 }) => {
        const chartContainerRef = React.useRef(null);
        const equityContainerRef = React.useRef(null);
        const chartRef = React.useRef(null);
        const equityChartRef = React.useRef(null);
        const [eagleMode, setEagleMode] = React.useState(true);

        React.useEffect(() => {
            if (!klines || klines.length === 0) return;

            // === MAIN CHART ===
            const chart = LightweightCharts.createChart(chartContainerRef.current, {
                height: height,
                layout: { background: { color: 'transparent' }, textColor: '#94a3b8', fontFamily: 'JetBrains Mono' },
                grid: { vertLines: { color: 'rgba(255,255,255,0.03)' }, horzLines: { color: 'rgba(255,255,255,0.03)' } },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                priceScale: { borderColor: 'rgba(255,255,255,0.1)' },
                timeScale: { borderColor: 'rgba(255,255,255,0.1)', timeVisible: true },
            });
            chartRef.current = chart;

            const candlestickSeries = chart.addCandlestickSeries({
                upColor: '#22c55e', downColor: '#ef4444', borderVisible: false,
                wickUpColor: '#22c55e', wickDownColor: '#ef4444'
            });
            candlestickSeries.setData(klines);

            // 2. Volume Series (Eagle Vision)
            if (eagleMode && window.calculateVolumes) {
                const volumeSeries = chart.addHistogramSeries({ color: 'rgba(38, 166, 154, 0.5)', priceFormat: { type: 'volume' }, priceScaleId: '' });
                volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
                volumeSeries.setData(window.calculateVolumes(klines));
            }

            // 3. Trade Markers
            if (trades && trades.length > 0) {
                const markers = [];
                trades.forEach(t => {
                    markers.push({
                        time: intTime(t.entry_time),
                        position: t.side === 'Long' ? 'belowBar' : 'aboveBar',
                        color: t.side === 'Long' ? '#22c55e' : '#f59e0b',
                        shape: t.side === 'Long' ? 'arrowUp' : 'arrowDown',
                        text: `${t.side} Entry`
                    });
                    if (t.exit_time) {
                        markers.push({
                            time: intTime(t.exit_time),
                            position: 'inBar',
                            color: (t.pnl || 0) >= 0 ? '#22c55e' : '#f43f5e',
                            shape: 'circle',
                            text: `EXIT ($${(t.pnl || 0).toFixed(1)})`
                        });
                    }
                });
                candlestickSeries.setMarkers(markers.sort((a,b) => a.time - b.time));
            }

            // === EQUITY CHART ===
            if (equityCurve && equityCurve.length > 0) {
                const equityChart = LightweightCharts.createChart(equityContainerRef.current, {
                    height: 120,
                    layout: { background: { color: 'transparent' }, textColor: '#64748b', fontSize: 10 },
                    grid: { vertLines: { visible: false }, horzLines: { color: 'rgba(255,255,255,0.02)' } },
                    priceScale: { position: 'right', borderColor: 'transparent' },
                    timeScale: { visible: false },
                });
                equityChartRef.current = equityChart;
                const lineSeries = equityChart.addAreaSeries({
                    lineColor: '#ffffff', topColor: 'rgba(255, 255, 255, 0.1)', bottomColor: 'transparent',
                    lineWidth: 2,
                });
                lineSeries.setData(equityCurve);
                equityChart.timeScale().fitContent();
            }

            chart.timeScale().fitContent();

            const handleResize = () => {
                chart.applyOptions({ width: chartContainerRef.current.clientWidth });
                if (equityChartRef.current) equityChartRef.current.applyOptions({ width: equityContainerRef.current.clientWidth });
            };
            window.addEventListener('resize', handleResize);

            return () => {
                window.removeEventListener('resize', handleResize);
                chart.remove();
                if (equityChartRef.current) equityChartRef.current.remove();
            };
        }, [klines, eagleMode]);

        const intTime = (ts) => (typeof ts === 'number' && ts < 1e11) ? ts : Math.floor(ts / 1000);

        return (
            <div className="flex flex-col gap-4">
                <div className="relative group">
                    <div ref={chartContainerRef} className="w-full rounded-2xl overflow-hidden border border-white/5 bg-black/40"></div>
                    <button 
                        onClick={() => setEagleMode(!eagleMode)}
                        className="absolute top-4 right-4 z-10 p-2 rounded-lg bg-black/60 border border-white/10 text-[10px] font-black uppercase tracking-widest text-white hover:bg-primary hover:text-black transition-all"
                    >
                        {eagleMode ? 'Eagle: Analytic' : 'Eagle: Simple'}
                    </button>
                </div>
                {equityCurve && (
                    <div className="flex flex-col gap-2">
                        <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest ml-1">Evolução do Capital (Backtest Estocástico)</span>
                        <div ref={equityContainerRef} className="w-full rounded-2xl overflow-hidden border border-white/5 bg-black/40"></div>
                    </div>
                )}
            </div>
        );
    };

    // =========================================================================
    // DeepAnalysisModal — Análise Forense V110.115
    // =========================================================================
    const DeepAnalysisModal = ({ symbol, onClose }) => {
        const [data, setData] = React.useState(null);
        const [loading, setLoading] = React.useState(true);

        React.useEffect(() => {
            if (!symbol) return;
            const fetchAnalysis = async () => {
                setLoading(true);
                try {
                    const res = await fetch(`${window.API_BASE}/api/backtest/run`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ symbol, timeframes: ["15m"] })
                    });
                    const json = await res.json();
                    if (json.status === 'success') setData(json.results);
                } catch (e) { console.error("Analysis Error:", e); }
                finally { setLoading(false); }
            };
            fetchAnalysis();
        }, [symbol]);

        if (!symbol) return null;

        return (
            <div className="fixed inset-0 z-[10500] flex items-center justify-center p-4 lg:p-8 animate-in fade-in duration-300">
                <div className="absolute inset-0 bg-black/80 backdrop-blur-xl" onClick={onClose}></div>
                
                <div className="bg-[#0a0c14] border border-white/10 w-full max-w-6xl h-full lg:max-h-[90vh] rounded-[2rem] overflow-hidden flex flex-col relative z-10 shadow-[0_0_100px_rgba(0,0,0,0.5)]">
                    {/* Header */}
                    <div className="p-6 border-b border-white/5 flex items-center justify-between bg-black/20">
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center">
                                <span className="material-icons-round text-white text-2xl">analytics</span>
                            </div>
                            <div>
                                <div className="flex items-center gap-3">
                                    <h2 className="text-xl font-black text-white uppercase tracking-tight">{symbol}</h2>
                                    <span className="text-[10px] bg-white/5 border border-white/10 px-2 py-0.5 rounded text-gray-400 font-bold uppercase tracking-widest">Deep Analysis PRO</span>
                                </div>
                                <p className="text-[10px] text-gray-500 font-bold uppercase tracking-[0.2em] mt-0.5">Simulação de Performance Sentinel · V110.115</p>
                            </div>
                        </div>
                        <button onClick={onClose} className="w-10 h-10 rounded-full hover:bg-white/5 flex items-center justify-center text-gray-400 hover:text-white transition-all">
                            <span className="material-icons-round">close</span>
                        </button>
                    </div>

                    {/* Content */}
                    <div className="flex-1 overflow-y-auto p-6 lg:p-8 custom-scrollbar">
                        {loading ? (
                            <div className="h-full flex flex-col items-center justify-center gap-4">
                                <div className="w-12 h-12 border-2 border-primary/20 border-t-primary rounded-full animate-spin"></div>
                                <span className="text-[10px] font-black text-gray-500 uppercase tracking-[0.3em] animate-pulse">Sincronizando Dados Históricos...</span>
                            </div>
                        ) : data ? (
                            <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
                                {/* Stats Column */}
                                <div className="lg:col-span-3 flex flex-col gap-6">
                                    <div className="grid grid-cols-1 gap-3">
                                        {[
                                            { label: 'Expectativa PnL', value: `${data.total_pnl_pct}`, color: data.total_pnl >= 0 ? 'text-white' : 'text-red-400', icon: 'payments' },
                                            { label: 'Win Rate', value: `${data.win_rate}%`, color: data.win_rate >= 60 ? 'text-white' : 'text-amber-400', icon: 'stars' },
                                            { label: 'Profit Factor', value: data.profit_factor, color: 'text-gray-400', icon: 'trending_up' },
                                            { label: 'Max Drawdown', value: data.max_drawdown, color: 'text-red-400', icon: 'warning' },
                                        ].map((s, i) => (
                                            <div key={i} className="bg-white/[0.02] border border-white/5 rounded-2xl p-4">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <span className="material-icons-round text-[14px] text-gray-500">{s.icon}</span>
                                                    <span className="text-[8px] font-black text-gray-500 uppercase tracking-widest">{s.label}</span>
                                                </div>
                                                <div className={`text-lg font-black font-mono ${s.color}`}>{s.value}</div>
                                            </div>
                                        ))}
                                    </div>

                                    <div className="bg-primary/5 border border-primary/10 rounded-2xl p-4 flex flex-col gap-4">
                                        <h3 className="text-[10px] font-black text-white uppercase tracking-[0.2em] flex items-center gap-2">
                                            <span className="material-icons-round text-sm">bolt</span>
                                            Dna Operacional
                                        </h3>
                                        <div className="flex flex-col gap-2">
                                            <div className="flex justify-between items-center text-[10px]">
                                                <span className="text-gray-500 font-bold uppercase">Correlação BTC</span>
                                                <span className="text-white font-mono font-bold">{(data.tactical_intel?.correlation_avg * 100).toFixed(1)}%</span>
                                            </div>
                                            <div className="w-full bg-black/40 h-1.5 rounded-full overflow-hidden border border-white/5">
                                                <div className="h-full bg-primary" style={{ width: `${data.tactical_intel?.correlation_avg * 100}%` }}></div>
                                            </div>
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                            {data.klines.filter(k => k.adx > 40).length > 0 && (
                                                <span className="text-[8px] font-black px-2 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20 uppercase">Trend Explosion</span>
                                            )}
                                            <span className="text-[8px] font-black px-2 py-0.5 rounded bg-green-500/10 text-white border border-green-500/20 uppercase">Volatility Guard</span>
                                        </div>
                                    </div>
                                </div>

                                {/* Charts Column */}
                                <div className="lg:col-span-9 flex flex-col gap-6">
                                    <InteractiveBacktestChart 
                                        klines={data.klines} 
                                        trades={data.trades} 
                                        equityCurve={data.equity_curve} 
                                        height={450} 
                                    />
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex items-center justify-center text-red-400 font-bold uppercase tracking-widest">Falha ao carregar análise.</div>
                        )}
                    </div>
                </div>
            </div>
        );
    };

    window.InteractiveBacktestChart = InteractiveBacktestChart;
    window.DeepAnalysisModal = DeepAnalysisModal;
})();
