#!/usr/bin/env python3
"""
Lector de Alertas Amarillas y Rojas de SENAPRED para "Alertas HSEC por Comuna".

Abre https://senapred.cl/alertas/ con un navegador automatizado (Playwright/Chromium),
recorre todas las páginas del listado, abre la ficha de cada Alerta Amarilla o Roja y
construye un feed candidato con el mismo formato de alerts.json.

Uso:
  python3 senapred_scraper.py --previous alerts.json --comunas comunas_cl.json --out candidato.json

Salidas:
  candidato.json  -> feed propuesto (alerts + recentChanges), sin generatedAt definitivo
  stdout          -> resumen de diferencias contra --previous, y advertencias

Reglas que respeta:
  - Solo SENAPRED. No usa DMC ni CONAF.
  - Nunca inventa fechas: todas salen del texto de SENAPRED.
  - No infiere cancelaciones: una alerta previa que no aparece y sin cancelación visible
    se conserva y se informa como ADVERTENCIA.
"""
import argparse, json, re, sys, unicodedata, datetime as dt

BASE = "https://senapred.cl"
LIST_URL = BASE + "/alertas/"
DATE_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{4}) (\d{1,2}):(\d{2})$")

REGIONES = {
    "arica y parinacota": "15", "tarapaca": "01", "antofagasta": "02", "atacama": "03", "coquimbo": "04",
    "valparaiso": "05", "metropolitana": "13", "metropolitana de santiago": "13", "o higgins": "06",
    "libertador general bernardo o higgins": "06", "libertador bernardo o higgins": "06", "maule": "07", "nuble": "16",
    "biobio": "08", "bio bio": "08", "la araucania": "09", "araucania": "09", "los rios": "14", "los lagos": "10",
    "aysen": "11", "aysen del general carlos ibanez del campo": "11", "magallanes": "12",
    "magallanes y de la antartica chilena": "12", "magallanes y antartica chilena": "12",
}
REG_NAME = {"15": "Región de Arica y Parinacota", "01": "Región de Tarapacá", "02": "Región de Antofagasta",
            "03": "Región de Atacama", "04": "Región de Coquimbo", "05": "Región de Valparaíso",
            "13": "Región Metropolitana", "06": "Región de O'Higgins", "07": "Región del Maule", "16": "Región de Ñuble",
            "08": "Región del Biobío", "09": "Región de La Araucanía", "14": "Región de Los Ríos",
            "10": "Región de Los Lagos", "11": "Región de Aysén", "12": "Región de Magallanes"}
ALIAS = {"aisen": "aysen", "coihaique": "coyhaique", "la calera": "calera", "puerto natales": "natales",
         "paiguano": "paihuano", "trehuaco": "treguaco", "llay llay": "llaillay", "til til": "tiltil",
         "marchihue": "marchigue", "santiago centro": "santiago", "rapa nui": "isla de pascua",
         "alto bio bio": "alto biobio", "chol chol": "cholchol"}


def norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def key(s):
    k = norm(s)
    k = re.sub(r"^comuna de ", "", k)
    return ALIAS.get(k, k)


def level_after(title):
    """Nivel vigente después de un boletín, según su título."""
    t = norm(title)
    if re.search(r"se cancela alerta roja y (se )?declara alerta amarilla", t):
        return "Amarilla"
    if re.search(r"se cancela alerta amarilla y (se )?declara alerta roja", t):
        return "Roja"
    if t.startswith("se cancela") and re.search(r"declara alerta temprana|$", t) and "declara alerta amarilla" not in t and "declara alerta roja" not in t:
        return "Cancelada"
    if "alerta roja" in t:
        return "Roja"
    if "alerta amarilla" in t:
        return "Amarilla"
    if "temprana preventiva" in t:
        return "Verde"
    return ""


def action_of(title):
    a = re.split(r"\s+para\s+(la|las|el|los)\s+", title, maxsplit=1)[0].strip()
    return re.sub(r"\s+", " ", a)


