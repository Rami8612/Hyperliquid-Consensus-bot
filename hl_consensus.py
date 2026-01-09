#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, time, asyncio, re
from datetime import datetime, timedelta
from pathlib import Path
import requests
import aiohttp
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = DATA_DIR / "config.json"
HIST_JSONL = DATA_DIR / "history.jsonl"
HIST_CSV = DATA_DIR / "history.csv"

INFO_URL = "https://api.hyperliquid.xyz/info"

# Bot de Telegram para recibir comandos
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
_last_update_id = 0

# Validación de wallet
_WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

def time_ago(timestamp_str: str) -> str:
    """Calcula hace cuánto tiempo desde un timestamp"""
    try:
        ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        now = datetime.utcnow()
        diff = now - ts
        
        if diff.days > 0:
            return f"hace {diff.days}d"
        elif diff.seconds >= 3600:
            hours = diff.seconds // 3600
            return f"hace {hours}h"
        elif diff.seconds >= 60:
            minutes = diff.seconds // 60
            return f"hace {minutes}m"
        else:
            return f"hace {diff.seconds}s"
    except Exception:
        return "desconocido"

def fmt_usd(x: float) -> str:
    try:
        return f"${x:,.0f}" if abs(x) >= 1000 else f"${x:.2f}"
    except Exception:
        return "$0"

def fmt_signed_usd(x: float) -> str:
    try:
        sign = "+" if x >= 0 else ""
        return f"{sign}{fmt_usd(x)}"
    except Exception:
        return "$0"

def now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CFG] Error loading config: {e}")
    
    return {
        "config": {
            "wallets": [],
            "symbols": ["BTC","ETH"],
            "window_minutes": 5,
            "min_nocional_usd": 10000.0,
            "poll_seconds": 12,
            "cooldown_minutes": 10,
            "consensus_count": 1,
            "use_positions": True
        },
        "last_poll_at": None,
        "last_signals": []
    }

def save_config(obj: dict):
    try:
        DATA_DIR.mkdir(exist_ok=True, parents=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CFG] Error saving config: {e}")

def post_info(payload: dict):
    try:
        r = requests.post(INFO_URL, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[API] Error calling Hyperliquid API: {e}")
        return {}

async def send_telegram_html(msg: str):
    bot = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    
    if not bot or not chat:
        print("[TG] Telegram credentials not configured")
        return
    
    url = f"https://api.telegram.org/bot{bot}/sendMessage"
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(url, json={"chat_id": chat, "text": msg, "parse_mode": "HTML"}) as resp:
                if resp.status == 200:
                    print("[TG] Message sent successfully")
                else:
                    print(f"[TG] Error sending message: {resp.status}")
        except Exception as e:
            print(f"[TG] Exception sending message: {e}")

async def get_telegram_updates():
    """Obtener actualizaciones de Telegram (comandos del usuario)"""
    global _last_update_id
    
    if not TELEGRAM_BOT_TOKEN:
        return []
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"offset": _last_update_id + 1, "timeout": 30}  # Long polling de 30s
    
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=35)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    updates = data.get("result", [])
                    if updates:
                        _last_update_id = updates[-1]["update_id"]
                        print(f"[TG] Got {len(updates)} updates, last_update_id: {_last_update_id}")
                    return updates
                else:
                    print(f"[TG] getUpdates failed with status {resp.status}")
                    text = await resp.text()
                    print(f"[TG] Response: {text}")
    except asyncio.TimeoutError:
        # Timeout normal en long polling, no es error
        return []
    except Exception as e:
        print(f"[TG] Error getting updates: {e}")
        import traceback
        traceback.print_exc()
    
    return []

