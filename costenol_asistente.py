# -*- coding: utf-8 -*-
"""
Costeñol - Asistente de IA

Responde preguntas sobre el compilador y escribe programas en Costeñol usando
la API de Anthropic (Claude). Solo usa la biblioteca estándar de Python.

Lo que lo hace confiable:
  * Recibe como instrucciones TODAS las reglas del lenguaje.
  * Todo código que escribe se COMPILA con el compilador real. Si tiene
    errores, se le devuelven al modelo para que los corrija (hasta 2 veces).
  * La respuesta indica, bloque por bloque, si el código compila o no.

La clave de API nunca sale de este computador: se guarda en ia_config.json
(junto al programa) o se lee de la variable de entorno ANTHROPIC_API_KEY, y
solo se envía a api.anthropic.com. Nunca se manda a la página web.
"""

import json
import os
import re
import urllib.error
import urllib.request

from costenol_compilador import compilar

MODELO_PREDETERMINADO = "claude-sonnet-5-5"
URL_PREDETERMINADA = "https://api.anthropic.com/v1/messages"
VERSION_API = os.environ.get("COSTENOL_API_VERSION", "").strip() or "2026-10-21"
MAX_TOKENS = 2000
TIEMPO_ESPERA = 90               # segundos
MAX_REINTENTOS = 2               # correcciones automáticas del código
MAX_TURNOS = 12                  # mensajes anteriores que se envían
MAX_CHARS_MENSAJE = 4000
MAX_CHARS_CODIGO = 8000
MAX_ERRORES_CONTEXTO = 20