def hazard_of(title):
    """El peligro es lo que va despues de "por". El titulo puede seguir con el
    alcance o con la cancelacion de otra alerta, y eso no es parte del peligro:
    "... por calor extremo para las Comunas de X y cancela Alerta Amarilla ..."."""
    m = re.search(r"\s+por\s+(.+)$", title, flags=re.I)
    h = m.group(1).strip() if m else ""
    h = re.split(r"\s+(?:y\s+(?:se\s+)?(?:declara|cancela)\b|para\s+(?:la|las|el|los)\b)", h, maxsplit=1, flags=re.I)[0]
    h = re.sub(r"\s+", " ", h).strip(" .,;:")
    return h[:1].upper() + h[1:] if h else ""


class Places:
    def __init__(self, comunas):
        self.by_key = {}
        self.by_region, self.by_prov = {}, {}
        for c in comunas:
            self.by_key[key(c["n"])] = c
            self.by_region.setdefault(c["r"], []).append(c["n"])
            self.by_prov.setdefault(norm(c["p"]), []).append(c["n"])

    def prov_lookup(self, nombre):
        """Busca una provincia tolerando el nombre corto: "San Felipe" tiene que
        encontrar "San Felipe de Aconcagua", y "El Loa" tanto con articulo como sin el."""
        n = norm(nombre).strip()
        if not n:
            return None
        if n in self.by_prov:
            return self.by_prov[n]
        cand = [k for k in self.by_prov
                if k.startswith(n + " ") or n.startswith(k + " ") or k == "el " + n or n == "el " + k]
        return self.by_prov[cand[0]] if len(cand) == 1 else None

    def resolve(self, title):
        """Devuelve (comunas, regiones, texto_no_resuelto) a partir del título del boletín vigente."""
        t = title.replace("’", "'")
        # Solo el tramo que describe el alcance: entre "para" y " por " (o " y declara")
        m = re.search(r"\bpara\s+(.*?)\s+por\s+", t, flags=re.I)
        scope = m.group(1) if m else t
        communes, regions, unresolved = [], set(), []
        # comunas explícitas
        # El articulo es opcional: SENAPRED escribe tanto "y las comunas de X"
        # como "y comunas de X", y el tramo termina donde empieza otro alcance.
        for cm in re.finditer(r"(?:(?:la|las)\s+)?comunas?\s+de\s+(.+?)(?=\s+(?:en|de)\s+la\s+regi[oó]n|\s+y\s+para\s+|\s+y\s+(?:la|las\s+)?provincias?\s|$)", scope, flags=re.I):
            parts = re.split(r",\s*|\s+y\s+", cm.group(1))
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                c = self.by_key.get(key(p))
                if c:
                    communes.append(c["n"]); regions.add(c["r"])
                else:
                    unresolved.append(p)
        # provincias. SENAPRED escribe "de", "del" y "de la" segun la provincia
        # ("Provincia del Tamarugal", "Provincia de Arauco"), y a veces usa el
        # nombre corto de una provincia cuyo nombre oficial es mas largo.
        for pm in re.finditer(r"(?:la|las)\s+provincias?\s+(?:de\s+la\s+|del\s+|de\s+)?(.+?)(?=\s+y\s+(?:la|las\s+)?comunas?\s|\s+en\s+la\s+regi[oó]n|$)", scope, flags=re.I):
            for p in re.split(r",\s*|\s+y\s+", pm.group(1)):
                lst = self.prov_lookup(p)
                if lst:
                    communes += lst
                    regions.add(self.by_key[key(lst[0])]["r"])
                elif p.strip():
                    unresolved.append("provincia " + p.strip())
        # región completa (solo si no hay comunas ni provincias en el alcance)
        if not communes:
            rm = re.search(r"(?:la\s+)?regi[oó]n\s+(?:de\s+|del\s+)?(.+)$", scope, flags=re.I)
            if rm:
                code = REGIONES.get(norm(rm.group(1)))
                if code:
                    communes = list(self.by_region.get(code, [])); regions.add(code)
                else:
                    unresolved.append("región " + rm.group(1).strip())
        # Fragmentos que otro tramo del mismo titulo ya resolvio: no son avisos utiles.
        unresolved = [u for u in unresolved
                      if not re.search(r"\bcancela\b", norm(u))
                      and not (u.startswith("provincia ") and re.search(r"comunas? de", norm(u)))]
        seen, out = set(), []
        for c in communes:
            if c not in seen:
                seen.add(c); out.append(c)
        return out, sorted(regions), unresolved