async def process_telegram_command(text: str, engine):
    """Procesar comandos de Telegram"""
    text_lower = text.strip().lower()
    text_original = text.strip()
    
    if text_lower == "/start" or text_lower == "/help":
        help_msg = """
╔═══════════════════════════
<b>🤖 COMANDOS DISPONIBLES</b>
╚═══════════════════════════

<b>📊 CONSULTAS:</b>
/reload - Actualización inmediata
/last - Ver últimas señales
/status - Estado del sistema
/config - Ver configuración
/stats - Estadísticas de posiciones

<b>⚙️ CONFIGURACIÓN:</b>
/add_wallet 0x... - Añadir wallet
/remove_wallet 0x... - Quitar wallet
/add_coin BTC - Añadir símbolo
/remove_coin BTC - Quitar símbolo
/set_consensus 3 - Cambiar consenso
/set_interval 60 - Cambiar intervalo

<b>📚 AYUDA:</b>
/commands - Ver ejemplos detallados
/help - Este menú

═══════════════════════════
"""
        await send_telegram_html(help_msg)
        return
    
    if text_lower == "/commands" or text_lower == "/ejemplos" or text_lower == "/examples":
        examples_msg = """
╔═══════════════════════════
<b>📚 EJEMPLOS DE COMANDOS</b>
╚═══════════════════════════

<b>🔍 CONSULTAR INFORMACIÓN:</b>

<code>/reload</code>
Actualiza posiciones ahora mismo

<code>/last</code>
Muestra posiciones actuales con consenso

<code>/status</code>
Estado del sistema y configuración

<code>/config</code>
Configuración detallada completa

<code>/stats</code>
Estadísticas de todas las posiciones

─────────────────────────────

<b>👛 GESTIONAR WALLETS:</b>

<code>/add_wallet 0xc2a30212a8DdAc9e123944d6e29FADdCe994E5f2</code>
Añade una wallet para seguir

<code>/remove_wallet 0xc2a3</code>
Elimina wallet (dirección completa o parcial)

─────────────────────────────

<b>🪙 GESTIONAR SÍMBOLOS:</b>

<code>/add_coin SOL</code>
Añade SOL a los símbolos a seguir

<code>/add_coin MATIC</code>
Añade MATIC

<code>/remove_coin BTC</code>
Elimina BTC de los símbolos

─────────────────────────────

<b>⚙️ AJUSTAR PARÁMETROS:</b>

<code>/set_consensus 3</code>
Requiere 3 wallets en misma dirección

<code>/set_consensus 5</code>
Requiere 5 wallets en misma dirección

<code>/set_interval 60</code>
Chequea cada 60 segundos (1 min)

<code>/set_interval 300</code>
Chequea cada 300 segundos (5 min)

─────────────────────────────

<b>💡 FLUJO DE TRABAJO TÍPICO:</b>

1️⃣ <code>/config</code> - Ver estado actual
2️⃣ <code>/add_wallet 0x...</code> - Añadir wallets
3️⃣ <code>/add_coin AVAX</code> - Añadir tokens
4️⃣ <code>/set_consensus 3</code> - Ajustar consenso
5️⃣ <code>/reload</code> - Probar
6️⃣ <code>/last</code> - Ver resultados

─────────────────────────────

<b>⚡ TIPS RÁPIDOS:</b>

• Puedes usar direcciones parciales para eliminar:
  <code>/remove_wallet 0xc2a3</code>

• Los símbolos se añaden en mayúsculas:
  <code>/add_coin sol</code> → SOL

• Intervalo válido: 10-600 segundos

• Todos los cambios son instantáneos

═══════════════════════════
"""
        await send_telegram_html(examples_msg)
        return
    
    # Comando /add_wallet
    if text_lower.startswith("/add_wallet "):
        wallet = text_original.split(maxsplit=1)[1].strip() if len(text_original.split()) > 1 else ""
        
        if not wallet:
            await send_telegram_html("❌ <b>Error:</b> Debes especificar una wallet\n\n<b>Uso:</b> /add_wallet 0x...")
            return
        
        # Validar formato
        if not _WALLET_RE.match(wallet):
            await send_telegram_html(f"❌ <b>Wallet inválida:</b> {wallet}\n\n<i>Debe ser formato: 0x + 40 caracteres hexadecimales</i>")
            return
        
        config = engine.cfg.get("config", {})
        wallets = config.get("wallets", [])
        
        if wallet in wallets:
            await send_telegram_html(f"⚠️ <b>Wallet ya existe:</b>\n<code>{wallet}</code>")
            return
        
        wallets.append(wallet)
        config["wallets"] = wallets
        save_config(engine.cfg)
        
        await send_telegram_html(f"✅ <b>Wallet añadida:</b>\n<code>{wallet}</code>\n\n📊 Total wallets: {len(wallets)}")
        print(f"[CFG] Wallet added via Telegram: {wallet}")
        return
    
    # Comando /remove_wallet
    if text_lower.startswith("/remove_wallet "):
        wallet = text_original.split(maxsplit=1)[1].strip() if len(text_original.split()) > 1 else ""
        
        if not wallet:
            await send_telegram_html("❌ <b>Error:</b> Debes especificar una wallet\n\n<b>Uso:</b> /remove_wallet 0x...")
            return
        
        config = engine.cfg.get("config", {})
        wallets = config.get("wallets", [])
        
        # Buscar wallet (puede ser dirección completa o parcial)
        wallet_to_remove = None
        for w in wallets:
            if w.lower() == wallet.lower() or w.lower().startswith(wallet.lower()):
                wallet_to_remove = w
                break
        
        if not wallet_to_remove:
            await send_telegram_html(f"❌ <b>Wallet no encontrada:</b>\n<code>{wallet}</code>")
            return
        
        wallets.remove(wallet_to_remove)
        config["wallets"] = wallets
        save_config(engine.cfg)
        
        await send_telegram_html(f"✅ <b>Wallet eliminada:</b>\n<code>{wallet_to_remove}</code>\n\n📊 Total wallets: {len(wallets)}")
        print(f"[CFG] Wallet removed via Telegram: {wallet_to_remove}")
        return
    
    # Comando /add_coin
    if text_lower.startswith("/add_coin "):
        coin = text_original.split(maxsplit=1)[1].strip().upper() if len(text_original.split()) > 1 else ""
        
        if not coin:
            await send_telegram_html("❌ <b>Error:</b> Debes especificar un símbolo\n\n<b>Uso:</b> /add_coin BTC")
            return
        
        config = engine.cfg.get("config", {})
        symbols = config.get("symbols", [])
        
        if coin in symbols:
            await send_telegram_html(f"⚠️ <b>Símbolo ya existe:</b> {coin}")
            return
        
        symbols.append(coin)
        config["symbols"] = symbols
        save_config(engine.cfg)
        
        await send_telegram_html(f"✅ <b>Símbolo añadido:</b> {coin}\n\n📊 Símbolos: {', '.join(symbols)}")
        print(f"[CFG] Symbol added via Telegram: {coin}")
        return
    
    # Comando /remove_coin
    if text_lower.startswith("/remove_coin "):
        coin = text_original.split(maxsplit=1)[1].strip().upper() if len(text_original.split()) > 1 else ""
        
        if not coin:
            await send_telegram_html("❌ <b>Error:</b> Debes especificar un símbolo\n\n<b>Uso:</b> /remove_coin BTC")
            return
        
        config = engine.cfg.get("config", {})
        symbols = config.get("symbols", [])
        
        if coin not in symbols:
            await send_telegram_html(f"❌ <b>Símbolo no encontrado:</b> {coin}")
            return
        
        symbols.remove(coin)
        config["symbols"] = symbols
        save_config(engine.cfg)
        
        await send_telegram_html(f"✅ <b>Símbolo eliminado:</b> {coin}\n\n📊 Símbolos: {', '.join(symbols)}")
        print(f"[CFG] Symbol removed via Telegram: {coin}")
        return
    
    # Comando /set_consensus
    if text_lower.startswith("/set_consensus "):
        try:
            value = int(text_original.split()[1])
            if value < 1:
                raise ValueError("Must be >= 1")
        except (IndexError, ValueError):
            await send_telegram_html("❌ <b>Error:</b> Valor inválido\n\n<b>Uso:</b> /set_consensus 3\n<i>(debe ser un número ≥ 1)</i>")
            return
        
        config = engine.cfg.get("config", {})
        old_value = config.get("consensus_count", 1)
        config["consensus_count"] = value
        save_config(engine.cfg)
        
        await send_telegram_html(f"✅ <b>Consenso actualizado:</b>\n{old_value} → {value}\n\n<i>Ahora se requieren {value} wallets en la misma dirección</i>")
        print(f"[CFG] Consensus changed via Telegram: {old_value} -> {value}")
        return
    
    # Comando /set_interval
    if text_lower.startswith("/set_interval "):
        try:
            value = int(text_original.split()[1])
            if value < 10 or value > 600:
                raise ValueError("Must be between 10-600")
        except (IndexError, ValueError):
            await send_telegram_html("❌ <b>Error:</b> Valor inválido\n\n<b>Uso:</b> /set_interval 60\n<i>(debe estar entre 10-600 segundos)</i>")
            return
        
        config = engine.cfg.get("config", {})
        old_value = config.get("poll_seconds", 12)
        config["poll_seconds"] = value
        save_config(engine.cfg)
        
        await send_telegram_html(f"✅ <b>Intervalo actualizado:</b>\n{old_value}s → {value}s\n\n<i>El bot chequeará posiciones cada {value} segundos</i>")
        print(f"[CFG] Interval changed via Telegram: {old_value} -> {value}")
        return
    
    # Resto de comandos existentes...
    if text_lower == "/reload" or text_lower == "/refresh" or text_lower == "/update":
        await send_telegram_html("🔄 <b>Actualizando posiciones...</b>\n<i>Esto tomará unos segundos</i>")
        
        # Forzar chequeo inmediato
        await engine.force_check()
        
        # Esperar un poco a que termine el chequeo
        await asyncio.sleep(2)
        
        # Enviar confirmación
        config = engine.cfg.get("config", {})
        wallets = config.get("wallets", [])
        await send_telegram_html(f"✅ <b>Actualización completada</b>\n📊 {len(wallets)} wallets consultadas")
        return
    
    if text == "/last" or text == "/latest":
        await send_telegram_html("🔄 <b>Consultando posiciones actuales...</b>")
        
        config = engine.cfg.get("config", {})
        wallets = config.get("wallets", [])
        coins = config.get("symbols", ["BTC"])
        consensus = int(config.get("consensus_count", 1))
        
        if not wallets:
            await send_telegram_html("❌ <b>No hay wallets configuradas</b>")
            return
        
        # Obtener precios actuales
        mids = get_all_mids()
        found_consensus = False
        
        for coin in coins:
            rows = []
            for addr in wallets:
                try:
                    st = post_info({"type": "clearinghouseState", "user": addr})
                except Exception:
                    st = {}
                
                det = extract_pos_details(st, coin)
                szi = det.get("szi")
                entry = det.get("entryPx")
                liq = det.get("liqPx")
                px = mids.get(coin.upper())
                
                # Determinar el lado de la posición
                side = None
                if szi is not None:
                    if szi > 0:
                        side = "long"
                    elif szi < 0:
                        side = "short"
                
                value = (abs(szi) * px) if (szi is not None and px is not None) else None
                upnl = ((px - entry) * szi) if (szi is not None and entry is not None and px is not None) else None
                
                # Buscar timestamp de apertura
                pos_key = f"{addr}:{coin}:{side}"
                opened_at = engine.position_timestamps.get(pos_key)
                
                rows.append({
                    "addr": addr, 
                    "szi": szi,
                    "side": side,
                    "entry": entry, 
                    "mark": px,
                    "liq": liq, 
                    "value": value, 
                    "upnl": upnl,
                    "opened_at": opened_at
                })
            
            # Contar por lado
            long_wallets = [r for r in rows if r.get("side") == "long"]
            short_wallets = [r for r in rows if r.get("side") == "short"]
            long_count = len(long_wallets)
            short_count = len(short_wallets)
            
            # Generar señales si hay consenso (SIN enviar alertas automáticas)
            if long_count >= consensus:
                found_consensus = True
                signal = {
                    "coin": coin,
                    "side": "long",
                    "count": long_count,
                    "threshold": consensus,
                    "ts": now_str(),
                    "use_positions": True,
                    "wallet_rows": long_wallets,
                }
                msg = build_tg_html(signal)
                await send_telegram_html(msg)
                await asyncio.sleep(0.5)
            
            if short_count >= consensus:
                found_consensus = True
                signal = {
                    "coin": coin,
                    "side": "short",
                    "count": short_count,
                    "threshold": consensus,
                    "ts": now_str(),
                    "use_positions": True,
                    "wallet_rows": short_wallets,
                }
                msg = build_tg_html(signal)
                await send_telegram_html(msg)
                await asyncio.sleep(0.5)
        
        if found_consensus:
            await send_telegram_html("✅ <b>Posiciones actualizadas</b>")
        else:
            await send_telegram_html(f"ℹ️ <b>No hay consenso alcanzado</b>\n\n📊 Se requieren {consensus} wallets en la misma dirección")
        
        print(f"[CMD] /last executed - Consensus found: {found_consensus}")
        return
    
    if text == "/status":
        config = engine.cfg.get("config", {})
        wallets = config.get("wallets", [])
        coins = config.get("symbols", ["BTC"])
        consensus = config.get("consensus_count", 1)
        
        status_msg = f"""
╔═══════════════════════════
<b>📊 ESTADO DEL SISTEMA</b>
╚═══════════════════════════

<b>Wallets monitoreadas:</b> {len(wallets)}
<b>Símbolos:</b> {', '.join(coins)}
<b>Consenso requerido:</b> {consensus}
<b>Polling:</b> {config.get('poll_seconds', 12)}s

<b>Estado:</b> ✅ Activo

<i>Usa /last para ver posiciones actuales</i>
═══════════════════════════
"""
        await send_telegram_html(status_msg)
        return
    
    if text == "/config":
        config = engine.cfg.get("config", {})
        wallets = config.get("wallets", [])
        
        config_msg = f"""
╔═══════════════════════════
<b>⚙️ CONFIGURACIÓN</b>
╚═══════════════════════════

<b>Wallets ({len(wallets)}):</b>
"""
        for idx, w in enumerate(wallets, 1):
            config_msg += f"{idx}. <code>{w[:8]}...{w[-6:]}</code>\n"
        
        config_msg += f"""
<b>Símbolos:</b> {', '.join(config.get('symbols', []))}
<b>Consenso:</b> {config.get('consensus_count', 1)}
<b>Intervalo:</b> {config.get('poll_seconds', 12)}s
<b>Usar posiciones:</b> {'✅' if config.get('use_positions', True) else '❌'}

═══════════════════════════
"""
        await send_telegram_html(config_msg)
        return
    
    if text == "/stats":
        await send_telegram_html("📊 <b>Generando estadísticas...</b>")
        await engine.send_stats_report()
        return
    
    # Comando no reconocido
    await send_telegram_html("❌ Comando no reconocido. Usa /help para ver comandos disponibles.")

