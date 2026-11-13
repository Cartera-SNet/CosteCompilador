#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Costeñol - Compilador

Arranca un servidor que:
  * entrega la interfaz visual (carpeta web/: HTML, CSS y JavaScript);
  * recibe el código, lo compila con las fases en Python (léxica, sintáctica y
    semántica), lo ejecuta y devuelve el resultado en JSON;
  * exporta el programa a otros lenguajes y conecta con el asistente de IA.

Todo el análisis y la ejecución se hacen en Python; el navegador solo dibuja
la interfaz y muestra los resultados. No necesita instalar nada: solo Python.

Dos formas de funcionar:
  * LOCAL (por defecto): solo accesible desde este computador (127.0.0.1). Se
    abre el navegador y el programa se cierra solo al cerrar la ventana. También
    funciona empaquetado en un .exe (construir_exe.bat).
  * NUBE (Railway u otro servicio): se activa con  python app.py --nube  o
    automáticamente si existen variables RAILWAY_*. Escucha en 0.0.0.0 y en el
    puerto de la variable PORT; no abre navegador ni se cierra solo, y no hace
    nada en segundo plano (para que el modo "serverless/sleep" pueda dormirlo).
    Ver RAILWAY.md.
"""

import base64
import hmac
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import costenol_asistente as asistente
import costenol_exportar as exportador
from costenol_compilador import Sesiones, catalogo, compilar, publico

# --- Rutas -----------------------------------------------------------------
# Empaquetado (.exe): los archivos incluidos (web/, ejemplos/) están dentro del
# paquete (sys._MEIPASS) y lo que el usuario guarda (clave de IA, registro de
# errores) va junto al .exe. Como script, todo está en la carpeta del programa.
CONGELADO = bool(getattr(sys, "frozen", False))
BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
DATOS = os.path.dirname(os.path.abspath(sys.executable)) if CONGELADO else os.path.dirname(os.path.abspath(__file__))
CARPETA_WEB = os.path.join(BASE, "web")
CARPETAS_EJEMPLOS = [os.path.join(BASE, "ejemplos")]
if os.path.abspath(DATOS) != os.path.abspath(BASE):
    CARPETAS_EJEMPLOS.append(os.path.join(DATOS, "ejemplos"))
CONFIG_IA = asistente.Configuracion(os.path.join(DATOS, "ia_config.json"))

PUERTO_PREFERIDO = 8765
MAXIMO_CUERPO = 4_000_000          # bytes aceptados por petición
ESPERA_PRIMER_LATIDO = 120         # s (modo local): si la ventana nunca se abre, el programa se cierra
TIEMPO_CONEXION = 60               # s: una conexión inactiva se cierra

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/manifest+json", ".webmanifest")

POLITICA_CONTENIDO = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                      "img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
                      "form-action 'none'; frame-ancestors 'none'")


def es_nube(argv=None):
    argv = sys.argv if argv is None else argv
    return ("--nube" in argv or os.environ.get("COSTENOL_NUBE") == "1"
            or any(k in os.environ for k in ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME",
                                             "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID")))


def _entero_env(nombre, defecto):
    try:
        return max(1, int(os.environ.get(nombre, defecto)))
    except ValueError:
        return defecto


class Limitador:
    """Límite de uso del asistente de IA en la nube (protege el saldo de la API)."""

    def __init__(self):
        self.por_ip = {}
        self.dia = []
        self.cerrojo = threading.Lock()

    def permitir(self, ip, por_hora, por_dia, ahora=None):
        ahora = time.time() if ahora is None else ahora
        with self.cerrojo:
            self.dia = [t for t in self.dia if ahora - t < 86400]
            if len(self.dia) >= por_dia:
                return False, "El asistente alcanzó su límite de uso de hoy. Intente de nuevo mañana."
            golpes = [t for t in self.por_ip.get(ip, []) if ahora - t < 3600]
            if len(golpes) >= por_hora:
                return False, "Hizo demasiadas consultas al asistente en la última hora. Espere un rato e intente de nuevo."
            golpes.append(ahora)
            self.por_ip[ip] = golpes
            self.dia.append(ahora)
            if len(self.por_ip) > 5000:                      # evita que la tabla crezca sin límite
                for k in [k for k, v in self.por_ip.items() if not v or ahora - v[-1] > 3600]:
                    del self.por_ip[k]
            return True, ""


class Estado:
    servidor = None
    ultimo_latido = time.time()
    hubo_latido = False
    sesiones = Sesiones()
    nube = es_nube()
    limitador = Limitador()


def registrar_error(texto):
    """Guarda un error inesperado en costenol_error.log (junto al programa)."""
    try:
        with open(os.path.join(DATOS, "costenol_error.log"), "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {texto}\n")
    except OSError:
        pass                                                # en la nube el disco puede ser de solo escritura temporal


def cargar_ejemplos():
    """Lee los programas de las carpetas ejemplos/. La primera línea de cada
    archivo debe ser un comentario:  // Ejemplo: Título //"""
    por_nombre = {}
    for carpeta in CARPETAS_EJEMPLOS:
        try:
            nombres = [n for n in os.listdir(carpeta) if n.lower().endswith(".cst")]
        except OSError:
            continue
        for nombre in nombres:
            try:
                with open(os.path.join(carpeta, nombre), "r", encoding="utf-8-sig") as f:
                    por_nombre[nombre] = f.read()
            except OSError:
                continue
    lista = []
    for nombre in sorted(por_nombre):
        codigo = por_nombre[nombre]
        primera = codigo.splitlines()[0] if codigo else ""
        titulo = nombre
        if primera.startswith("//") and "Ejemplo:" in primera:
            titulo = primera.split("Ejemplo:", 1)[1].strip().rstrip("/").strip()
        lista.append({"archivo": nombre, "titulo": titulo, "codigo": codigo})
    return lista