def parse_ficha(text):
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    entries = []
    for i, l in enumerate(lines):
        if DATE_RE.match(l):
            j = i - 1
            while j >= 0 and re.match(r"^regi[oó]n\b", lines[j], flags=re.I):
                j -= 1
            if j >= 0:
                entries.append({"title": lines[j], "at": l})
    region = next((l for l in lines[:6] if re.match(r"^regi[oó]n\b", l, flags=re.I)), "")
    return entries, region


# Una alerta que deja de aparecer en SENAPRED sin cancelacion visible se conserva
# por si el listado la escondio, pero no para siempre: pasada una semana se descarta,
# porque dejarla inflaria las personas expuestas con una emergencia ya terminada.
DIAS_CONSERVAR = 7


def ts(at):
    m = DATE_RE.match(at)
    return dt.datetime(int(m[3]), int(m[2]), int(m[1]), int(m[4]), int(m[5])) if m else None


def scrape(max_pages=60, timeout=30000):
    from playwright.sync_api import sync_playwright
    items, pages = {}, 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        # SENAPRED muestra las fechas en la hora local del navegador: fijamos la de Chile
        # continental para que el resultado no dependa de donde se ejecute el lector.
        pg = b.new_page(viewport={"width": 1200, "height": 1600}, locale="es-CL",
                        timezone_id="America/Santiago")
        pg.goto(LIST_URL, wait_until="domcontentloaded", timeout=timeout)
        pg.wait_for_function("document.querySelectorAll('a[href*=\"/alerta/\"]').length>0", timeout=timeout)
        last_sig = None
        while pages < max_pages:
            pages += 1
            pg.wait_for_timeout(1500)
            batch = pg.evaluate(r"""() => [...document.querySelectorAll('a[href*="/alerta/"]')].map(a => {
                let el = a, txt = '';
                for (let k = 0; k < 6 && el; k++) { txt = (el.innerText || '').trim(); if (/\d{2}-\d{2}-\d{4} \d{1,2}:\d{2}/.test(txt)) break; el = el.parentElement; }
                return {href: a.getAttribute('href'), text: txt};
            })""")
            body = pg.inner_text("body")
            sig = "|".join(x["href"] for x in batch)
            if "Sin alertas que mostrar" in body or not batch or sig == last_sig:
                break
            last_sig = sig
            for x in batch:
                ls = [l.strip() for l in x["text"].splitlines() if l.strip()]
                date = next((l for l in ls if DATE_RE.match(l)), "")
                title = next((l for l in ls if not DATE_RE.match(l)), "")
                url = BASE + x["href"] if x["href"].startswith("/") else x["href"]
                items.setdefault(url, {"url": url, "title": title, "at": date})
            nxt = pg.get_by_role("button", name=">>")
            if not nxt.count():
                break
            btn = nxt.first
            try:
                # En la ultima pagina el boton sigue presente pero deshabilitado.
                if btn.is_disabled(timeout=5000):
                    break
                btn.click(timeout=10000)
            except Exception:
                break
        fichas = {}
        for url, it in items.items():
            if not re.search(r"alerta (amarilla|roja)", norm(it["title"])):
                continue
            pg.goto(url, wait_until="domcontentloaded", timeout=timeout)
            try:
                pg.wait_for_function("/\\d{2}-\\d{2}-\\d{4} \\d{1,2}:\\d{2}/.test(document.body.innerText)", timeout=timeout)
            except Exception:
                pass
            pg.wait_for_timeout(800)
            fichas[url] = pg.inner_text("body")
        b.close()
    return list(items.values()), fichas, pages


