#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hyperliquid Consensus Radar - Bot Version (Solo Telegram)
Sin interfaz web, optimizado para VPS
"""
import asyncio
from hl_consensus import ConsensusEngine, load_config

async def main():
    print("=" * 50)
    print("🤖 Hyperliquid Consensus Radar - Bot Mode")
    print("=" * 50)
    
    # Cargar configuración
    cfg = load_config()
    
    # Crear engine
    engine = ConsensusEngine(cfg)
    
    print("\n✅ Bot iniciado correctamente")
    print("📱 Escuchando comandos de Telegram...")
    print("🔄 Monitoreando posiciones automáticamente...\n")
    print("Presiona Ctrl+C para detener\n")
    
    # Ejecutar ambos loops en paralelo
    await asyncio.gather(
        engine.loop(),
        engine.telegram_listener()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️  Bot detenido por el usuario")
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()