RUTAS_CON_JSON = ("/api/analizar", "/api/ejecutar", "/api/entrada", "/api/detener",
                  "/api/ia/config", "/api/asistente", "/api/exportar")


class Manejador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Costenol"
    timeout = TIEMPO_CONEXION

    def log_message(self, *args):          # sin ruido en la consola
        pass

    # -- utilidades ------------------------------------------------------------
    def _enviar(self, codigo, tipo, datos: bytes, extra=None):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", POLITICA_CONTENIDO)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(datos)

    def _json(self, objeto, codigo=200, extra=None):
        datos = json.dumps(objeto, ensure_ascii=False).encode("utf-8")
        self._enviar(codigo, "application/json; charset=utf-8", datos, extra)

    def _ip(self):
        xff = self.headers.get("X-Forwarded-For", "")
        return xff.split(",")[0].strip() if xff else self.client_address[0]

    # -- seguridad ---------------------------------------------------------------
    def _autorizado(self):
        usuario, clave = os.environ.get("ACCESO_USUARIO"), os.environ.get("ACCESO_CLAVE")
        if not (usuario and clave):
            return True
        cab = self.headers.get("Authorization", "")
        if not cab.startswith("Basic "):
            return False
        try:
            u, _, c = base64.b64decode(cab[6:]).decode("utf-8").partition(":")
        except Exception:
            return False
        return hmac.compare_digest(u.encode(), usuario.encode()) and hmac.compare_digest(c.encode(), clave.encode())

    def _host_valido(self):
        """En modo local solo se atiende a 127.0.0.1 / localhost (evita ataques de 'DNS rebinding')."""
        if Estado.nube:
            return True
        puerto = self.server.server_address[1]
        return (self.headers.get("Host") or "").lower() in (f"127.0.0.1:{puerto}", f"localhost:{puerto}")

    def _origen_valido(self):
        """Una página de otro sitio no puede mandar peticiones a este servidor."""
        origen = self.headers.get("Origin")
        if origen is None:
            return True                                     # herramientas que no son navegadores
        if origen == "null":
            return False
        destino = urlparse(origen).netloc
        return destino in (self.headers.get("Host", ""), self.headers.get("X-Forwarded-Host", ""))

    def _puerta(self):
        """Devuelve True si la petición puede continuar (si no, ya respondió)."""
        if not self._host_valido():
            self._json({"error": "Dirección no permitida."}, 403)
            return False
        if not self._autorizado():
            self._json({"error": "Se necesita usuario y contraseña."}, 401,
                       {"WWW-Authenticate": 'Basic realm="Costeñol", charset="UTF-8"'})
            return False
        return True

    # -- GET ---------------------------------------------------------------------
    def do_GET(self):
        try:
            ruta = unquote(urlparse(self.path).path)
            if ruta == "/api/salud":                        # para la comprobación de salud del servicio
                return self._json({"ok": True})
            if not self._puerta():
                return
            if ruta == "/api/modo":
                return self._json({"nube": Estado.nube})
            if ruta == "/api/ejemplos":
                return self._json(cargar_ejemplos())
            if ruta == "/api/catalogo":
                return self._json(catalogo())
            if ruta == "/api/ia/estado":
                e = CONFIG_IA.estado()
                e["configurable"] = not Estado.nube
                return self._json(e)
            if ruta == "/api/exportar/formatos":
                return self._json(exportador.formatos())
            if ruta in ("/", ""):
                ruta = "/index.html"
            absoluta = os.path.normpath(os.path.join(CARPETA_WEB, ruta.lstrip("/")))
            if not absoluta.startswith(os.path.normpath(CARPETA_WEB) + os.sep) or not os.path.isfile(absoluta):
                return self._enviar(404, "text/plain; charset=utf-8", "No encontrado".encode())
            tipo = mimetypes.guess_type(absoluta)[0] or "application/octet-stream"
            if tipo.startswith("text/") or tipo in ("application/javascript", "image/svg+xml"):
                tipo += "; charset=utf-8" if "charset" not in tipo else ""
            with open(absoluta, "rb") as f:
                self._enviar(200, tipo, f.read())
        except Exception as exc:
            registrar_error(traceback.format_exc())
            self._json({"error": f"Error interno: {exc}"}, 500)

    do_HEAD = do_GET

    # -- POST --------------------------------------------------------------------
    def do_POST(self):
        try:
            ruta = urlparse(self.path).path
            if not self._puerta():
                return
            if not self._origen_valido():
                return self._json({"error": "Origen no permitido."}, 403)
            largo = int(self.headers.get("Content-Length") or 0)
            if largo > MAXIMO_CUERPO:
                self.close_connection = True      # no se lee el cuerpo: se cierra la conexión
                return self._json({"error": "El contenido es demasiado grande."}, 413)
            cuerpo = self.rfile.read(largo) if largo else b""

            datos = {}
            if ruta in RUTAS_CON_JSON:
                try:
                    datos = json.loads(cuerpo.decode("utf-8"))
                    if not isinstance(datos, dict):
                        raise ValueError
                except (ValueError, RecursionError):
                    return self._json({"error": "Petición inválida."}, 400)

            if ruta == "/api/analizar":
                codigo = datos.get("codigo", "")
                if not isinstance(codigo, str):
                    return self._json({"error": "El código debe ser texto."}, 400)
                return self._json(publico(compilar(codigo)))

            if ruta == "/api/ejecutar":
                codigo = datos.get("codigo", "")
                if not isinstance(codigo, str):
                    return self._json({"error": "El código debe ser texto."}, 400)
                comp = compilar(codigo)
                if not comp["exitoso"]:
                    return self._json({"compilacion": publico(comp), "sesion": None, "salida": [],
                                       "espera": None, "terminado": True, "error": None})
                sid, sesion = Estado.sesiones.crear(comp["arbol"])
                r = sesion.iniciar()
                if r["terminado"]:
                    Estado.sesiones.cerrar(sid)
                    sid = None
                r.update({"compilacion": publico(comp), "sesion": sid})
                return self._json(r)

            if ruta == "/api/entrada":
                sid, valor = datos.get("sesion"), datos.get("valor", "")
                if not isinstance(sid, str) or not isinstance(valor, str):
                    return self._json({"error": "Petición inválida."}, 400)
                sesion = Estado.sesiones.obtener(sid)
                if sesion is None:
                    return self._json({"error": "La ejecución ya terminó o expiró. Vuelva a ejecutar."}, 404)
                r = sesion.entregar(valor)
                if r["terminado"]:
                    Estado.sesiones.cerrar(sid)
                return self._json(r)

            if ruta == "/api/detener":
                sid = datos.get("sesion")
                if isinstance(sid, str):
                    Estado.sesiones.cerrar(sid)
                return self._json({"ok": True})

            # -- exportar --------------------------------------------------------
            if ruta == "/api/exportar":
                codigo, formato, nombre = datos.get("codigo", ""), datos.get("formato"), datos.get("nombre")
                if not isinstance(codigo, str) or not isinstance(formato, str) or (nombre is not None and not isinstance(nombre, str)):
                    return self._json({"error": "Petición inválida."}, 400)
                comp = compilar(codigo)
                if not comp["exitoso"]:
                    return self._json({"error": "El programa tiene errores: corríjalos antes de exportar.",
                                       "errores": comp["errores"][:10]}, 422)
                try:
                    r = exportador.exportar(comp["arbol"], formato, nombre)
                except exportador.ErrorExportacion as e:
                    return self._json({"error": e.mensaje}, e.estado)
                return self._json({"archivo": r["archivo"], "mime": r["mime"], "como": r["como"],
                                   "base64": base64.b64encode(r["contenido"]).decode("ascii")})

            # -- asistente de IA ------------------------------------------------
            if ruta in ("/api/ia/config", "/api/ia/borrar"):
                if Estado.nube:
                    return self._json({"error": "En la versión en línea la clave del asistente se configura en el "
                                                "servidor (variable ANTHROPIC_API_KEY), no desde la página."}, 403)
                if ruta == "/api/ia/borrar":
                    try:
                        CONFIG_IA.borrar_clave()
                    except asistente.ErrorAsistente as e:
                        return self._json({"error": e.mensaje}, e.estado)
                    return self._json(CONFIG_IA.estado())
                try:
                    clave, modelo = datos.get("clave"), datos.get("modelo")
                    if (clave is not None and not isinstance(clave, str)) or (modelo is not None and not isinstance(modelo, str)):
                        return self._json({"error": "Petición inválida."}, 400)
                    CONFIG_IA.guardar(clave=clave, modelo=modelo)
                except asistente.ErrorAsistente as e:
                    return self._json({"error": e.mensaje}, e.estado)
                return self._json(CONFIG_IA.estado())

            if ruta == "/api/asistente":
                if Estado.nube:
                    ok, motivo = Estado.limitador.permitir(self._ip(), _entero_env("IA_LIMITE_HORA", 30),
                                                           _entero_env("IA_LIMITE_DIA", 300))
                    if not ok:
                        return self._json({"error": motivo}, 429)
                try:
                    r = asistente.responder(CONFIG_IA, datos.get("mensajes"), datos.get("codigo"), datos.get("errores"))
                except asistente.ErrorAsistente as e:
                    return self._json({"error": e.mensaje}, e.estado)
                return self._json(r)

            # -- control de la ventana (solo modo local) -------------------------------
            if ruta == "/api/latido":
                Estado.ultimo_latido = time.time()
                Estado.hubo_latido = True
                return self._json({"ok": True})

            if ruta == "/api/cerrar":
                if not Estado.nube:
                    momento = time.time()
                    # Si la página se recarga llega un latido nuevo y no se cierra.
                    threading.Timer(4.0, apagar_si_no_hay_latidos, args=(momento,)).start()
                return self._json({"ok": True})

            self._json({"error": "Ruta desconocida."}, 404)
        except Exception as exc:
            registrar_error(traceback.format_exc())
            try:
                self._json({"error": f"Error interno: {exc}"}, 500)
            except Exception:
                pass