INSTRUCCIONES = """\
Eres el asistente integrado del compilador de Costeñol. Costeñol es un lenguaje de programación educativo, con instrucciones en español, creado para el curso de Compiladores. Ayudas a las personas a escribir programas en Costeñol y respondes preguntas sobre el lenguaje y sobre el compilador (sus pantallas, sus fases y sus mensajes de error). Si te preguntan algo que no tiene que ver con Costeñol ni con el compilador, di amablemente que solo puedes ayudar con eso.

=== REGLAS DEL LENGUAJE (nunca las incumplas) ===
ESCRITURA
- Las mayúsculas y minúsculas importan. Palabras reservadas, escritas exactamente así y SIN tilde: Entero Texto Real Logico Captura Mensaje Si Sino FinSi Verdadero Falso.
- Cada instrucción simple termina en punto y coma ;  Las líneas "Si (...)", "Sino" y "FinSi" NO llevan punto y coma.
- Los decimales se escriben con COMA: 3,1416 (nunca con punto).
- Los textos van entre comillas dobles "así", en una sola línea. Pueden llevar tildes y ñ.
- Comentarios: se escriben entre dos // en la misma línea:  // esto es un comentario //
- Nombres de variables: empiezan con letra; después letras SIN tilde (la ñ sí se acepta), dígitos o guion bajo; máximo 30 caracteres. Distinguen mayúsculas (edad y Edad son distintas). Usa nombres como anioNacimiento, nunca añoNacimiento con tilde.
- Una variable NO puede llamarse como un tipo de dato ni como ninguna palabra reservada, ni siquiera cambiando mayúsculas o minúsculas: "entero Entero;", "texto Texto;", "si = 5;" son errores. Sí valen nombres que solo CONTIENEN la palabra, como miEntero, enteros o textoLargo.
TIPOS
- Entero (sin decimales, de -2147483647 a 2147483647), Real (con decimales), Texto, Logico (Verdadero o Falso).
VARIABLES
- Se declaran antes de usarlas, una sola vez y fuera de los Si, así:  nombre Tipo;   Ejemplo: edad Entero;
- Se asigna con =:  edad = 20;   suma = a + (b * c);   nombre = "Ana";
- Una variable solo guarda valores de su tipo. La única conversión automática: un Entero se puede guardar en un Real.
- Una variable debe tener valor (asignado o leído con Captura) antes de usarse.
LEER Y MOSTRAR
- Leer un dato: variable = Captura.Tipo();  con Tipo = Texto, Entero, Real o Logico, igual al tipo de la variable. Captura solo se usa así, nunca dentro de operaciones.
- El compilador NO muestra ningún texto por sí solo al pedir un dato: para avisar qué debe escribir el usuario, usa Mensaje.Texto("...") justo antes de Captura.
- Mostrar: Mensaje.Texto(valor);  El valor puede ser un texto, un número, una variable o una operación. Cada Mensaje baja de línea. Mensaje.Texto(""); muestra una línea en blanco.
- Con + se unen textos, y si un lado es Texto el otro se convierte a texto:  Mensaje.Texto("Tu edad es: " + edad + " años");
OPERACIONES
- Entre dos valores siempre va un operador: un paréntesis NO puede ir pegado a un número ("2(3 + 4)" es un error; se escribe "2 * (3 + 4)"). Todo "(" debe cerrarse.
- Aritméticas: + - * /  (con paréntesis). La división / SIEMPRE da Real, así que se guarda en una variable Real (no en Entero). Dividir por cero da error.
- Comparaciones (dan Logico): == != < > <= >=  Para Texto y Logico solo existen == y !=; < > <= >= son solo para números.
- No existen los operadores lógicos Y, O, No, ni el módulo %.
CONDICIONALES
- Forma exacta (un espacio entre Si y el paréntesis; Sino y FinSi solos en su línea):
    Si (condicion)
        instrucciones
    Sino
        instrucciones
    FinSi
- Sino es opcional (máximo uno por Si). Todo Si termina con FinSi. Se pueden anidar. La condición debe ser Logico (por ejemplo edad >= 18).
- Dentro de un Si se compara con ==, nunca con un solo =.
LO QUE NO EXISTE (dilo claramente si lo piden y ofrece la alternativa más cercana): ciclos (para, mientras, repetir), listas o arreglos, funciones propias, operadores Y/O/No, módulo, números aleatorios, fechas, comentarios de varias líneas, imprimir con otra instrucción distinta de Mensaje.Texto.

=== SOBRE EL COMPILADOR (para responder preguntas) ===
- El compilador es una ventana con un editor (pestañas con +), una pantalla negra "Salida del Programa" y paneles de resultados: Mensajes, Errores, Advertencias, Reporte (los tokens), Árbol Sintáctico y Tabla de Símbolos.
- Botones: Nuevo, Abrir, Guardar, Compilar (F7: solo revisa), Ejecutar (F5 o Ctrl+Enter: revisa y corre el programa), Exportar y Configuración. En la barra lateral: Ejemplos, Analizador, Asistente IA y Manual de uso (con todas las reglas y el catálogo de errores).
- Revisa el programa en tres fases, una después de otra (si una falla, las siguientes no se ejecutan): análisis léxico (palabras y símbolos válidos), sintáctico (orden correcto) y semántico (tipos y variables). Si pasa las tres, se ejecuta. Los errores tienen un código como E-SIN-01 y muestran línea y columna; al hacer clic en un error se va a esa línea.
- Exportar convierte un programa SIN errores en un archivo que se ejecuta solo: Python (.py), JavaScript (.js, con Node.js), página web (.html, doble clic), Java (.java para compilar con javac) o Java ejecutable (.jar, que necesita un JDK instalado para construirse). El navegador pregunta en qué carpeta guardarlo.
- Al ejecutar, un Captura abre una casilla en la pantalla negra; Enter envía el dato y Esc detiene el programa.
- El editor tiene autocompletado: al escribir sugiere en gris (Mensaje.Texto, Captura.Tipo(), Si … FinSi, tipos de dato, variables ya declaradas) y la tecla Tab completa; Esc lo cierra; se puede desactivar en Configuración.
- Los mensajes de error y advertencia salen en costeño con el formato "<saludo> en la línea N. Error <léxico|sintáctico|semántico|de ejecución>: <causa>"; en Configuración se pueden cambiar a español formal. El botón "Limpiar código" borra el código de la pestaña (Ctrl+Z lo recupera).
- Si no sabes algo del compilador que no esté aquí, dilo; no lo inventes.

=== CÓMO RESPONDER ===
- Responde siempre en español, de forma clara, amable y breve, pensando en principiantes.
- Cuando pidan código, entrega un programa COMPLETO en un solo bloque de código con triple acento grave (```) y sin indicar nombre de lenguaje, listo para pegar en el editor. Empieza el programa con un comentario // ... // que diga qué hace. Antes o después del bloque, explica en 2 a 4 líneas qué hace.
- El código de los bloques debe compilar sin errores con las reglas de arriba. Si necesitas mostrar un ejemplo INCORRECTO, escríbelo en línea con comillas invertidas simples (`así`), nunca en un bloque.
- Si te dan el código del usuario y sus errores, explica en pocas palabras qué falla y entrega el programa corregido.
- Si preguntan cómo se hace algo del lenguaje (por ejemplo declarar enteros), responde con la regla y un ejemplo corto.
- No inventes instrucciones que no estén en las reglas.

=== EJEMPLO DE UN PROGRAMA CORRECTO ===
```
// Calcula la edad a partir del año de nacimiento //
anioNacimiento Entero;
anioActual Entero;
edad Entero;

anioActual = 2026;

Mensaje.Texto("Ingrese su año de nacimiento:");
anioNacimiento = Captura.Entero();

edad = anioActual - anioNacimiento;

Mensaje.Texto("Tu edad es: " + edad + " años");
```
"""


