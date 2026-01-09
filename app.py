import os, re, asyncio
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Query
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from hl_consensus import ConsensusEngine, send_telegram_html, save_config, load_config, HIST_CSV
from datetime import datetime


app = FastAPI(title="Hyperliquid Consensus Radar", version="8.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

clients = set()

def _normalize_cfg(raw):
    if isinstance(raw, dict) and "config" in raw and isinstance(raw["config"], dict):
        return raw
    if isinstance(raw, dict):
        return {"config": raw}
    return {"config": {}}

_cfg_raw = load_config()
cfg = _normalize_cfg(_cfg_raw)
engine = ConsensusEngine(cfg)

_WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

def _to_int(x, default=0):
    try: 
        return int(float(x))
    except Exception: 
        return default

def _to_float(x, default=0.0):
    try: 
        return float(x)
    except Exception: 
        return default

def _to_bool(x):
    if isinstance(x, str):
        return x.strip().lower() not in ("0","false","no","off","")
    return bool(x)

@app.on_event("startup")
async def startup_event():
    async def on_signal(signal: dict):
        payload = {
            "coin": signal.get("coin"),
            "side": str(signal.get("side","")).lower(),
            "count": signal.get("count"),
            "threshold": signal.get("threshold"),
            "ts": signal.get("ts"),
            "use_positions": bool(signal.get("use_positions")),
            "wallets": [r.get("addr") for r in (signal.get("wallet_rows") or [])],
            "wallet_rows": signal.get("wallet_rows") or [],
        }
        dead = set()
        for ws in list(clients):
            try:
                await ws.send_json({"type":"signal","data": payload})
            except Exception as e:
                print(f"[WS] Error sending to client: {e}")
                dead.add(ws)
        for z in dead:
            clients.discard(z)

    engine.set_ws_callback(on_signal)
    
    # Iniciar loop de monitoreo
    asyncio.create_task(engine.loop())
    
    # Iniciar loop de Telegram (respuestas rápidas)
    asyncio.create_task(engine.telegram_listener())
    
    print("[APP] All tasks started")

@app.get("/")
async def root():
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    # Fallback: servir HTML inline si no existe el archivo
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hyperliquid Consensus Radar v8</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        .header h1 { color: #667eea; margin-bottom: 10px; }
        .status {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: bold;
        }
        .status.connected { background: #10b981; color: white; }
        .status.disconnected { background: #ef4444; color: white; }
        .config-panel, .signals-panel {
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        .form-group { margin-bottom: 20px; }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #555;
        }
        .form-group input, .form-group textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 14px;
        }
        .form-group input:focus, .form-group textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        .form-group textarea {
            min-height: 100px;
            font-family: monospace;
        }
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn-primary { background: #667eea; color: white; }
        .btn-primary:hover {
            background: #5568d3;
            transform: translateY(-2px);
        }
        .btn-secondary { background: #6b7280; color: white; }
        .btn-danger { background: #ef4444; color: white; }
        .button-group {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }
        .signal-card {
            background: #f9fafb;
            border-left: 4px solid #667eea;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 8px;
        }
        .signal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .signal-title {
            font-size: 20px;
            font-weight: bold;
            color: #667eea;
        }
        .signal-time { color: #6b7280; font-size: 14px; }
        .wallet-item {
            background: white;
            padding: 12px;
            margin-bottom: 8px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 13px;
        }
        .wallet-addr {
            color: #667eea;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #6b7280;
        }
        @media (max-width: 768px) {
            .form-row { grid-template-columns: 1fr; }
            .button-group { flex-direction: column; }
            .btn { width: 100%; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ Hyperliquid Consensus Radar</h1>
            <p>Sistema de monitoreo de consenso en tiempo real</p>
            <div style="margin-top: 15px;">
                <span class="status disconnected" id="wsStatus">⚫ Desconectado</span>
            </div>
        </div>

        <div class="config-panel">
            <h2>⚙️ Configuración</h2>
            <div class="form-group">
                <label>Wallets (una por línea o separadas por comas)</label>
                <textarea id="wallets" placeholder="0x..."></textarea>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Símbolos (ej: BTC,ETH,SOL)</label>
                    <input type="text" id="symbols" placeholder="BTC,ETH">
                </div>
                <div class="form-group">
                    <label>Consenso mínimo</label>
                    <input type="number" id="consensus_count" min="1" value="1">
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Polling (segundos)</label>
                    <input type="number" id="poll_seconds" min="5" value="12">
                </div>
                <div class="form-group">
                    <label>Usar posiciones</label>
                    <input type="checkbox" id="use_positions" checked style="width: auto;">
                </div>
            </div>
            <div class="button-group">
                <button class="btn btn-primary" onclick="saveConfig()">💾 Guardar</button>
                <button class="btn btn-secondary" onclick="testTelegram()">📱 Test Telegram</button>
                <button class="btn btn-danger" onclick="clearHistory()">🗑️ Limpiar</button>
            </div>
        </div>

        <div class="signals-panel">
            <h2>📊 Señales en Tiempo Real</h2>
            <div id="signalsContainer">
                <div class="empty-state">
                    <div style="font-size: 64px;">📡</div>
                    <h3>Esperando señales...</h3>
                    <p>Las señales aparecerán aquí en tiempo real</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws = null;
        const signals = [];
        const signalCache = new Map(); // Cache para evitar duplicados

        function connectWS() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.host;
            ws = new WebSocket(`${protocol}//${host}/ws`);
            
            ws.onopen = () => {
                console.log('WebSocket connected');
                document.getElementById('wsStatus').textContent = '🟢 Conectado';
                document.getElementById('wsStatus').className = 'status connected';
            };
            
            ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                console.log('WS message:', msg);
                if (msg.type === 'signal') addSignal(msg.data);
            };
            
            ws.onclose = () => {
                console.log('WebSocket disconnected');
                document.getElementById('wsStatus').textContent = '⚫ Desconectado';
                document.getElementById('wsStatus').className = 'status disconnected';
                setTimeout(connectWS, 3000);
            };
            
            ws.onerror = (error) => console.error('WebSocket error:', error);
        }

        async function loadConfig() {
            try {
                const resp = await fetch('/config');
                const config = await resp.json();
                document.getElementById('wallets').value = (config.wallets || []).join('\\n');
                document.getElementById('symbols').value = (config.symbols || []).join(',');
                document.getElementById('consensus_count').value = config.consensus_count || 1;
                document.getElementById('poll_seconds').value = config.poll_seconds || 12;
                document.getElementById('use_positions').checked = config.use_positions !== false;
            } catch (e) {
                console.error('Error loading config:', e);
            }
        }

        async function saveConfig() {
            const wallets = document.getElementById('wallets').value
                .split(/[\\n,]/)
                .map(w => w.trim())
                .filter(w => w);
            
            const symbols = document.getElementById('symbols').value
                .split(',')
                .map(s => s.trim())
                .filter(s => s);
            
            const config = {
                wallets,
                symbols,
                consensus_count: parseInt(document.getElementById('consensus_count').value) || 1,
                poll_seconds: parseInt(document.getElementById('poll_seconds').value) || 12,
                use_positions: document.getElementById('use_positions').checked
            };
            
            try {
                const resp = await fetch('/config', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                alert(resp.ok ? '✅ Configuración guardada' : '❌ Error al guardar');
            } catch (e) {
                console.error('Error saving config:', e);
                alert('❌ Error al guardar');
            }
        }

        async function testTelegram() {
            try {
                const resp = await fetch('/test_telegram');
                const data = await resp.json();
                alert(data.sent ? '✅ Telegram enviado' : '❌ Error en Telegram');
            } catch (e) {
                alert('❌ Error al enviar');
            }
        }

        async function clearHistory() {
            if (!confirm('¿Seguro?')) return;
            try {
                await fetch('/history/clear', { method: 'POST' });
                alert('✅ Historial limpiado');
            } catch (e) {
                alert('❌ Error al limpiar');
            }
        }

        function addSignal(signal) {
            // Crear un ID único para la señal basado en coin, wallets y timestamp (redondeado a minuto)
            const timestamp = new Date(signal.ts).setSeconds(0, 0); // Redondear a minuto
            const walletIds = signal.wallets.sort().join(',');
            const signalId = `${signal.coin}-${signal.side}-${walletIds}-${timestamp}`;
            
            // Si ya existe esta señal, actualizar en lugar de añadir
            if (signalCache.has(signalId)) {
                console.log('Signal already exists, updating:', signalId);
                const existingIndex = signals.findIndex(s => {
                    const existingTs = new Date(s.ts).setSeconds(0, 0);
                    const existingWallets = s.wallets.sort().join(',');
                    return `${s.coin}-${s.side}-${existingWallets}-${existingTs}` === signalId;
                });
                
                if (existingIndex !== -1) {
                    signals[existingIndex] = signal; // Actualizar datos
                }
            } else {
                // Nueva señal
                console.log('New signal detected:', signalId);
                signalCache.set(signalId, true);
                signals.unshift(signal);
                
                // Limpiar cache antiguo (mantener últimas 100)
                if (signalCache.size > 100) {
                    const firstKey = signalCache.keys().next().value;
                    signalCache.delete(firstKey);
                }
            }
            
            if (signals.length > 50) signals.pop();
            renderSignals();
        }

        function renderSignals() {
            const container = document.getElementById('signalsContainer');
            if (signals.length === 0) {
                container.innerHTML = '<div class="empty-state"><div style="font-size: 64px;">📡</div><h3>Esperando señales...</h3></div>';
                return;
            }
            
            container.innerHTML = signals.map(signal => `
                <div class="signal-card">
                    <div class="signal-header">
                        <div class="signal-title">${signal.coin} ${signal.side.toUpperCase()}</div>
                        <div class="signal-time">${signal.ts}</div>
                    </div>
                    <p><strong>Consenso:</strong> ${signal.count}/${signal.threshold} | <strong>Wallets:</strong> ${signal.wallets.length}</p>
                    <div style="margin-top: 15px;">
                        ${(signal.wallet_rows || []).map(w => `
                            <div class="wallet-item">
                                <div class="wallet-addr">${w.addr.substring(0, 10)}...${w.addr.substring(w.addr.length - 8)}</div>
                                <div style="color: #6b7280; font-size: 12px;">
                                    ${w.szi ? `Size: ${w.szi.toFixed(4)}` : 'No position'}
                                    ${w.entry ? ` | Entry: ${w.entry.toFixed(2)}` : ''}
                                    ${w.mark ? ` | Mark: ${w.mark.toFixed(2)}` : ''}
                                    ${w.upnl ? ` | PnL: ${w.upnl.toFixed(2)}` : ''}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('');
        }

        connectWS();
        loadConfig();
    </script>
</body>
</html>
""")

@app.get("/health")
async def health(): 
    return {"ok": True}

@app.get("/state")
async def state(): 
    return JSONResponse({"status": "running", "clients": len(clients)})

@app.get("/config")
async def get_config():
    return JSONResponse(cfg.get("config", {}))

@app.patch("/config")
async def patch_config(patch: dict = Body(...)):
    current = cfg.get("config", {})
    new_cfg = current.copy()
    if not isinstance(patch, dict):
        patch = {}

    for k, v in patch.items():
        if k == "wallets":
            if isinstance(v, str):
                v = [s.strip() for s in v.split(",") if s.strip()]
            v = v if isinstance(v, list) else []
            v = [w for w in v if _WALLET_RE.match(w)]
            new_cfg["wallets"] = v
        elif k == "symbols":
            if isinstance(v, str):
                v = [s.strip() for s in v.split(",") if s.strip()]
            v = v if isinstance(v, list) else []
            new_cfg["symbols"] = [s.upper() for s in v]
        elif k in ("window_minutes","poll_seconds","cooldown_minutes","consensus_count"):
            new_cfg[k] = _to_int(v, current.get(k, 0))
        elif k == "min_nocional_usd":
            new_cfg[k] = _to_float(v, current.get(k, 0.0))
        elif k == "use_positions":
            new_cfg[k] = _to_bool(v)

    cfg["config"] = new_cfg
    save_config(cfg)
    engine.cfg = cfg
    return JSONResponse({"ok": True, "config": new_cfg})

@app.get("/test_telegram")
async def test_telegram(text: str = Query("Test desde /test_telegram")):
    from hl_consensus import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {
            "error": "Telegram not configured",
            "bot_token_set": bool(TELEGRAM_BOT_TOKEN),
            "chat_id_set": bool(TELEGRAM_CHAT_ID)
        }
    
    await send_telegram_html(f"<b>Prueba</b>: {text}")
    return {
        "sent": True, 
        "text": text,
        "chat_id": TELEGRAM_CHAT_ID
    }

@app.post("/force_telegram")
async def force_telegram():
    html = "<b>Force</b>: no hay señales aún, mensaje de prueba."
    await send_telegram_html(html)
    return {"forced": True, "message": html}

@app.get("/history.csv")
async def history_csv():
    if not os.path.exists(HIST_CSV):
        return PlainTextResponse("No history yet", status_code=404)
    return FileResponse(HIST_CSV, media_type="text/csv", filename="consensus_history.csv")

def _clear_history_files():
    try:
        if os.path.exists(HIST_CSV): 
            os.remove(HIST_CSV)
    except Exception: 
        pass
    hist_jsonl = os.path.join(os.path.dirname(HIST_CSV), "history.jsonl")
    try:
        if os.path.exists(hist_jsonl): 
            os.remove(hist_jsonl)
    except Exception: 
        pass

@app.post("/history/clear")
async def history_clear_endpoint():
    _clear_history_files()
    return {"ok": True}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    print(f"[WS] Client connected. Total clients: {len(clients)}")
    await ws.send_json({"type": "hello", "data": {"status": "connected"}})
    try:
        while True:
            data = await ws.receive_text()
            # Echo back or handle messages if needed
    except WebSocketDisconnect:
        clients.discard(ws)
        print(f"[WS] Client disconnected. Total clients: {len(clients)}")
    except Exception as e:
        print(f"[WS] Error: {e}")
        clients.discard(ws)

@app.post("/refresh")
async def refresh_snapshot():
    return await engine.compute_last_snapshot()


@app.get("/snapshot")
async def snapshot():
    snapshots = []

    config = engine.cfg.get("config", {})
    consensus = int(config.get("consensus_count", 1))

    for coin, rows in engine.last_positions.items():
        long_wallets = [r for r in rows if r.get("side") == "long"]
        short_wallets = [r for r in rows if r.get("side") == "short"]

        if len(long_wallets) >= consensus:
            snapshots.append({
                "coin": coin,
                "side": "long",
                "count": len(long_wallets),
                "threshold": consensus,
                "ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "use_positions": True,
                "wallet_rows": long_wallets,
            })

        if len(short_wallets) >= consensus:
            snapshots.append({
                "coin": coin,
                "side": "short",
                "count": len(short_wallets),
                "threshold": consensus,
                "ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "use_positions": True,
                "wallet_rows": short_wallets,
            })

    return snapshots
