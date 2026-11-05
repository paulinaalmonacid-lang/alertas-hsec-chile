#!/usr/bin/env python3
"""Compara el feed candidato con el publicado y, solo si hay cambios oficiales,
escribe el nuevo alerts.json con su fecha de generacion.

Uso: python tools/aplicar_cambios.py alerts.json candidato.json
Salida: imprime ACTUALIZADO o SIN CAMBIOS, y escribe changed=... en $GITHUB_OUTPUT.
"""
import json, os, sys, datetime as dt

def clave(feed):
    # Lo que define un cambio oficial: las alertas y las cancelaciones recientes.
    return json.dumps({"alerts": feed.get("alerts", []),
                       "recentChanges": feed.get("recentChanges", [])},
                      ensure_ascii=False, sort_keys=True)

def main():
    if len(sys.argv) != 3:
        print("Uso: aplicar_cambios.py <alerts.json> <candidato.json>"); sys.exit(2)
    destino, candidato_path = sys.argv[1], sys.argv[2]
    nuevo = json.load(open(candidato_path, encoding="utf-8"))
    if not nuevo.get("alerts") and not nuevo.get("recentChanges"):
        print("ERROR: el candidato vino vacio; no se toca nada."); sys.exit(2)
    try:
        viejo = json.load(open(destino, encoding="utf-8"))
    except Exception:
        viejo = {}
    cambio = clave(viejo) != clave(nuevo)
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write("changed=%s\n" % ("true" if cambio else "false"))
    if not cambio:
        print("SIN CAMBIOS: %d alertas vigentes" % len(nuevo.get("alerts", [])))
        return
    ahora = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3)))
    nuevo["generatedAt"] = ahora.isoformat(timespec="seconds")
    marca = ahora.strftime("%d-%m-%Y %H:%M")
    for a in nuevo.get("alerts", []):
        a["verifiedAt"] = marca
    json.dump(nuevo, open(destino, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("ACTUALIZADO: %d alertas vigentes al %s" % (len(nuevo.get("alerts", [])), marca))

if __name__ == "__main__":
    main()
