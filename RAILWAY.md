# Costeñol en Railway

Esta carpeta está lista para montarse en Railway. El servicio queda con **Serverless (sleep) activado**: cuando
nadie lo usa se duerme solo y no consume recursos; la primera visita lo despierta.

## Archivos que hacen posible el despliegue

| Archivo | Para qué sirve |
|---|---|
| `railway.json` | Orden de arranque (`python app.py --nube`), comprobación de salud (`/api/salud`) y **`"sleepApplication": true`** (Serverless). |
| `Procfile` | Respaldo del comando de arranque. |
| `requirements.txt` | Vacío a propósito (no hay paquetes externos); sirve para que Railway detecte Python. |
| `.python-version` | Versión de Python (3.12). |
| `.gitignore` | Evita subir claves (`ia_config.json`, `.env`) al repositorio. |

## Pasos

1. Suba esta carpeta a un repositorio de **GitHub** (la clave nunca debe subirse; el `.gitignore` ya la excluye).
2. En Railway: **New Project → Deploy from GitHub repo** y elija el repositorio.
3. En el servicio: **Settings → Networking → Generate Domain** para tener la dirección pública.
4. **Variables** (pestaña *Variables* del servicio). Todas son opcionales:

| Variable | Qué hace |
|---|---|
| `ANTHROPIC_API_KEY` | Activa el asistente de IA en la versión en línea. Sin ella el asistente avisa que no está activado. |
| `COSTENOL_MODELO` | Modelo del asistente (por defecto `claude-sonnet-5-5`). |
| `COSTENOL_API_VERSION` | Versión de la API de Anthropic (por defecto `2026-10-21`). |
| `IA_LIMITE_HORA` | Consultas al asistente por persona y por hora (por defecto 30). |
| `IA_LIMITE_DIA` | Consultas al asistente en total por día (por defecto 300): protege su saldo. |
| `ACCESO_USUARIO` y `ACCESO_CLAVE` | Si se definen **las dos**, toda la página pide usuario y contraseña. |
| `COSTENOL_MAX_SESIONES` | Programas en ejecución a la vez (por defecto 30). |

5. Espere a que termine el despliegue y abra el dominio. Listo.

## Serverless (sleep)

`railway.json` ya trae `"sleepApplication": true`. **Pero compruébelo**: Railway marcó *Config as Code* como
obsoleto (los `railway.json` de servicios existentes funcionan hasta el **2026-12-01** y, según su documentación,
los servicios nuevos ya no pueden usarlo). Si en **Settings → Deploy → Serverless** el interruptor no aparece
activado, **actívelo a mano**: *Enable Serverless*.

Cómo decide Railway que se duerma: si el servicio **no envía ningún tráfico saliente durante unos 10 minutos**
(las respuestas a las visitas también cuentan como tráfico saliente). Por eso la versión en línea:

* **no hace "latidos"** ni ninguna tarea en segundo plano (un navegador abierto no lo mantiene despierto);
* no usa base de datos ni conexiones abiertas;
* guarda los programas del usuario en **su navegador** (no en el servidor).

Al despertar, la primera petición puede tardar unos segundos o dar un error 502; la página reintenta sola, y si
carga con un error basta con recargarla.

Qué se pierde al dormirse: solo un programa que estuviera **esperando un dato** en ese momento (hay que volver a
ejecutarlo). Las pestañas y el código siguen en el navegador.

## Diferencias de la versión en línea

* La clave del asistente **se pone en las variables de Railway**; la página no permite cambiarla ni borrarla.
* El asistente tiene límites de uso (variables `IA_LIMITE_*`) para que nadie gaste su saldo.
* El botón **X** de la ventana solo oculta la ventana; no apaga el servidor.
* Exportar a **.jar** necesita un JDK en el servidor; Railway no lo trae, así que esa opción aparece desactivada
  (Python, JavaScript, página web y Java `.java` sí funcionan). Se puede agregar un JDK con la variable
  `RAILPACK_DEPLOY_APT_PACKAGES=default-jdk-headless` (no lo hemos probado; hace el despliegue más pesado).

## Seguridad

* Toda petición que cambie algo debe venir de la misma página (se rechazan otros orígenes).
* La clave de API **solo** se lee de la variable de entorno; nunca se envía al navegador.
* Con `ACCESO_USUARIO`/`ACCESO_CLAVE` puede dejar la página privada (por ejemplo para el profesor y el equipo).
* La comprobación de salud (`/api/salud`) es pública a propósito para que Railway pueda verificar el servicio.

## Probar el modo en línea en su computador

```
python app.py --nube          # escucha en el puerto 8765 (o en el de la variable PORT)
```

Abra `http://127.0.0.1:8765/`. En este modo no se abre el navegador ni el programa se cierra solo.

## Problemas frecuentes

| Síntoma | Qué hacer |
|---|---|
| «Application failed to respond» | Revise que el comando de arranque sea `python app.py --nube` y que el servicio tenga dominio. |
| La primera visita tarda | Es normal después de dormir. |
| El asistente dice que no está activado | Falta la variable `ANTHROPIC_API_KEY` en Railway (y saldo en la cuenta de la API). |
| El asistente dice «límite de uso» | Se alcanzó `IA_LIMITE_HORA` o `IA_LIMITE_DIA`; suba el valor si hace falta. |
| El servicio nunca duerme | Compruebe que Serverless esté activado y que ninguna otra herramienta consulte la página cada pocos minutos (monitores, *uptime checks*). |
