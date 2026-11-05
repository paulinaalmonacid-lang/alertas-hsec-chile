# Alertas HSEC por Comuna

Cruza las **Alertas Rojas y Amarillas oficiales de SENAPRED** con la nómina de personas de una empresa, para saber en minutos quién está en una comuna con alerta y poder contactarlo.

Hecho para equipos de HSEC (Salud, Seguridad, Medio Ambiente y Comunidades) en Chile.

## Privacidad

**La nómina nunca sale del navegador.** El archivo Excel, CSV o JSON se lee en el computador de quien lo carga y se borra al cerrar la pestaña. No hay servidor, no hay base de datos y no se envía nada a ninguna parte. En este repositorio no hay —ni puede haber— datos de personas.

Las oficinas y el logo de la empresa se guardan solo en el navegador de cada persona (almacenamiento local).

## Qué hace

- Mapa de Chile por regiones y comunas, con las alertas vigentes y la cantidad de personas expuestas en cada zona.
- Lista de contacto con las personas en comunas con alerta, agrupadas por alerta y con la Roja primero.
- Contacto guiado: una persona a la vez, con teléfono, WhatsApp y correo, y registro de **Está bien / No contesta / Necesita apoyo**.
- Exportación a PDF para imprimir y a Excel, además de copiar para pegar en una planilla.
- Oficinas de la empresa en el mapa, con aviso cuando quedan en una comuna con alerta.
- Manual de uso integrado y recorrido guiado (botón **Ayuda**).

## Cómo se usa

Abre la página, ve a la pestaña **Planilla** y carga un archivo con al menos dos columnas: `Nombre` y `Comuna`. Son opcionales `Teléfono`, `Correo`, `Área` y cualquier otra columna, que aparecerá en la lista y permitirá filtrar.

También acepta JSON:

```json
[
  {"nombre": "Ana Pérez", "comuna": "Puente Alto", "area": "Operaciones",
   "telefono": "+56 9 1234 5678", "correo": "ana.perez@empresa.cl"}
]
```

El manual dentro de la página (**Ayuda → Preparar la nómina**) tiene plantillas listas para copiar.

## Cómo se actualizan las alertas

Una tarea programada de GitHub Actions (`.github/workflows/alertas.yml`) lee el sitio oficial de SENAPRED tres veces al día (07:58, 13:58 y 19:58 de Chile continental) y actualiza `alerts.json` **solo cuando hay un cambio oficial**: una alerta nueva, un cambio de nivel, un cambio de comunas, un boletín nuevo o una cancelación.

Para ejecutarla a mano: pestaña **Actions** → *Actualizar alertas SENAPRED* → **Run workflow**.

El lector está en `tools/senapred_scraper.py`. Reglas que respeta:

- Solo SENAPRED declara alertas. Los avisos de la Dirección Meteorológica (DMC) y el Botón Rojo de CONAF **no** se convierten en alertas.
- Nunca infiere cancelaciones: si una alerta desaparece del listado sin cancelación oficial, se conserva y queda advertida.
- Nunca inventa fechas: usa las que publica SENAPRED.

## Avisos por correo

Cuando la revisión detecta un cambio oficial, escribe a las personas inscritas. El envío lo hace `tools/avisar_correo.py` dentro de la misma tarea automática, así que no depende de ningún servicio externo.

La configuración vive en **Settings → Secrets and variables → Actions**, nunca en el código:

| Secreto | Qué es |
|---|---|
| `SMTP_USUARIO` | El correo desde el que se envía, por ejemplo `nombre@icloud.com` |
| `SMTP_CLAVE` | Una **contraseña de aplicación**, nunca la contraseña normal de la cuenta |
| `DESTINATARIOS` | Los correos que reciben los avisos, separados por comas o saltos de línea |

Para que alguien reciba solo ciertas regiones, se escribe su correo seguido de una barra vertical y los códigos: `persona@empresa.cl|08,13` avisa solo de Biobío y Metropolitana. Sin barra, recibe todas.

Si el correo de salida no es de iCloud, se agregan dos *variables* (no secretos) en la misma pantalla: `SMTP_SERVIDOR` y `SMTP_PUERTO`. Para Gmail son `smtp.gmail.com` y `587`.

Mientras los secretos no existan, la revisión funciona igual: detecta los cambios, los guarda y deja anotado en el registro que no había a quién avisar.

## Publicar los cambios

El sitio se publica con GitHub Pages desde la rama `main`. Cualquier cambio en `index.html` o `alerts.json` queda en línea en un par de minutos.

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `index.html` | La página completa (todo en un archivo) |
| `alerts.json` | Alertas vigentes de SENAPRED |
| `mapdata.json` | Geometría del mapa de Chile |
| `help/` | Capturas que usa el manual |
| `tools/senapred_scraper.py` | Lector del sitio de SENAPRED |
| `tools/comunas_cl.json` | Las 346 comunas con su región y provincia |
| `tools/aplicar_cambios.py` | Decide si hubo cambio oficial y marca la fecha |
| `tools/avisar_correo.py` | Escribe a las personas inscritas cuando hay un cambio |

## Créditos y límites

Cartografía referencial de la **Biblioteca del Congreso Nacional de Chile (BCN)**, vía [react-chile-map](https://www.npmjs.com/package/react-chile-map) (MIT). No apta para precisión geodésica.

Esta herramienta **no declara alertas**: cruza comunas con las alertas oficiales. Confirma siempre en [senapred.cl/alertas](https://senapred.cl/alertas/) antes de tomar decisiones.

## Licencia

MIT — ver [LICENSE](LICENSE).