class ErrorAsistente(Exception):
    def __init__(self, mensaje, estado=500):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado = estado


# ---------------------------------------------------------------------------
# Configuración (clave y modelo)
# ---------------------------------------------------------------------------

class Configuracion:
    def __init__(self, ruta):
        self.ruta = ruta

    def _leer(self):
        try:
            with open(self.ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            return datos if isinstance(datos, dict) else {}
        except (OSError, ValueError):
            return {}

    def clave(self):
        c = self._leer().get("clave")
        if isinstance(c, str) and c.strip():
            return c.strip(), "archivo"
        c = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if c:
            return c, "variable"
        return None, None

    def modelo(self):
        m = self._leer().get("modelo")
        if isinstance(m, str) and m.strip():
            return m.strip()
        return os.environ.get("COSTENOL_MODELO", "").strip() or MODELO_PREDETERMINADO

    def estado(self):
        clave, origen = self.clave()
        return {
            "configurada": clave is not None,
            "origen": origen,
            "sufijo": ("…" + clave[-4:]) if clave and len(clave) >= 8 else None,
            "modelo": self.modelo(),
        }

    def guardar(self, clave=None, modelo=None):
        datos = self._leer()
        if clave is not None:
            clave = clave.strip()
            if clave:
                if not re.fullmatch(r"[A-Za-z0-9_\-\.]{20,300}", clave):
                    raise ErrorAsistente("La clave no tiene el formato esperado. Cópiela completa desde console.anthropic.com.", 400)
                datos["clave"] = clave
        if modelo is not None:
            modelo = modelo.strip()
            if modelo:
                if not re.fullmatch(r"[A-Za-z0-9_\-\.:]{3,80}", modelo):
                    raise ErrorAsistente("El nombre del modelo no es válido.", 400)
                datos["modelo"] = modelo
            else:
                datos.pop("modelo", None)
        self._escribir(datos)

    def borrar_clave(self):
        datos = self._leer()
        datos.pop("clave", None)
        self._escribir(datos)

    def _escribir(self, datos):
        try:
            with open(self.ruta, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(self.ruta, 0o600)
            except OSError:
                pass
        except OSError as exc:
            raise ErrorAsistente(f"No se pudo guardar la configuración ({exc.strerror}).", 500)


# ---------------------------------------------------------------------------
# Código dentro de las respuestas
# ---------------------------------------------------------------------------

_RE_BLOQUE = re.compile(r"```[ \t]*[A-Za-z0-9_+\-]*[ \t]*\r?\n(.*?)```", re.S)


def extraer_bloques(texto):
    return [b.strip("\r\n") for b in _RE_BLOQUE.findall(texto or "")]


def verificar(bloques):
    """Compila cada bloque con el compilador real (sin ejecutarlo)."""
    resultado = []
    for codigo in bloques:
        c = compilar(codigo + "\n")
        resultado.append({
            "codigo": codigo,
            "exitoso": c["exitoso"],
            "errores": [{"linea": e["linea"], "columna": e["columna"], "codigo": e["codigo"],
                         "mensaje": e["mensaje"]} for e in c["errores"][:10]],
        })
    return resultado


def _mensaje_correccion(malos):
    partes = ["El compilador de Costeñol encontró errores en el código que escribiste. "
              "Corrígelos y responde de nuevo: explica brevemente y entrega el programa completo y corregido "
              "en un solo bloque de código.\n"]
    for i, v in enumerate(malos, 1):
        partes.append(f"Bloque {i}:")
        for e in v["errores"]:
            partes.append(f"- Línea {e['linea']}, columna {e['columna']} [{e['codigo']}]: {e['mensaje']}")
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# Llamada a la API
# ---------------------------------------------------------------------------

def _url():
    return os.environ.get("COSTENOL_API_URL", "").strip() or URL_PREDETERMINADA


def _llamar_api(clave, modelo, sistema, mensajes):
    cuerpo = json.dumps({
        "model": modelo,
        "max_tokens": MAX_TOKENS,
        "system": sistema,
        "messages": mensajes,
    }).encode("utf-8")
    req = urllib.request.Request(_url(), data=cuerpo, method="POST", headers={
        "content-type": "application/json",
        "x-api-key": clave,
        "anthropic-version": VERSION_API,
    })
    try:
        with urllib.request.urlopen(req, timeout=TIEMPO_ESPERA) as r:
            datos = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detalle = ""
        try:
            detalle = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        raise ErrorAsistente(_mensaje_http(e.code, detalle, modelo), 502)
    except urllib.error.URLError:
        raise ErrorAsistente("No se pudo conectar con el servicio de IA. Revise su conexión a internet.", 502)
    except TimeoutError:
        raise ErrorAsistente("El servicio de IA tardó demasiado en responder. Intente de nuevo.", 504)
    except (OSError, ValueError):
        raise ErrorAsistente("No se pudo leer la respuesta del servicio de IA.", 502)

    texto = "".join(b.get("text", "") for b in datos.get("content", []) if isinstance(b, dict) and b.get("type") == "text")
    if not texto.strip():
        raise ErrorAsistente("El asistente no devolvió ninguna respuesta. Intente de nuevo.", 502)
    return texto


def _mensaje_http(codigo, detalle, modelo):
    if codigo == 401:
        return "La clave de API no es válida o fue revocada. Revísela en la configuración del asistente."
    if codigo == 403:
        return "La clave de API no tiene permiso para usar este servicio."
    if codigo == 404:
        return f"El modelo «{modelo}» no existe o su clave no tiene acceso. Cámbielo en la configuración del asistente."
    if codigo == 400 and "credit" in detalle.lower():
        return "La cuenta de la API no tiene saldo. Agregue crédito en console.anthropic.com."
    if codigo == 429:
        return "Se enviaron demasiadas solicitudes seguidas. Espere un momento e intente de nuevo."
    if codigo >= 500:
        return "El servicio de IA está ocupado o no disponible en este momento. Intente de nuevo en unos minutos."
    return f"El servicio de IA rechazó la solicitud (código {codigo}). {detalle}".strip()


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def _limpiar_historial(mensajes):
    limpio = []
    for m in (mensajes or [])[-MAX_TURNOS:]:
        if not isinstance(m, dict):
            continue
        rol, contenido = m.get("rol"), m.get("contenido")
        if rol not in ("user", "assistant") or not isinstance(contenido, str) or not contenido.strip():
            continue
        limpio.append({"role": rol, "content": contenido[:MAX_CHARS_MENSAJE]})
    while limpio and limpio[0]["role"] != "user":
        limpio.pop(0)
    return limpio


def responder(config, mensajes, codigo_actual=None, errores_actuales=None):
    clave, _ = config.clave()
    if clave is None:
        raise ErrorAsistente("El asistente todavía no tiene una clave de API. Agréguela en la configuración del asistente.", 400)
    modelo = config.modelo()

    historial = _limpiar_historial(mensajes)
    if not historial or historial[-1]["role"] != "user":
        raise ErrorAsistente("Escriba una pregunta o una petición para el asistente.", 400)

    extra = ""
    if isinstance(codigo_actual, str) and codigo_actual.strip():
        extra += "\n\n[Código que hay ahora en el editor del usuario]\n```\n" + codigo_actual[:MAX_CHARS_CODIGO] + "\n```"
    if isinstance(errores_actuales, list) and errores_actuales:
        lineas = [str(e)[:300] for e in errores_actuales[:MAX_ERRORES_CONTEXTO]]
        extra += "\n\n[Errores que mostró el compilador para ese código]\n" + "\n".join("- " + l for l in lineas)
    if extra:
        historial[-1] = {"role": "user", "content": historial[-1]["content"] + extra}

    msgs = list(historial)
    texto = _llamar_api(clave, modelo, INSTRUCCIONES, msgs)
    reintentos = 0
    while True:
        verificados = verificar(extraer_bloques(texto))
        malos = [v for v in verificados if not v["exitoso"]]
        if not malos or reintentos >= MAX_REINTENTOS:
            break
        reintentos += 1
        msgs = msgs + [{"role": "assistant", "content": texto},
                       {"role": "user", "content": _mensaje_correccion(malos)}]
        texto = _llamar_api(clave, modelo, INSTRUCCIONES, msgs)

    return {"respuesta": texto, "bloques": verificados, "reintentos": reintentos}