def preventivas(items, places, now, dias=30):
    """Alertas Tempranas Preventivas vigentes segun el listado de SENAPRED.

    El titulo de cada item refleja su ULTIMO estado: si todavia dice que se
    declara una Temprana Preventiva, sigue vigente; si dice que se cancela, no.
    Son avisos previos, nunca Alertas Amarillas ni Rojas, y van aparte."""
    out = []
    for it in items:
        t = norm(it["title"])
        if "temprana preventiva" not in t or t.startswith("se cancela"):
            continue
        d = ts(it["at"])
        if not d or (now - d).days > dias:
            continue
        communes, regs, _ = places.resolve(it["title"])
        out.append({
            "at": it["at"], "hazard": hazard_of(it["title"]) or "Evento",
            "region": ", ".join(REG_NAME[r] for r in regs),
            "communes": communes, "regions": regs,
            "detail": it["title"], "officialUrl": it["url"],
        })
    out.sort(key=lambda x: ts(x["at"]) or dt.datetime.min, reverse=True)
    return out


def build(items, fichas, places, previous, now):
    prev_alerts = previous.get("alerts", []) if previous else []
    prev_by_url = {a.get("officialUrl"): a for a in prev_alerts}
    alerts, cancels, warnings = [], [], []
    for it in items:
        lvl_list = level_after(it["title"])
        if it["url"] in fichas:
            entries, region = parse_ficha(fichas[it["url"]])
            if not entries:
                warnings.append("No se pudo leer el historial de " + it["url"]); continue
            hist = sorted(({"at": e["at"], "level": level_after(e["title"]), "action": action_of(e["title"])} for e in entries if ts(e["at"])), key=lambda e: ts(e["at"]))
            # boletín vigente = el más reciente
            cur_title = max(entries, key=lambda e: ts(e["at"]) or dt.datetime.min)["title"]
            cur = level_after(cur_title)
            if cur == "Cancelada":
                communes, regs, unres = places.resolve(cur_title)
                d = ts(hist[-1]["at"])
                if d and (now - d).days < 14:
                    prevlvl = next((h["level"] for h in reversed(hist[:-1]) if h["level"] in ("Roja", "Amarilla")), "")
                    cancels.append({"at": hist[-1]["at"], "type": "cancelled", "level": prevlvl or "Amarilla", "hazard": hazard_of(cur_title),
                                    "region": region or ", ".join(REG_NAME[r] for r in regs), "communes": communes,
                                    "detail": cur_title, "officialUrl": it["url"]})
                continue
            if cur not in ("Roja", "Amarilla"):
                continue
            # Declaración del nivel vigente: inicio del último tramo con ese nivel
            start = len(hist) - 1
            while start > 0 and hist[start - 1]["level"] == cur:
                start -= 1
            declared = hist[start]["at"]
            updated = hist[-1]["at"] if len(hist) - 1 > start else ""
            communes, regs, unres = places.resolve(cur_title)
            if unres:
                warnings.append("Alcance no reconocido en '" + cur_title + "': " + ", ".join(unres))
            if not communes:
                warnings.append("Sin comunas reconocidas para '" + cur_title + "'. Revisar a mano."); continue
            prev = prev_by_url.get(it["url"])
            same = bool(prev) and prev.get("level") == cur
            slug = it["url"].rstrip("/").split("/")[-1]
            alerts.append({
                "id": prev["id"] if prev else "SENAPRED-" + re.sub(r"[^A-Z0-9]+", "-", slug.upper())[:80],
                "level": cur, "hazard": prev["hazard"] if same and prev.get("hazard") else hazard_of(cur_title),
                "region": prev["region"] if same and prev.get("region") else (region or ", ".join(REG_NAME[r] for r in regs)),
                "communes": communes,
                "source": "SENAPRED - Alerta " + cur + " oficial",
                "detail": (prev or {}).get("detail") if prev and prev.get("level") == cur else cur_title,
                "officialUrl": it["url"], "officialDeclaredAt": declared, "officialUpdatedAt": updated,
                "verifiedAt": now.strftime("%d-%m-%Y %H:%M"), "history": hist,
            })
        elif lvl_list == "Cancelada" and re.search(r"se cancela alerta (amarilla|roja)", norm(it["title"])):
            d = ts(it["at"])
            if d and (now - d).days < 14:
                communes, regs, _ = places.resolve(it["title"])
                cancels.append({"at": it["at"], "type": "cancelled", "level": "Roja" if "alerta roja" in norm(it["title"]) else "Amarilla",
                                "hazard": hazard_of(it["title"]), "region": ", ".join(REG_NAME[r] for r in regs), "communes": communes,
                                "detail": it["title"], "officialUrl": it["url"]})
    # Alertas previas que ya no aparecen y sin cancelación visible: se conservan
    found = {a["officialUrl"] for a in alerts} | {c["officialUrl"] for c in cancels}
    for a in prev_alerts:
        if a.get("officialUrl") in found:
            continue
        etiqueta = (a.get("hazard", "") + " (" + ", ".join(a.get("communes", [])[:3]) + ")")
        # SENAPRED a veces reemplaza un boletin por otro con URL nueva: si ya hay
        # una alerta vigente del mismo nivel, peligro y alcance, esta es la copia vieja.
        copia = any(b["level"] == a.get("level")
                    and norm(b.get("hazard", "")) == norm(a.get("hazard", ""))
                    and set(b.get("communes", [])) == set(a.get("communes", []))
                    for b in alerts)
        if copia:
            warnings.append("La alerta '" + etiqueta + "' aparece con un boletin nuevo: se descarta la copia anterior.")
            continue
        desde = a.get("missingSince") or now.strftime("%d-%m-%Y %H:%M")
        d0 = ts(desde)
        dias = (now - d0).days if d0 else 0
        if dias >= DIAS_CONSERVAR:
            warnings.append("La alerta '" + etiqueta + "' lleva " + str(dias) + " dias sin aparecer en SENAPRED y sin cancelacion: SE DESCARTA. Ficha: " + str(a.get("officialUrl")))
            continue
        warnings.append("La alerta '" + etiqueta + "' ya no aparece y no se encontró su cancelación: SE CONSERVA (dia " + str(dias + 1) + " de " + str(DIAS_CONSERVAR) + "). Revisar su ficha: " + str(a.get("officialUrl")))
        alerts.append({**a, "missingSince": desde})
    alerts.sort(key=lambda a: (0 if a["level"] == "Roja" else 1, a["hazard"]))
    return alerts, cancels, warnings