def get_all_mids() -> dict:
    try:
        res = post_info({"type": "allMids"})
        if isinstance(res, dict):
            out = {}
            for k, v in res.items():
                try:
                    out[str(k).upper()] = float(v)
                except Exception:
                    pass
            return out
    except Exception as e:
        print(f"[API] Error getting mids: {e}")
    return {}

def extract_pos_details(state: dict, coin: str) -> dict:
    out = {"szi": None, "entryPx": None, "liqPx": None}
    try:
        for a in state.get("assetPositions", []):
            pos = a.get("position") or {}
            this_coin = str(pos.get("coin", "")).upper()
            
            if this_coin != str(coin).upper():
                continue
            
            try:
                if pos.get("szi") is not None: 
                    out["szi"] = float(pos["szi"])
            except Exception: 
                pass
            
            try:
                if pos.get("entryPx") is not None: 
                    out["entryPx"] = float(pos["entryPx"])
            except Exception: 
                pass
            
            lp = pos.get("liquidationPx") or pos.get("liqPx")
            try:
                if lp is not None: 
                    out["liqPx"] = float(lp)
            except Exception: 
                pass
            
            return out
    except Exception as e:
        print(f"[POS] Error extracting position details: {e}")
    
    return out

def build_tg_html(signal: dict) -> str:
    coin = signal.get("coin", "?")
    side = str(signal.get("side", "?")).upper()
    count = signal.get("count", 0)
    thr = signal.get("threshold", 0)
    ts = signal.get("ts", "")
    rows = signal.get("wallet_rows", [])
    
    # Emoji según el lado
    side_emoji = "🟢" if side == "LONG" else "🔴"
    
    # Header más destacado
    header = f"╔═══════════════════════════\n{side_emoji} <b>CONSENSO ALCANZADO</b> {side_emoji}\n╚═══════════════════════════"
    body = [
        f"📊 <b>{coin} {side}</b> → {count}/{thr} wallets",
        f"🕒 {ts}",
        "─────────────────────────────"
    ]
    
    # Calcular totales
    total_value = sum(r.get("value", 0) or 0 for r in rows)
    total_pnl = sum(r.get("upnl", 0) or 0 for r in rows)
    
    if total_value > 0 or total_pnl != 0:
        body.append(f"💰 <b>Total Posición:</b> {fmt_usd(total_value)}")
        if total_pnl != 0:
            pnl_emoji = "📈" if total_pnl >= 0 else "📉"
            body.append(f"{pnl_emoji} <b>PnL Total:</b> {fmt_signed_usd(total_pnl)}")
        body.append("─────────────────────────────")
    
    # Mostrar cada wallet con formato mejorado
    for idx, r in enumerate(rows, 1):
        addr = r.get("addr", "")
        szi = r.get("szi")
        entry = r.get("entry")
        px = r.get("mark")
        liq = r.get("liq")
        val = r.get("value")
        upnl = r.get("upnl")
        opened_at = r.get("opened_at")
        
        # Encabezado de la wallet con enlace a HyperDash
        hyperdash_url = f"https://app.hyperdash.xyz/trader/{addr}"
        wallet_header = f"\n<b>#{idx} Wallet</b> → <a href='{hyperdash_url}'>{addr[:8]}...{addr[-6:]}</a>"
        body.append(wallet_header)
        
        # Tiempo desde apertura
        if opened_at:
            time_since = time_ago(opened_at)
            body.append(f"  ⏱️ Abierta: <code>{time_since}</code>")
        
        # Cada parámetro en su línea con mejor formato
        if szi is not None:
            body.append(f"  📊 Size: <code>{abs(szi):.4f}</code>")
        if entry is not None:
            body.append(f"  💰 Entry: <code>${entry:.2f}</code>")
        if px is not None:
            body.append(f"  📈 Mark: <code>${px:.2f}</code>")
            # Calcular % de cambio
            if entry is not None and entry > 0:
                change_pct = ((px - entry) / entry) * 100
                change_emoji = "🟢" if change_pct >= 0 else "🔴"
                body.append(f"  {change_emoji} Cambio: <code>{change_pct:+.2f}%</code>")
        if liq is not None:
            # Calcular distancia a liquidación
            if px is not None and px > 0:
                dist_to_liq = abs((liq - px) / px) * 100
                liq_emoji = "⚠️" if dist_to_liq < 20 else "✅"
                body.append(f"  {liq_emoji} Liquidación: <code>${liq:.2f}</code> ({dist_to_liq:.1f}%)")
            else:
                body.append(f"  ⚠️ Liquidación: <code>${liq:.2f}</code>")
        if val is not None:
            body.append(f"  💵 Valor: <code>{fmt_usd(val)}</code>")
        if upnl is not None:
            pnl_emoji = "📈" if upnl >= 0 else "📉"
            pnl_symbol = "+" if upnl >= 0 else ""
            body.append(f"  {pnl_emoji} PnL: <b>{pnl_symbol}{fmt_usd(upnl)}</b>")
    
    body.append("\n═══════════════════════════")
    
    return "\n".join([header] + body)

