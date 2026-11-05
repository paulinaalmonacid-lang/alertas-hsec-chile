#!/usr/bin/env python3
"""Envia un aviso por correo cuando SENAPRED declara, cambia o cancela una alerta.

Lee los cambios que detecto el lector (cambios.json) y escribe a cada persona
inscrita, filtrando por las regiones que le interesan.

Uso: python tools/avisar_correo.py cambios.json

Configuracion, toda por variables de entorno (secretos del repositorio):
  SMTP_USUARIO     correo desde el que se envia, p.ej. nombre@icloud.com
  SMTP_CLAVE       contrasena de aplicacion (NO la contrasena normal de la cuenta)
  DESTINATARIOS    lista separada por comas o saltos de linea. Cada entrada puede
                   ser "correo@empresa.cl" (todas las regiones) o
                   "correo@empresa.cl|08,13" (solo esas regiones).
  SMTP_SERVIDOR    opcional, por defecto smtp.mail.me.com (iCloud)
  SMTP_PUERTO      opcional, por defecto 587
  PAGINA_URL       opcional, el enlace que se incluye en el correo

Si no hay destinatarios o falta la clave, no envia nada y termina bien: asi el
repositorio funciona aunque todavia no se configuren los secretos.
"""
import json, os, re, smtplib, ssl, sys
from email.message import EmailMessage

CORREO_RE = re.compile(r"^[^\s@,;<>\"]+@[^\s@,;<>\"]+\.[a-zA-Z]{2,}$")

REGIONES = {
    "15": "Arica y Parinacota", "01": "Tarapacá", "02": "Antofagasta", "03": "Atacama",
    "04": "Coquimbo", "05": "Valparaíso", "13": "Metropolitana", "06": "O'Higgins",
    "07": "Maule", "16": "Ñuble", "08": "Biobío", "09": "La Araucanía",
    "14": "Los Ríos", "10": "Los Lagos", "11": "Aysén", "12": "Magallanes",
}

TITULOS = {
    "new": "Nueva alerta",
    "level": "Cambio de nivel",
    "communes": "Cambian las comunas",
    "cancelled": "Alerta cancelada",
}


def destinatarios():
    """Devuelve [(correo, {codigos de region} o None para todas)]."""
    crudo = os.environ.get("DESTINATARIOS", "")
    salida = []
    for linea in re.split(r"[,\n]", crudo):
        linea = linea.strip()
        if not linea:
            continue
        correo, _, regs = linea.partition("|")
        correo = correo.strip()
        if not CORREO_RE.match(correo):
            print("Se ignora una entrada con formato de correo invalido.")
            continue
        codigos = {r.strip().zfill(2) for r in regs.split(";") if r.strip()} if regs.strip() else None
        salida.append((correo, codigos))
    return salida


def para(cambio):
    """Regiones de un cambio, como conjunto de codigos."""
    return {str(r).zfill(2) for r in cambio.get("regions", [])}


def asunto(cambios):
    rojas = [c for c in cambios if c.get("level") == "Roja" and c.get("kind") != "cancelled"]
    nuevas = [c for c in cambios if c.get("kind") in ("new", "level")]
    primero = (rojas or nuevas or cambios)[0]
    lugar = (primero.get("communes") or [primero.get("region", "")])[0]
    if rojas:
        return "[ALERTA ROJA] %s · %s" % (primero.get("hazard", "Alerta SENAPRED"), lugar)
    if nuevas and primero.get("level") == "Amarilla":
        return "[ALERTA AMARILLA] %s · %s" % (primero.get("hazard", "Alerta SENAPRED"), lugar)
    return "[Alertas HSEC] Actualización SENAPRED"


def cuerpo(cambios, pagina):
    lineas = ["Cambios en las alertas oficiales de SENAPRED:", ""]
    for c in cambios:
        titulo = TITULOS.get(c.get("kind"), "Actualización")
        if c.get("kind") == "level" and c.get("prevLevel"):
            titulo = "Pasa de Alerta %s a Alerta %s" % (c["prevLevel"], c.get("level", ""))
        comunas = c.get("communes") or []
        texto = ", ".join(comunas[:15]) + (" y %d más" % (len(comunas) - 15) if len(comunas) > 15 else "")
        regs = ", ".join(REGIONES.get(r, r) for r in sorted(para(c)))
        lineas += [
            "- %s" % titulo,
            "  Nivel: Alerta %s" % c.get("level", "—"),
            "  Peligro: %s" % (c.get("hazard") or "—"),
            "  Región: %s" % (c.get("region") or regs or "—"),
            "  Comunas: %s" % (texto or "—"),
            "  Fecha oficial: %s" % (c.get("at") or "—"),
        ]
        if c.get("url"):
            lineas.append("  Ficha oficial: %s" % c["url"])
        lineas.append("")
    lineas += [
        "Revisa a las personas y oficinas afectadas en Alertas HSEC por Comuna:",
        pagina, "",
        "Recibes este aviso porque tu correo está inscrito en Alertas HSEC por Comuna.",
        "Para dejar de recibirlo, responde a este correo pidiendo la baja.",
        "Fuente oficial: https://senapred.cl/alertas/",
    ]
    return "\n".join(lineas)


def main():
    if len(sys.argv) != 2:
        print("Uso: avisar_correo.py <cambios.json>"); sys.exit(2)
    try:
        cambios = json.load(open(sys.argv[1], encoding="utf-8"))
    except Exception:
        cambios = []
    if not cambios:
        print("Sin cambios que avisar."); return

    gente = destinatarios()
    usuario, clave = os.environ.get("SMTP_USUARIO", "").strip(), os.environ.get("SMTP_CLAVE", "")
    if not gente or not usuario or not clave:
        print("Avisos por correo no configurados todavia (faltan DESTINATARIOS, SMTP_USUARIO o SMTP_CLAVE).")
        print("Hubo %d cambio(s) oficial(es); no se envio ningun correo." % len(cambios))
        return

    servidor = os.environ.get("SMTP_SERVIDOR", "smtp.mail.me.com").strip()
    puerto = int(os.environ.get("SMTP_PUERTO", "587"))
    pagina = os.environ.get("PAGINA_URL", "https://senapred.cl/alertas/").strip()

    enviados, omitidos, fallidos = 0, 0, []
    contexto = ssl.create_default_context()
    with smtplib.SMTP(servidor, puerto, timeout=60) as s:
        s.starttls(context=contexto)
        s.login(usuario, clave)
        for correo, codigos in gente:
            suyos = [c for c in cambios if codigos is None or (para(c) & codigos)]
            if not suyos:
                omitidos += 1
                continue
            msg = EmailMessage()
            msg["From"] = usuario
            msg["To"] = correo
            msg["Subject"] = asunto(suyos)
            msg.set_content(cuerpo(suyos, pagina))
            try:
                s.send_message(msg)
                enviados += 1
            except Exception as e:
                fallidos.append("%s (%s)" % (correo, type(e).__name__))
    print("Correos enviados: %d · sin cambios en sus regiones: %d" % (enviados, omitidos))
    if fallidos:
        print("No se pudo enviar a: " + ", ".join(fallidos))


if __name__ == "__main__":
    main()