def events(prev, alerts, cancels, places):
    """Cambios que ameritan aviso por correo: alerta nueva, cambio de nivel, cambio de comunas, cancelación."""
    regs = lambda cs: sorted({places.by_key[key(c)]["r"] for c in cs if key(c) in places.by_key})
    ev = []
    pa = {a.get("officialUrl"): a for a in (prev or {}).get("alerts", [])}
    for a in alerts:
        p = pa.get(a["officialUrl"])
        base = {"level": a["level"], "hazard": a["hazard"], "region": a.get("region", ""), "communes": a["communes"],
                "regions": regs(a["communes"]), "url": a["officialUrl"], "at": a["officialUpdatedAt"] or a["officialDeclaredAt"]}
        if not p:
            ev.append({"kind": "new", **base})
        elif p.get("level") != a["level"]:
            ev.append({"kind": "level", "prevLevel": p.get("level"), **base})
        elif sorted(p.get("communes", [])) != sorted(a["communes"]):
            ev.append({"kind": "communes", **base})
    prev_c = {(c.get("at"), tuple(sorted(c.get("communes", [])))) for c in (prev or {}).get("recentChanges", [])}
    for c in cancels:
        if (c["at"], tuple(sorted(c["communes"]))) not in prev_c:
            ev.append({"kind": "cancelled", "level": c.get("level", ""), "hazard": c.get("hazard", ""), "region": c.get("region", ""),
                       "communes": c["communes"], "regions": regs(c["communes"]), "url": c.get("officialUrl", ""), "at": c["at"]})
    return ev