def format_wallet_line(r: dict) -> str:
    addr = r.get("addr", "")
    szi = r.get("szi")
    entry = r.get("entry")
    px = r.get("mark")
    liq = r.get("liq")
    val = r.get("value")
    upnl = r.get("upnl")
    
    parts = [f"• <code>{addr}</code>"]
    if szi is not None: 
        parts.append(f"szi={abs(szi):.4f}")
    if entry is not None: 
        parts.append(f"entry={entry:.2f}")
    if px is not None: 
        parts.append(f"px={px:.2f}")
    if liq is not None: 
        parts.append(f"liq={liq:.2f}")
    if val is not None: 
        parts.append(f"value={fmt_usd(val)}")
    if upnl is not None: 
        parts.append(f"uPnL={fmt_signed_usd(upnl)}")
    
    return " | ".join(parts)

class ConsensusEngine:
    def __init__(self, cfg: dict):
        self.cfg = cfg if "config" in cfg else {"config": cfg}
        self.ws_callback = None
        self.last_signals = {}  # Cache de últimas señales por coin para detectar cambios
        self.force_check_flag = False  # Flag para forzar chequeo
        self.last_positions = {}  # Cache de posiciones para stats
        self.position_timestamps = {}  # Guardar cuándo detectamos cada posición
        self.running = True  # Flag para controlar los loops
        print(f"[CFG] wallets: {self.cfg['config'].get('wallets', [])}")
        print(f"[CFG] consensus_count: {self.cfg['config'].get('consensus_count', 1)} | use_positions: {self.cfg['config'].get('use_positions', True)}")
        print(f"[CFG] data dir: {DATA_DIR}")

    def set_ws_callback(self, cb):
        self.ws_callback = cb
    
    async def force_check(self):
        """Forzar un chequeo inmediato"""
        self.force_check_flag = True
        print("[CMD] Force check requested")
    
    async def telegram_listener(self):
        """Loop separado para escuchar comandos de Telegram en tiempo real"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print(f"[TG] Telegram listener disabled - BOT_TOKEN: {'✓' if TELEGRAM_BOT_TOKEN else '✗'}, CHAT_ID: {'✓' if TELEGRAM_CHAT_ID else '✗'}")
            return
        
        print(f"[TG] Telegram listener started - Monitoring chat ID: {TELEGRAM_CHAT_ID}")
        
        while self.running:
            try:
                updates = await get_telegram_updates()
                if updates:
                    print(f"[TG] Received {len(updates)} update(s)")
                    
                for update in updates:
                    if "message" in update and "text" in update["message"]:
                        chat_id = str(update["message"]["chat"]["id"])
                        text = update["message"]["text"]
                        username = update["message"].get("from", {}).get("username", "unknown")
                        
                        print(f"[TG] Message from @{username} (chat_id: {chat_id}): {text}")
                        
                        # Solo procesar si es del chat configurado
                        if chat_id == TELEGRAM_CHAT_ID:
                            print(f"[TG] ✓ Chat ID matches, processing command")
                            await process_telegram_command(text, self)
                        else:
                            print(f"[TG] ✗ Chat ID mismatch - Expected: {TELEGRAM_CHAT_ID}, Got: {chat_id}")
                            await send_telegram_html(f"❌ Acceso denegado. Tu chat ID es: {chat_id}")
            except Exception as e:
                print(f"[TG] Listener error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)
    
    async def send_stats_report(self):
        """Enviar reporte de estadísticas de todas las posiciones"""
        config = self.cfg.get("config", {})
        wallets = config.get("wallets", [])
        coins = config.get("symbols", ["BTC"])
        
        if not wallets:
            await send_telegram_html("❌ No hay wallets configuradas")
            return
        
        mids = get_all_mids()
        
        stats_msg = "╔═══════════════════════════\n<b>📊 ESTADÍSTICAS GENERALES</b>\n╚═══════════════════════════\n\n"
        
        for coin in coins:
            long_wallets = []
            short_wallets = []
            neutral_wallets = []
            
            for addr in wallets:
                try:
                    st = post_info({"type": "clearinghouseState", "user": addr})
                except Exception:
                    st = {}
                
                det = extract_pos_details(st, coin)
                szi = det.get("szi")
                
                if szi is not None and abs(szi) > 0.0001:
                    entry = det.get("entryPx")
                    px = mids.get(coin.upper())
                    upnl = ((px - entry) * szi) if (entry and px) else 0
                    
                    wallet_info = {
                        "addr": addr,
                        "szi": szi,
                        "entry": entry,
                        "mark": px,
                        "upnl": upnl
                    }
                    
                    if szi > 0:
                        long_wallets.append(wallet_info)
                    else:
                        short_wallets.append(wallet_info)
                else:
                    neutral_wallets.append(addr)
            
            stats_msg += f"<b>━━━ {coin} ━━━</b>\n"
            stats_msg += f"🟢 LONG: {len(long_wallets)} | 🔴 SHORT: {len(short_wallets)} | ⚪ Sin posición: {len(neutral_wallets)}\n\n"
            
            if long_wallets:
                total_long_pnl = sum(w["upnl"] for w in long_wallets)
                pnl_emoji = "📈" if total_long_pnl >= 0 else "📉"
                stats_msg += f"🟢 <b>Total LONG PnL:</b> {pnl_emoji} {fmt_signed_usd(total_long_pnl)}\n"
            
            if short_wallets:
                total_short_pnl = sum(w["upnl"] for w in short_wallets)
                pnl_emoji = "📈" if total_short_pnl >= 0 else "📉"
                stats_msg += f"🔴 <b>Total SHORT PnL:</b> {pnl_emoji} {fmt_signed_usd(total_short_pnl)}\n"
            
            stats_msg += "\n"
        
        stats_msg += "═══════════════════════════"
        await send_telegram_html(stats_msg)
    
    def _get_signal_key(self, signal: dict) -> str:
        """Genera una clave única para la señal basada en sus datos importantes"""
        rows = signal.get("wallet_rows", [])
        side = signal.get("side")
        
        wallet_data = []
        for r in rows:
            szi = r.get("szi")
            if szi is not None and abs(szi) > 0.0001:
                addr = r.get("addr")
                wallet_data.append(f"{addr}:{round(abs(szi), 4)}")
        
        return f"{signal['coin']}:{side}:{len(wallet_data)}:{','.join(sorted(wallet_data))}"
    
    def _has_signal_changed(self, coin: str, signal: dict) -> bool:
        """Verifica si la señal ha cambiado desde la última vez"""
        new_key = self._get_signal_key(signal)
        old_key = self.last_signals.get(coin)
        
        if old_key is None:
            return True  # Primera vez
        
        return new_key != old_key

    async def compute_last_snapshot(self):
        """
        Ejecuta la misma lógica que /last pero devuelve datos estructurados
        para la web (sin enviar a Telegram)
        """
        config = self.cfg.get("config", {})
        wallets = config.get("wallets", [])
        coins = config.get("symbols", ["BTC"])
        consensus = int(config.get("consensus_count", 1))

        if not wallets:
            return []

        mids = get_all_mids()
        snapshots = []

        for coin in coins:
            rows = []
            for addr in wallets:
                try:
                    st = post_info({"type": "clearinghouseState", "user": addr})
                except Exception:
                    st = {}

                det = extract_pos_details(st, coin)
                szi = det.get("szi")
                entry = det.get("entryPx")
                liq = det.get("liqPx")
                px = mids.get(coin.upper())

                side = "long" if szi and szi > 0 else "short" if szi and szi < 0 else None
                value = (abs(szi) * px) if szi and px else None
                upnl = ((px - entry) * szi) if szi and entry and px else None

                rows.append({
                    "addr": addr,
                    "szi": szi,
                    "side": side,
                    "entry": entry,
                    "mark": px,
                    "liq": liq,
                    "value": value,
                    "upnl": upnl,
                })

            long_wallets = [r for r in rows if r["side"] == "long"]
            short_wallets = [r for r in rows if r["side"] == "short"]

            if len(long_wallets) >= consensus:
                snapshots.append({
                    "coin": coin,
                    "side": "long",
                    "count": len(long_wallets),
                    "threshold": consensus,
                    "ts": now_str(),
                    "use_positions": True,
                    "wallet_rows": long_wallets,
                })

            if len(short_wallets) >= consensus:
                snapshots.append({
                    "coin": coin,
                    "side": "short",
                    "count": len(short_wallets),
                    "threshold": consensus,
                    "ts": now_str(),
                    "use_positions": True,
                    "wallet_rows": short_wallets,
                })

        return snapshots
 

    async def loop(self):
        """Loop principal de monitoreo"""
        while self.running:
            try:
                config = self.cfg.get("config", {})
                wallets = config.get("wallets", [])
                coins = config.get("symbols", ["BTC"])
                consensus = int(config.get("consensus_count", 1))
                use_positions = bool(config.get("use_positions", True))
                poll_seconds = int(config.get("poll_seconds", 12))

                if not wallets:
                    print("[ENGINE] No wallets configured, skipping...")
                    await asyncio.sleep(poll_seconds)
                    continue

                # Si hay force check, ejecutar inmediatamente
                if self.force_check_flag:
                    print("[ENGINE] 🔄 Force check activated")
                    self.force_check_flag = False
                else:
                    print(f"[ENGINE] Polling {len(wallets)} wallets for {len(coins)} coins...")
                
                mids = get_all_mids()
                
                for coin in coins:
                    rows = []
                    for addr in wallets:
                        try:
                            st = post_info({"type": "clearinghouseState", "user": addr})
                        except Exception as e:
                            print(f"[API] Error fetching state for {addr}: {e}")
                            st = {}
                        
                        det = extract_pos_details(st, coin)
                        szi = det.get("szi")
                        entry = det.get("entryPx")
                        liq = det.get("liqPx")
                        px = mids.get(coin.upper())
                        
                        # Determinar el lado de la posición
                        side = None
                        if szi is not None:
                            if szi > 0:
                                side = "long"
                            elif szi < 0:
                                side = "short"
                        
                        value = (abs(szi) * px) if (szi is not None and px is not None) else None
                        upnl = ((px - entry) * szi) if (szi is not None and entry is not None and px is not None) else None
                        
                        # Registrar timestamp si es nueva posición
                        pos_key = f"{addr}:{coin}:{side}"
                        if side and pos_key not in self.position_timestamps:
                            self.position_timestamps[pos_key] = now_str()
                            print(f"[POS] New position detected: {pos_key}")
                        
                        # Obtener timestamp de apertura
                        opened_at = self.position_timestamps.get(pos_key)
                        
                        rows.append({
                            "addr": addr, 
                            "szi": szi,
                            "side": side,
                            "entry": entry, 
                            "mark": px,
                            "liq": liq, 
                            "value": value, 
                            "upnl": upnl,
                            "opened_at": opened_at
                        })
                    
                    # Guardar posiciones para stats
                    self.last_positions[coin] = rows

                    # Contar por lado (long/short)
                    long_wallets = [r for r in rows if r.get("side") == "long"]
                    short_wallets = [r for r in rows if r.get("side") == "short"]
                    long_count = len(long_wallets)
                    short_count = len(short_wallets)
                    
                    # Verificar si algún lado alcanza el consenso
                    signals_to_send = []
                    
                    if long_count >= consensus:
                        signals_to_send.append({
                            "coin": coin,
                            "side": "long",
                            "count": long_count,
                            "threshold": consensus,
                            "ts": now_str(),
                            "use_positions": use_positions,
                            "wallet_rows": long_wallets,
                        })
                    
                    if short_count >= consensus:
                        signals_to_send.append({
                            "coin": coin,
                            "side": "short",
                            "count": short_count,
                            "threshold": consensus,
                            "ts": now_str(),
                            "use_positions": use_positions,
                            "wallet_rows": short_wallets,
                        })
                    
                    # Procesar cada señal que alcanzó consenso
                    for signal in signals_to_send:
                        signal_key = self._get_signal_key(signal)
                        has_changed = self._has_signal_changed(f"{coin}_{signal['side']}", signal)
                        
                        if has_changed:
                            side_name = signal['side'].upper()
                            print(f"[ALERT] 🚨 {coin} {side_name} consensus: {signal['count']}/{consensus}")
                            self.last_signals[f"{coin}_{signal['side']}"] = signal_key
                            
                            # Send to websocket clients
                            if self.ws_callback:
                                try:
                                    await self.ws_callback(signal)
                                except Exception as e:
                                    print(f"[WS] callback error: {e}")

                            # Send to Telegram
                            msg = build_tg_html(signal)
                            await send_telegram_html(msg)
                            print(f"[TG] Alert sent for {coin} {side_name}")
                        else:
                            # Hay consenso pero sin cambios - NO enviar alerta
                            side_name = signal['side'].upper()
                            print(f"[INFO] ✓ {coin} {side_name}: {signal['count']}/{consensus} (no changes, alert suppressed)")
                    
                    # Log info si no hay consenso
                    if not signals_to_send:
                        print(f"[INFO] {coin}: {long_count}L/{short_count}S - No consensus ({consensus} needed)")

                # Solo esperar si no hay force check pendiente
                if not self.force_check_flag:
                    await asyncio.sleep(poll_seconds)
                
            except Exception as e:
                print(f"[ERR] loop: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)

    

if __name__ == "__main__":
    cfg = load_config()
    eng = ConsensusEngine(cfg)
    asyncio.run(eng.loop())
