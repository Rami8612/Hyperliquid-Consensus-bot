# Hyperliquid Consensus Radar

A real-time monitoring system for detecting **position consensus across multiple Hyperliquid wallets**, with **Telegram alerts** and an optional **Web UI dashboard**.

The system identifies situations where a configurable number of wallets hold positions in the **same direction (LONG / SHORT)** for the **same asset**, and notifies users when consensus conditions are met.

---

## Key features

- Consensus detection across multiple Hyperliquid wallets  
- Support for multiple trading pairs  
- Configurable consensus threshold  
- Position-based monitoring (not just fills)  
- Periodic polling with cooldown protection  
- Telegram bot with full command interface  
- Optional Web UI with:
  - WebSocket real-time updates
  - On-demand snapshot loading (state persistence across reloads)
- No external databases required  
- Designed for long-running execution (VPS / server)

---

## Architecture overview

The project is built around a **single consensus engine** shared across all interfaces:

- **ConsensusEngine** (`hl_consensus.py`)  
  Core logic, position tracking, consensus detection and alert suppression.

- **Telegram Bot runner** (`bot.py`)  
  Headless runner that sends alerts and accepts runtime commands via Telegram.

- **Web API + UI** (`app.py`)  
  FastAPI backend providing REST endpoints, WebSocket updates and a static HTML dashboard.

All components rely on the **same detection logic and configuration**, ensuring consistent behaviour across Telegram and Web.

---

## Project structure

```
backend/
├── app.py              # FastAPI backend + WebSocket + Web UI
├── bot.py              # Telegram-only runner (headless mode)
├── hl_consensus.py     # Core consensus engine
├── requirements.txt
├── .env.example
├── run.sh
└── data/               # Runtime state (auto-generated, not versioned)
```

---

## Configuration

Configuration is handled through environment variables.

A template is provided in:

```
.env.example
```

Create your own `.env` file:

```bash
cp .env.example .env
```

Main configuration parameters include:

- Wallets to monitor
- Polling interval
- Consensus threshold
- Minimum notional value
- Telegram credentials (optional)

Runtime state (configuration snapshots, caches, optional history) is stored under the `data/` directory and generated automatically at execution time.

---

## Running the system

### 1. Create and activate virtual environment

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run in Telegram-only mode (recommended for VPS)

```bash
python bot.py
```

This mode runs continuously and sends alerts directly to Telegram.

---

### 4. Run with Web UI

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Then open in your browser:

```
http://localhost:8000
```

The Web UI supports:
- Real-time updates via WebSocket
- Manual refresh to load the latest detected state

---

## Telegram Commands

The bot can be fully operated via Telegram commands.

### Queries
- `/reload` — Force an immediate on-chain refresh
- `/last` — Show latest detected consensus signals
- `/status` — Display current system status
- `/config` — Show current configuration
- `/stats` — Show aggregated position statistics

### Configuration
- `/add_wallet 0x...` — Add a wallet to monitor
- `/remove_wallet 0x...` — Remove a wallet (full or partial address)
- `/add_coin BTC` — Add a symbol to monitor
- `/remove_coin BTC` — Remove a monitored symbol
- `/set_consensus N` — Set required wallet count for consensus
- `/set_interval SECONDS` — Update polling interval

### Help
- `/commands` — Show detailed command examples
- `/help` — Show command menu


All changes are applied **at runtime**, without restarting the service.

---

## Design notes

- The system uses **polling**, not event subscriptions  
- Multiple independent instances may emit alerts at different times depending on poll alignment  
- This behaviour is intentional and provides redundancy  
- No external state sharing is required

---

## Project status

This project is actively used in private environments.

The public repository is published for **demonstration and engineering reference**, focusing on system architecture, consensus logic and real-time monitoring design.

Deployment-specific secrets and runtime state are intentionally excluded.
"# Hyperliquid-Consensus-bot" 
