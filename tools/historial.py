#!/usr/bin/env python3
"""Lleva el historial de alertas por comuna.

Cada vez que corre el lector de SENAPRED, este script compara el estado nuevo
con el historial guardado y lo va completando: abre un tramo cuando una comuna
entra en alerta, lo cierra cuando sale, y empieza un tramo nuevo cuando la
misma alerta cambia de nivel. No consulta nada por su cuenta: solo ordena lo
que el lector ya trajo.

Uso:
  python tools/historial.py --alerts alerts.json --out historial.json
  python tools/historial.py --alerts alerts.json --out historial.json --now "13-11-2026 12:00"
"""
import argparse
import datetime as dt
import json
import os
import re
import unicodedata

DATE_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{4}) (\d{1,2}):(\d{2})$")


def key(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def ahora_texto(now=None):
    if now:
        return now
    t = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).replace(tzinfo=None)
    return t.strftime("%d-%m-%Y %H:%M")


def ts(at):
    m = DATE_RE.match(str(at or ""))
    return dt.datetime(int(m[3]), int(m[2]), int(m[1]), int(m[4]), int(m[5])) if m else None


def actualizar(hist, feed, ahora):
    """Devuelve el historial con el estado de este momento ya incorporado."""
    comunas = hist.setdefault("comunas", {})
    hist.setdefault("desde", ahora)

    # Lo que esta vigente ahora, por comuna: clave de tramo -> datos de la alerta.
    vigente = {}
    for a in feed.get("alerts", []):
        ident = a.get("id") or a.get("officialUrl") or (a.get("hazard", "") + a.get("level", ""))
        for c in a.get("communes", []):
            vigente.setdefault(key(c), {})[ident] = {
                "n": c,
                "nivel": a.get("level", ""),
                "peligro": a.get("hazard", "") or "Evento",
                "declarada": a.get("officialDeclaredAt", ""),
                "url": a.get("officialUrl", ""),
            }

    for k, alertas in vigente.items():
        com = comunas.setdefault(k, {"n": next(iter(alertas.values()))["n"], "eventos": []})
        com["n"] = next(iter(alertas.values()))["n"]
        for ident, info in alertas.items():
            abierto = next((e for e in com["eventos"] if e.get("abierto") and e.get("ref") == ident), None)
            # Un cambio de nivel cierra el tramo y abre otro: asi el historial
            # muestra "estuvo Amarilla y despues paso a Roja", no un solo tramo.
            if abierto and abierto.get("nivel") != info["nivel"]:
                abierto["abierto"] = False
                abierto["hasta"] = ahora
                abierto = None
            if abierto:
                abierto["hasta"] = ahora
                abierto["peligro"] = info["peligro"]
            else:
                com["eventos"].append({
                    "ref": ident, "nivel": info["nivel"], "peligro": info["peligro"],
                    "desde": info["declarada"] or ahora, "hasta": ahora,
                    "url": info["url"], "abierto": True,
                })

    # Tramos que estaban abiertos y ya no aparecen: se cierran.
    for k, com in comunas.items():
        activos = vigente.get(k, {})
        for e in com["eventos"]:
            if e.get("abierto") and e.get("ref") not in activos:
                e["abierto"] = False

    hist["generatedAt"] = ahora
    hist["comunas"] = comunas
    return hist


def resumen(hist):
    tot = sum(len(c["eventos"]) for c in hist.get("comunas", {}).values())
    abiertos = sum(1 for c in hist.get("comunas", {}).values() for e in c["eventos"] if e.get("abierto"))
    return "%d comunas con historial · %d tramos (%d vigentes) desde el %s" % (
        len(hist.get("comunas", {})), tot, abiertos, hist.get("desde", "?"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alerts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--now", help="dd-mm-aaaa hh:mm (para pruebas y para rehacer el historial)")
    a = ap.parse_args()
    feed = json.load(open(a.alerts, encoding="utf-8"))
    hist = json.load(open(a.out, encoding="utf-8")) if os.path.exists(a.out) else {}
    hist = actualizar(hist, feed, ahora_texto(a.now))
    json.dump(hist, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("Historial: " + resumen(hist))


if __name__ == "__main__":
    main()