def apagar_si_no_hay_latidos(desde):
    if not Estado.nube and Estado.ultimo_latido < desde and Estado.servidor is not None:
        print("\nVentana cerrada. Cerrando el compilador...")
        Estado.servidor.shutdown()


def apagar_si_nunca_se_abrio():
    if not Estado.nube and not Estado.hubo_latido and Estado.servidor is not None:
        Estado.servidor.shutdown()


def vigilar_ventana():
    """Solo en el .exe (que no tiene consola): si hace mucho que ninguna ventana
    avisa que sigue abierta, el programa se cierra para no quedar escondido."""
    while Estado.servidor is not None:
        time.sleep(30)
        if Estado.hubo_latido and time.time() - Estado.ultimo_latido > 1200:
            Estado.servidor.shutdown()
            return


def crear_servidor():
    if Estado.nube:
        puerto = _entero_env("PORT", PUERTO_PREFERIDO)
        return ThreadingHTTPServer(("0.0.0.0", puerto), Manejador)
    for puerto in (PUERTO_PREFERIDO, 0):
        try:
            return ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
        except OSError:
            continue
    raise RuntimeError("No se pudo abrir un puerto local para el compilador.")


def main():
    if not os.path.isfile(os.path.join(CARPETA_WEB, "index.html")):
        print("No se encontró la carpeta web/. Verifique que descomprimió el .zip completo.", flush=True)
        return 1

    servidor = crear_servidor()
    servidor.daemon_threads = True
    Estado.servidor = servidor
    puerto = servidor.server_address[1]

    if Estado.nube:
        # Mensajes mínimos para los registros del servicio. Nada más se hace en segundo plano.
        print(f"Costeñol en línea: escuchando en el puerto {puerto} (modo nube).", flush=True)
        if os.environ.get("ACCESO_USUARIO") and os.environ.get("ACCESO_CLAVE"):
            print("Acceso protegido con usuario y contraseña.", flush=True)
    else:
        url = f"http://127.0.0.1:{puerto}/"
        print("=" * 60)
        print("  Compilador Costeñol")
        print("=" * 60)
        print(f"  Dirección: {url}")
        print("  Se abrirá en su navegador. Para salir, cierre la ventana")
        print("  del compilador o presione Ctrl+C en esta consola.")
        print("=" * 60)
        if "--sin-navegador" not in sys.argv:
            threading.Timer(0.6, lambda: webbrowser.open(url)).start()
            t = threading.Timer(ESPERA_PRIMER_LATIDO, apagar_si_nunca_se_abrio)
            t.daemon = True
            t.start()
            if CONGELADO:
                threading.Thread(target=vigilar_ventana, daemon=True).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando el compilador...")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        registrar_error(traceback.format_exc())
        raise
