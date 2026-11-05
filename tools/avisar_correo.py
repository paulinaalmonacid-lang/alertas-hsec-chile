#!/usr/bin/env python3
"""Envia un aviso por correo cuando SENAPRED declara, cambia o cancela una alerta.

Lee los cambios que detecto el lector (cambios.json) y escribe a cada persona
inscrita, filtrando por las regiones que le interesan.

Uso: python tools/avisar_correo.py cambios.json
     python tools/avisar_correo.py --prueba   (envia un correo de prueba a todos)

Configuracion, toda por variables de entorno (secretos del repositorio):
  SMTP_USUARIO     correo desde el que se envia, p.ej. nombre@icloud.com
  SMTP_CLAVE       contrasena de aplicacion (NO la contrasena normal de la cuenta)
  DESTINATARIOS    uno o varios correos, separados por comas o saltos de linea.
                   Cada entrada puede ser "correo@empresa.cl" (todas las
                   regiones) o "correo@empresa.cl|08,13" para recibir solo
                   esas regiones. Dentro de la lista de regiones sirven tanto
                   la coma como el punto y coma.
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


# Un correo, opcionalmente seguido de "|" y sus regiones. Se busca asi, y no
# cortando por comas, porque la lista de regiones tambien puede llevar comas:
# "ana@empresa.cl, beto@empresa.cl|08,13" son dos entradas, no tres.
ENTRADA_RE = re.compile(r"([^\s,;|<>\"]+@[^\s,;|<>\"]+\.[a-zA-Z]{2,})\s*(?:\|\s*([0-9\s,;]*))?")


def destinatarios():
    """Devuelve [(correo, {codigos de region} o None para todas)]."""
    crudo = os.environ.get("DESTINATARIOS", "")
    salida, vistos = [], set()
    for correo, regs in ENTRADA_RE.findall(crudo):
        correo = correo.strip()
        if not CORREO_RE.match(correo):
            print("Se ignora una entrada con formato de correo invalido.")
            continue
        if correo.lower() in vistos:
            print("Se ignora un correo repetido.")
            continue
        vistos.add(correo.lower())
        codigos = {r.strip().zfill(2) for r in re.split(r"[;,]", regs) if r.strip()} if regs.strip() else None
        salida.append((correo, codigos))
    sobra = ENTRADA_RE.sub("", crudo).strip(" ,;\n\t")
    if sobra:
        print("Hay texto en DESTINATARIOS que no parece un correo y se ignora: %r" % sobra[:60])
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


def tapado(correo):
    """Muestra el correo a medias, para poder revisarlo en el registro publico
    de la tarea sin dejar la direccion completa a la vista."""
    usuario, _, dominio = correo.partition("@")
    return (usuario[:2] + "*" * max(1, len(usuario) - 2)) + "@" + dominio


def cuerpo_prueba(correo, codigos, pagina):
    donde = "todas las regiones" if codigos is None else ", ".join(
        REGIONES.get(r, r) for r in sorted(codigos))
    return "\n".join([
        "Esto es una prueba. No hay ninguna alerta nueva.",
        "",
        "Si estas leyendo este correo, los avisos de Alertas HSEC por Comuna",
        "estan bien configurados y te llegaran cuando SENAPRED declare, suba de",
        "nivel o cancele una Alerta Roja o Amarilla.",
        "",
        "Tu correo: %s" % correo,
        "Regiones que recibes: %s" % donde,
        "",
        "La pagina: %s" % pagina,
        "Fuente oficial: https://senapred.cl/alertas/",
    ])


def main():
    if len(sys.argv) != 2:
        print("Uso: avisar_correo.py <cambios.json> | --prueba"); sys.exit(2)
    prueba = sys.argv[1] == "--prueba"
    if prueba:
        cambios = []
    else:
        try:
            cambios = json.load(open(sys.argv[1], encoding="utf-8"))
        except Exception:
            cambios = []
        if not cambios:
            print("Sin cambios que avisar."); return

    gente = destinatarios()
    if prueba:
        print("Destinatarios configurados: %d" % len(gente))
        for correo, codigos in gente:
            print("  - %s · %s" % (tapado(correo),
                  "todas las regiones" if codigos is None else ",".join(sorted(codigos))))
    usuario, clave = os.environ.get("SMTP_USUARIO", "").strip(), os.environ.get("SMTP_CLAVE", "")
    if not gente or not usuario or not clave:
        falta = [n for n in ("DESTINATARIOS", "SMTP_USUARIO", "SMTP_CLAVE")
                 if not os.environ.get(n, "").strip()]
        print("Avisos por correo no configurados todavia. Falta: %s" % (", ".join(falta) or "revisar el formato de DESTINATARIOS"))
        if not prueba:
            print("Hubo %d cambio(s) oficial(es); no se envio ningun correo." % len(cambios))
        return

    # GitHub Actions entrega las variables que no existen como texto vacio, no
    # como ausentes: por eso no sirve el valor por defecto de os.environ.get.
    def ajuste(nombre, defecto):
        return (os.environ.get(nombre) or "").strip() or defecto

    servidor = ajuste("SMTP_SERVIDOR", "smtp.mail.me.com")
    try:
        puerto = int(ajuste("SMTP_PUERTO", "587"))
    except ValueError:
        print("SMTP_PUERTO no es un numero; se usa 587.")
        puerto = 587
    pagina = ajuste("PAGINA_URL", "https://senapred.cl/alertas/")

    enviados, omitidos, fallidos = 0, 0, []
    contexto = ssl.create_default_context()
    try:
        conexion = smtplib.SMTP(servidor, puerto, timeout=60)
    except Exception as e:
        print("No se pudo conectar a %s:%s (%s)." % (servidor, puerto, type(e).__name__))
        print("Revisa SMTP_SERVIDOR y SMTP_PUERTO en Settings > Secrets and variables > Actions > Variables.")
        sys.exit(1)
    with conexion as s:
        try:
            s.starttls(context=contexto)
        except Exception as e:
            print("El servidor de correo no acepto la conexion segura (%s)." % type(e).__name__)
            print("Revisa SMTP_SERVIDOR y SMTP_PUERTO: para iCloud son smtp.mail.me.com y 587.")
            sys.exit(1)
        try:
            s.login(usuario, clave)
        except smtplib.SMTPAuthenticationError:
            print("El servidor de correo rechazo el usuario o la clave.")
            print("Si usas iCloud, SMTP_CLAVE tiene que ser una contrasena especifica para apps")
            print("(appleid.apple.com > Inicio de sesion y seguridad), no la contrasena de tu cuenta,")
            print("y SMTP_USUARIO tiene que ser la misma direccion que la genero.")
            print("Revisa tambien que no se haya copiado con espacios al principio o al final.")
            sys.exit(1)
        except Exception as e:
            print("No se pudo iniciar sesion en el correo (%s)." % type(e).__name__)
            sys.exit(1)
        for correo, codigos in gente:
            if prueba:
                suyos = None
            else:
                suyos = [c for c in cambios if codigos is None or (para(c) & codigos)]
                if not suyos:
                    omitidos += 1
                    continue
            msg = EmailMessage()
            msg["From"] = usuario
            msg["To"] = correo
            msg["Subject"] = "[Alertas HSEC] Prueba de aviso" if prueba else asunto(suyos)
            msg.set_content(cuerpo_prueba(correo, codigos, pagina) if prueba else cuerpo(suyos, pagina))
            try:
                s.send_message(msg)
                enviados += 1
            except Exception as e:
                fallidos.append("%s (%s)" % (correo, type(e).__name__))
    print(("Correos de prueba enviados: %d" % enviados) if prueba
          else ("Correos enviados: %d · sin cambios en sus regiones: %d" % (enviados, omitidos)))
    if fallidos:
        print("No se pudo enviar a: " + ", ".join(fallidos))


if __name__ == "__main__":
    main()
