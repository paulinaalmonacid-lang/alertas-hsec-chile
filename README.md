# Alertas HSEC por Comuna

Cruza las **Alertas Rojas y Amarillas oficiales de SENAPRED** con la nómina de personas de una empresa, para saber en minutos quién está en una comuna con alerta y poder contactarlo. Muestra además los **sismos recientes** con la gente que quedó cerca del epicentro y el **clima** de cualquier comuna.

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

Una tarea programada de GitHub Actions (`.github/workflows/alertas.yml`) lee el sitio oficial de SENAPRED cada tres horas (01:23, 04:23, 07:23… hora de Chile continental) y actualiza `alerts.json` **solo cuando hay un cambio oficial**: una alerta nueva, un cambio de nivel, un cambio de comunas, un boletín nuevo o una cancelación.

Para ejecutarla a mano: pestaña **Actions** → *Actualizar alertas SENAPRED* → **Run workflow**.

El lector está en `tools/senapred_scraper.py`. Reglas que respeta:

- Solo SENAPRED declara alertas. Los avisos de la Dirección Meteorológica (DMC) y el Botón Rojo de CONAF **no** se convierten en alertas.
- Nunca infiere cancelaciones: si una alerta desaparece del listado sin cancelación oficial, se conserva y queda advertida.
- Nunca inventa fechas: usa las que publica SENAPRED.

## Avisos preventivos

Además de las Alertas Amarillas y Rojas, la página muestra aparte las **Alertas Tempranas Preventivas** que declara SENAPRED. Son avisos previos —muchos por pronósticos de la Dirección Meteorológica o riesgo de incendio— que suelen anticipar una alerta formal.

Nunca se mezclan con las alertas: no cuentan como personas expuestas, no pintan el mapa ni entran en la lista de contacto. Viven en `alerts.json` bajo `preventive` y se consideran vigentes mientras el último estado publicado siga declarándolas y no pasen 30 días.

> GitHub atrasa las tareas programadas cuando tiene carga, y a veces se salta alguna: no hay garantía de que corran a la hora exacta. Por eso hay ocho horarios al día en vez de los tres del principio, con los que llegaron a pasar diecinueve horas entre una revisión y la siguiente.

## Sismos y clima

Dos fuentes que **no** son SENAPRED y que la página pide directamente desde el navegador de quien la abre, sin pasar por este repositorio:

- **Sismos**, del [USGS](https://earthquake.usgs.gov/fdsnws/event/1/) (servicio geológico de Estados Unidos), que publica los eventos en abierto y al instante. Se muestran los últimos 7 días desde magnitud 4 dentro de Chile. Para cada sismo se calculan las comunas dentro de un radio referencial según la magnitud (50 km bajo M4,5; 100, 150, 250 y 400 km hacia arriba) y, si hay nómina cargada, cuántas personas viven o trabajan ahí. **El radio no mide daño**: sirve para ver a quién se tiene cerca del epicentro mientras SENAPRED todavía no declara nada.
- **Clima**, de [Open-Meteo](https://open-meteo.com/): condiciones actuales y pronóstico de 7 días para la comuna que se busque, más un aviso si esa comuna tiene alerta vigente. Referencial; lo oficial es la [Dirección Meteorológica de Chile](https://www.meteochile.gob.cl/).

Las coordenadas de las 343 comunas del mapa están en `comunas_geo.json` y van embebidas en la página, así que el cálculo de cercanía funciona sin conexión.

## Historial por comuna

`tools/historial.py` va anotando en `historial.json`, cada vez que cambia el listado, qué comuna estuvo bajo qué alerta y entre qué fechas. Un cambio de nivel cierra un tramo y abre otro, así que queda registrado "estuvo Amarilla y pasó a Roja". Al tocar una comuna en el mapa, la página muestra ese historial.

Empieza el 04-11-2026, que es cuando este repositorio guardó la primera lectura: no hay datos anteriores a esa fecha.

## Avisos por correo

Cuando la revisión detecta un cambio oficial, escribe a las personas inscritas. El envío lo hace `tools/avisar_correo.py` dentro de la misma tarea automática, así que no depende de ningún servicio externo.

La configuración vive en **Settings → Secrets and variables → Actions**, nunca en el código:

| Secreto | Qué es |
|---|---|
| `SMTP_USUARIO` | El correo desde el que se envía, por ejemplo `nombre@icloud.com` |
| `SMTP_CLAVE` | Una **contraseña de aplicación**, nunca la contraseña normal de la cuenta |
| `DESTINATARIOS` | Los correos que reciben los avisos, separados por comas o saltos de línea |

Para que alguien reciba solo ciertas regiones, se escribe su correo seguido de una barra vertical y los códigos: `persona@empresa.cl|08,13` avisa solo de Biobío y Metropolitana. Sin barra, recibe todas. Varios correos van separados por coma o por salto de línea:

```
paulina@empresa.cl
jefatura@empresa.cl|08,13
```

**Para probar que llegan:** pestaña **Actions** → *Actualizar alertas SENAPRED* → **Run workflow**, marcar *Enviar un correo de prueba* y ejecutar. Manda un correo de prueba a cada destinatario sin tocar SENAPRED, y en el registro de la tarea queda cuántos destinatarios hay y con qué regiones, con las direcciones tapadas a medias.

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
| `comunas_geo.json` | Latitud y longitud de las 343 comunas del mapa (sismos) |
| `historial.json` | Qué comuna estuvo bajo qué alerta y entre qué fechas |
| `tools/historial.py` | Va completando ese historial en cada lectura |
| `tools/aplicar_cambios.py` | Decide si hubo cambio oficial y marca la fecha |
| `tools/avisar_correo.py` | Escribe a las personas inscritas cuando hay un cambio |

## Créditos y límites

Cartografía referencial de la **Biblioteca del Congreso Nacional de Chile (BCN)**, vía [react-chile-map](https://www.npmjs.com/package/react-chile-map) (MIT). No apta para precisión geodésica.

Esta herramienta **no declara alertas**: cruza comunas con las alertas oficiales. Confirma siempre en [senapred.cl/alertas](https://senapred.cl/alertas/) antes de tomar decisiones.

## Licencia

MIT — ver [LICENSE](LICENSE).