def diff_preventivas(prev, atp):
    antes = {(x.get("at"), tuple(sorted(x.get("communes", [])))) for x in (prev or {}).get("preventive", [])}
    ahora = {(x["at"], tuple(sorted(x["communes"]))) for x in atp}
    return antes != ahora


def diff(prev, alerts, cancels):
    out = []
    pa = {a.get("officialUrl"): a for a in (prev or {}).get("alerts", [])}
    na = {a["officialUrl"]: a for a in alerts}
    for u, a in na.items():
        p = pa.get(u)
        if not p:
            out.append("NUEVA: Alerta %s · %s · %s" % (a["level"], a["hazard"], ", ".join(a["communes"][:6])))
            continue
        if p.get("level") != a["level"]:
            out.append("CAMBIO DE NIVEL: %s → %s · %s" % (p.get("level"), a["level"], a["hazard"]))
        if sorted(p.get("communes", [])) != sorted(a["communes"]):
            out.append("CAMBIO DE COMUNAS: %s" % a["hazard"])
        if (p.get("officialUpdatedAt"), p.get("officialDeclaredAt")) != (a["officialUpdatedAt"], a["officialDeclaredAt"]):
            out.append("NUEVO BOLETÍN: %s · %s" % (a["hazard"], a["officialUpdatedAt"] or a["officialDeclaredAt"]))
        elif len(p.get("history", [])) != len(a.get("history", [])):
            out.append("HISTORIAL ACTUALIZADO: %s" % a["hazard"])
    for u, p in pa.items():
        if u not in na:
            out.append("CANCELADA: Alerta %s · %s" % (p.get("level"), p.get("hazard")))
    pc = {(c.get("at"), tuple(sorted(c.get("communes", [])))) for c in (prev or {}).get("recentChanges", [])}
    nc = {(c["at"], tuple(sorted(c["communes"]))) for c in cancels}
    if pc != nc:
        out.append("CAMBIO EN CANCELACIONES RECIENTES")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--previous"); ap.add_argument("--comunas", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--now", help="dd-mm-aaaa hh:mm (para pruebas)")
    ap.add_argument("--changes-out", help="archivo JSON con los cambios que ameritan aviso por correo")
    a = ap.parse_args()
    previous = json.load(open(a.previous, encoding="utf-8")) if a.previous else None
    places = Places(json.load(open(a.comunas, encoding="utf-8")))
    now = ts(a.now) if a.now else dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).replace(tzinfo=None)
    try:
        items, fichas, pages = scrape()
    except Exception as e:
        print("ERROR: no se pudo leer SENAPRED: %s" % e); sys.exit(2)
    if not items:
        print("ERROR: el listado de SENAPRED vino vacío. No se modifica nada."); sys.exit(2)
    alerts, cancels, warnings = build(items, fichas, places, previous, now)
    prev_atp = preventivas(items, places, now)
    feed = {"source": "SENAPRED", "mode": "verified_snapshot",
            "note": (previous or {}).get("note", "Feed operativo HSEC."),
            "alerts": alerts, "recentChanges": cancels, "preventive": prev_atp}
    json.dump(feed, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("Páginas del listado leídas: %d · ítems: %d · fichas abiertas: %d" % (pages, len(items), len(fichas)))
    print("Alertas vigentes: %d (%d Rojas) · cancelaciones recientes: %d · avisos preventivos: %d"
          % (len(alerts), sum(x["level"] == "Roja" for x in alerts), len(cancels), len(prev_atp)))
    ch = diff(previous, alerts, cancels)
    if diff_preventivas(previous, prev_atp):
        ch.append("CAMBIO EN AVISOS PREVENTIVOS (Alertas Tempranas Preventivas): %d vigentes" % len(prev_atp))
    if a.changes_out:
        ev = events(previous, alerts, cancels, places)
        json.dump(ev, open(a.changes_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("Cambios para aviso por correo: %d (ver %s)" % (len(ev), a.changes_out))
    print("CAMBIOS:" if ch else "SIN CAMBIOS OFICIALES")
    for c in ch: print("  - " + c)
    for w in warnings: print("ADVERTENCIA: " + w)


if __name__ == "__main__":
    main()
