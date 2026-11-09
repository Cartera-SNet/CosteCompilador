#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Costeñol - Analizador Léxico (25 % del compilador)
Asignatura: Compiladores

Primera fase del compilador: descomponer el código fuente en tokens, de
izquierda a derecha, y rechazar todo lo que no pertenezca al lenguaje.

Reglas generales
  * El analizador NUNCA se cierra por culpa del código del usuario: todo
    problema se convierte en un diagnóstico (error o advertencia) con su
    línea y su columna.
  * Las mayúsculas y minúsculas importan (Si no es lo mismo que si).
  * Los decimales se escriben con coma (3,1416), como en el enunciado.
  * Cada línea se analiza por separado: ni los comentarios ni las cadenas
    pueden ocupar varias líneas.

Uso desde consola:
    python costenol_lexico.py programa.cst
"""

import re
import sys
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Definición del lenguaje (todo en un solo lugar para poder ajustarlo)
# ---------------------------------------------------------------------------

# Palabras reservadas del enunciado del profesor (mayúsculas exactas).
PALABRAS_RESERVADAS = (
    "Entero", "Texto", "Real", "Logico",   # tipos de dato
    "Captura", "Mensaje",                  # entrada y salida
    "Si", "Sino", "FinSi",                 # condicional
)

# Valores del tipo Logico (propuesta del equipo: confirmar con el docente).
VALORES_LOGICOS = ("Verdadero", "Falso")

# Operadores relacionales para las condiciones de Si (propuesta del equipo).
OPERADORES_RELACIONALES = ("==", "!=", "<", ">", "<=", ">=")

LONGITUD_MAXIMA_IDENTIFICADOR = 30
ENTERO_MAXIMO = 2_147_483_647          # 32 bits con signo
MAXIMO_ERRORES = 200
TAMANO_MAXIMO_CODIGO = 2_000_000       # caracteres

# Nombres de los tipos de token (en español).
COMENTARIO = "COMENTARIO"
CADENA = "CADENA"
PALABRA_RESERVADA = "PALABRA_RESERVADA"
IDENTIFICADOR = "IDENTIFICADOR"
NUMERO_ENTERO = "NUMERO_ENTERO"
NUMERO_REAL = "NUMERO_REAL"
VALOR_LOGICO = "VALOR_LOGICO"
OPERADOR_ASIGNACION = "OPERADOR_ASIGNACION"
OPERADOR_RELACIONAL = "OPERADOR_RELACIONAL"
OPERADOR_ARITMETICO = "OPERADOR_ARITMETICO"
PARENTESIS_APERTURA = "PARENTESIS_APERTURA"
PARENTESIS_CIERRE = "PARENTESIS_CIERRE"
PUNTO_Y_COMA = "PUNTO_Y_COMA"
PUNTO = "PUNTO"

TIPOS_DE_TOKEN = (
    PALABRA_RESERVADA, IDENTIFICADOR, NUMERO_ENTERO, NUMERO_REAL, CADENA,
    VALOR_LOGICO, OPERADOR_ASIGNACION, OPERADOR_RELACIONAL,
    OPERADOR_ARITMETICO, PARENTESIS_APERTURA, PARENTESIS_CIERRE,
    PUNTO_Y_COMA, PUNTO, COMENTARIO,
)

ERROR = "ERROR"
ADVERTENCIA = "ADVERTENCIA"

_SIMBOLOS = {
    "(": PARENTESIS_APERTURA,
    ")": PARENTESIS_CIERRE,
    ";": PUNTO_Y_COMA,
    "+": OPERADOR_ARITMETICO,
    "-": OPERADOR_ARITMETICO,
    "*": OPERADOR_ARITMETICO,
    "/": OPERADOR_ARITMETICO,
}
_GRUPO_RELACIONAL = "=<>!"
_COMILLAS = {'"': '"', "\u201c": "\u201d"}          # apertura -> cierre
_NOMBRE_COMILLA = {
    '"': 'comilla recta (")',
    "\u201c": "comilla curva de apertura (\u201c)",
    "\u201d": "comilla curva de cierre (\u201d)",
}
_RESERVADAS_MIN = {p.lower(): p for p in PALABRAS_RESERVADAS + VALORES_LOGICOS}
_RE_ENTERO = re.compile(r"^(0|[1-9][0-9]*)$")
_RE_REAL = re.compile(r"^(0|[1-9][0-9]*),[0-9]+$")


# ---------------------------------------------------------------------------
# Estructuras de datos
# ---------------------------------------------------------------------------

@dataclass
class Token:
    tipo: str
    valor: str
    linea: int
    columna: int


@dataclass
class Diagnostico:
    nivel: str          # ERROR o ADVERTENCIA
    codigo: str         # p. ej. E-LEX-07
    linea: int
    columna: int
    mensaje: str

    def texto(self) -> str:
        return f"[{self.codigo}] Línea {self.linea}, columna {self.columna}: {self.mensaje}"


@dataclass
class Resultado:
    tokens: list = field(default_factory=list)
    errores: list = field(default_factory=list)
    advertencias: list = field(default_factory=list)
    lineas: int = 0

    @property
    def exitoso(self) -> bool:
        return not self.errores

    def conteo_por_tipo(self) -> dict:
        conteo = {}
        for t in self.tokens:
            conteo[t.tipo] = conteo.get(t.tipo, 0) + 1
        return conteo

    def a_dict(self) -> dict:
        def d(x):
            return {"nivel": x.nivel, "codigo": x.codigo, "linea": x.linea,
                    "columna": x.columna, "mensaje": x.mensaje}
        return {
            "exitoso": self.exitoso,
            "lineas": self.lineas,
            "tokens": [[t.linea, t.columna, t.tipo, t.valor] for t in self.tokens],
            "errores": [d(e) for e in self.errores],
            "advertencias": [d(a) for a in self.advertencias],
            "conteo": self.conteo_por_tipo(),
        }


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def quitar_tildes(texto: str) -> str:
    """Quita las tildes y la diéresis, pero conserva la ñ."""
    texto = texto.replace("ñ", "\0n").replace("Ñ", "\0N")
    base = "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")
    return base.replace("\0n", "ñ").replace("\0N", "Ñ")


def _es_letra_valida(c: str) -> bool:
    return ("a" <= c <= "z") or ("A" <= c <= "Z") or c in "ñÑ"


def _es_caracter_de_palabra(c: str) -> bool:
    """Caracteres que se leen como parte de una palabra (aunque luego se
    rechacen) para poder dar un mensaje claro en vez de varios errores."""
    return c.isalnum() or c == "_" or unicodedata.category(c) == "Mn"


def _describir(c: str) -> str:
    cp = ord(c)
    if c.isprintable() and not c.isspace():
        return f"'{c}' (U+{cp:04X})"
    return f"carácter invisible (U+{cp:04X})"


def _sugerencia_reservada(palabra: str):
    """Si la palabra se parece a una reservada (otras mayúsculas o con tilde)
    devuelve la forma correcta."""
    sin_tildes = quitar_tildes(palabra)
    return _RESERVADAS_MIN.get(sin_tildes.lower())


# ---------------------------------------------------------------------------
# Analizador
# ---------------------------------------------------------------------------

class _Analizador:
    def __init__(self):
        self.res = Resultado()
        self._detenido = False

    # -- registro de diagnósticos ------------------------------------------
    def error(self, codigo, linea, col, mensaje):
        if len(self.res.errores) >= MAXIMO_ERRORES:
            if not self._detenido:
                self._detenido = True
                self.res.advertencias.append(Diagnostico(
                    ADVERTENCIA, "A-LEX-99", linea, col,
                    f"Se alcanzó el máximo de {MAXIMO_ERRORES} errores; "
                    "los siguientes no se muestran."))
            return
        self.res.errores.append(Diagnostico(ERROR, codigo, linea, col, mensaje))

    def aviso(self, codigo, linea, col, mensaje):
        self.res.advertencias.append(
            Diagnostico(ADVERTENCIA, codigo, linea, col, mensaje))

    def token(self, tipo, valor, linea, col):
        self.res.tokens.append(Token(tipo, valor, linea, col))

    # -- recorrido principal -----------------------------------------------
    def analizar(self, fuente: str) -> Resultado:
        if fuente.startswith("\ufeff"):
            fuente = fuente[1:]
        lineas = re.split(r"\r\n|\r|\n", fuente)
        # una sola nueva línea final no cuenta como línea
        if len(lineas) > 1 and lineas[-1] == "":
            lineas.pop()
        self.res.lineas = len(lineas)

        for numero, texto in enumerate(lineas, start=1):
            self._linea(numero, texto)
            if self._detenido:
                break

        if not self.res.tokens and not self.res.errores:
            self.aviso("A-LEX-01", 1, 1, "El código está vacío: no hay nada que analizar.")
        elif self.res.tokens and not self.res.errores and all(
                t.tipo == COMENTARIO for t in self.res.tokens):
            self.aviso("A-LEX-02", 1, 1, "El programa solo contiene comentarios, sin instrucciones.")
        return self.res

    def _linea(self, ln: int, s: str):
        i, n = 0, len(s)
        while i < n:
            c = s[i]
            col = i + 1

            # -- espacios -----------------------------------------------------
            if c in " \t":
                i += 1
                continue
            cat = unicodedata.category(c)
            if cat == "Zs":
                self.aviso("A-LEX-03", ln, col,
                           f"Espacio no estándar (U+{ord(c):04X}), típico de textos copiados desde "
                           "Word o la web. Se tomó como espacio; reemplácelo por un espacio normal.")
                i += 1
                continue

            # -- comentario  // ... //  --------------------------------------
            if s.startswith("//", i):
                fin = s.find("//", i + 2)
                if fin == -1:
                    self.error("E-LEX-01", ln, col,
                               "Comentario sin cerrar: falta el // de cierre en la misma línea.")
                    return                      # el resto de la línea queda dentro del comentario
                self.token(COMENTARIO, s[i:fin + 2], ln, col)
                i = fin + 2
                continue

            # -- cadena  "..."  o  “...”  ------------------------------------
            if c in _COMILLAS:
                cierre = _COMILLAS[c]
                fin = s.find(cierre, i + 1)
                if fin == -1:
                    otra = [q for q in ('"', "\u201d", "\u201c") if q != c and q in s[i + 1:]]
                    if otra:
                        self.error("E-LEX-02", ln, col,
                                   f"Cadena mal cerrada: se abrió con {_NOMBRE_COMILLA[c]} y debe cerrarse "
                                   f"con {_NOMBRE_COMILLA[cierre]}; se encontró {_NOMBRE_COMILLA[otra[0]]}.")
                    else:
                        self.error("E-LEX-02", ln, col,
                                   f"Cadena sin cerrar: falta la comilla de cierre {cierre} en la misma línea.")
                    return
                self.token(CADENA, s[i:fin + 1], ln, col)
                i = fin + 1
                continue

            # -- números ------------------------------------------------------
            if "0" <= c <= "9":
                j = i
                while j < n and (s[j].isalnum() or s[j] in "_,." or unicodedata.category(s[j]) == "Mn"):
                    j += 1
                self._numero(ln, col, s[i:j])
                i = j
                continue

            # .5  (número que empieza con punto)
            if c == "." and i + 1 < n and "0" <= s[i + 1] <= "9":
                j = i + 1
                while j < n and (s[j].isalnum() or s[j] in "_,."):
                    j += 1
                self.error("E-LEX-08", ln, col,
                           f"Número mal formado '{s[i:j]}': no puede empezar con punto; "
                           "escriba el cero y use coma decimal (ej.: 0,5).")
                i = j
                continue

            # -- palabras (identificadores y reservadas) ----------------------
            if c == "_" or c.isalpha():
                j = i
                while j < n and _es_caracter_de_palabra(s[j]):
                    j += 1
                self._palabra(ln, col, s[i:j])
                i = j
                continue

            # -- operadores = < > ! -------------------------------------------
            if c in _GRUPO_RELACIONAL:
                j = i
                while j < n and s[j] in _GRUPO_RELACIONAL:
                    j += 1
                self._operador_relacional(ln, col, s[i:j])
                i = j
                continue

            # -- símbolos simples ---------------------------------------------
            if c in _SIMBOLOS:
                self.token(_SIMBOLOS[c], c, ln, col)
                i += 1
                continue
            if c == ".":
                self.token(PUNTO, c, ln, col)
                i += 1
                continue

            # -- cualquier otra cosa es un error ------------------------------
            self._caracter_invalido(ln, col, c)
            i += 1

    # -- reglas por tipo de lexema -------------------------------------------
    def _numero(self, ln, col, m):
        if any(ch.isalpha() or ch == "_" or unicodedata.category(ch) == "Mn" for ch in m):
            self.error("E-LEX-04", ln, col,
                       f"Número mal formado '{m}': un número no puede contener letras ni quedar "
                       "pegado a un identificador.")
        elif "." in m:
            self.error("E-LEX-05", ln, col,
                       f"Decimal mal escrito '{m}': el separador decimal es la coma, no el punto "
                       "(ej.: 3,1416).")
        elif m.count(",") > 1:
            self.error("E-LEX-06", ln, col,
                       f"Número mal formado '{m}': solo se permite una coma decimal.")
        elif m.endswith(","):
            self.error("E-LEX-06", ln, col,
                       f"Número incompleto '{m}': después de la coma debe haber al menos un dígito.")
        elif _RE_ENTERO.match(m):
            if int(m) > ENTERO_MAXIMO:
                self.error("E-LEX-07", ln, col,
                           f"Entero fuera de rango '{m}': el máximo permitido es {ENTERO_MAXIMO}.")
            else:
                self.token(NUMERO_ENTERO, m, ln, col)
        elif _RE_REAL.match(m):
            self.token(NUMERO_REAL, m, ln, col)
        elif m[0] == "0":
            self.error("E-LEX-09", ln, col,
                       f"Número con ceros a la izquierda '{m}': no se permiten (escriba "
                       f"{m.lstrip('0') or '0'}).")
        else:
            self.error("E-LEX-04", ln, col, f"Número mal formado '{m}'.")

    def _palabra(self, ln, col, w):
        if w[0] == "_":
            self.error("E-LEX-10", ln, col,
                       f"Identificador '{w}' inválido: debe empezar con una letra, no con guion bajo.")
            return

        invalidos = []
        for ch in w:
            if not (_es_letra_valida(ch) or "0" <= ch <= "9" or ch == "_") and ch not in invalidos:
                invalidos.append(ch)
        if invalidos:
            detalle = ", ".join(_describir(ch) for ch in invalidos)
            msg = (f"'{w}' contiene caracteres no permitidos: {detalle}. Solo se aceptan letras "
                   "sin tilde, ñ, dígitos y guion bajo.")
            sug = _sugerencia_reservada(w)
            if sug:
                msg += f" ¿Quiso decir '{sug}'?"
            self.error("E-LEX-11", ln, col, msg)
            return

        if len(w) > LONGITUD_MAXIMA_IDENTIFICADOR:
            self.error("E-LEX-12", ln, col,
                       f"Identificador demasiado largo ({len(w)} caracteres): el máximo es "
                       f"{LONGITUD_MAXIMA_IDENTIFICADOR}.")
            return

        if w in PALABRAS_RESERVADAS:
            self.token(PALABRA_RESERVADA, w, ln, col)
        elif w in VALORES_LOGICOS:
            self.token(VALOR_LOGICO, w, ln, col)
        else:
            self.token(IDENTIFICADOR, w, ln, col)

    def _operador_relacional(self, ln, col, r):
        if r == "=":
            self.token(OPERADOR_ASIGNACION, r, ln, col)
        elif r in OPERADORES_RELACIONALES:
            self.token(OPERADOR_RELACIONAL, r, ln, col)
        else:
            ayudas = {
                "!": "el signo ! solo no existe; para 'distinto de' use !=.",
                "<>": "para 'distinto de' use !=.",
                "=>": "para 'mayor o igual' use >= (el igual va después).",
                "=<": "para 'menor o igual' use <= (el igual va después).",
                "===": "no existe ===; para comparar use ==.",
            }
            extra = ayudas.get(r, "los operadores válidos son = == != < > <= >=.")
            self.error("E-LEX-13", ln, col, f"Operador no válido '{r}': {extra}")

    def _caracter_invalido(self, ln, col, c):
        cat = unicodedata.category(c)
        if cat in ("Cf", "Cc", "Zl", "Zp", "Co", "Cn", "Cs"):
            self.error("E-LEX-14", ln, col,
                       f"Carácter invisible o de control no permitido ({_describir(c)}). "
                       "Bórrelo o vuelva a escribir la línea.")
            return
        ayudas = {
            ",": "la coma solo se usa como separador decimal dentro de un número (ej.: 3,14).",
            "'": "para textos use comillas dobles (\"texto\").",
            "\u2018": "para textos use comillas dobles (\"texto\").",
            "\u2019": "para textos use comillas dobles (\"texto\").",
            "\u201d": "es una comilla de cierre sin su comilla de apertura “.",
            "`": "para textos use comillas dobles (\"texto\").",
            "{": "las llaves no forman parte de Costeñol; los bloques se cierran con FinSi.",
            "}": "las llaves no forman parte de Costeñol; los bloques se cierran con FinSi.",
            "[": "los corchetes no forman parte de Costeñol.",
            "]": "los corchetes no forman parte de Costeñol.",
            ":": "los dos puntos no forman parte de Costeñol; declare así: nombre Tipo;",
            "&": "no existen operadores lógicos con & en Costeñol.",
            "|": "no existen operadores lógicos con | en Costeñol.",
            "%": "el módulo (%) no forma parte de Costeñol.",
            "¿": "los signos de interrogación no se usan fuera de un texto.",
            "?": "los signos de interrogación no se usan fuera de un texto.",
            "¡": "los signos de exclamación no se usan fuera de un texto.",
        }
        extra = ayudas.get(c, "no forma parte del alfabeto de Costeñol.")
        self.error("E-LEX-15", ln, col, f"Carácter no válido {_describir(c)}: {extra}")


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def analizar(fuente) -> Resultado:
    """Analiza el texto y devuelve un Resultado. Nunca lanza excepciones."""
    try:
        if fuente is None:
            fuente = ""
        if not isinstance(fuente, str):
            fuente = str(fuente)
        if len(fuente) > TAMANO_MAXIMO_CODIGO:
            r = Resultado()
            r.errores.append(Diagnostico(
                ERROR, "E-LEX-98", 1, 1,
                f"El código supera el tamaño máximo permitido ({TAMANO_MAXIMO_CODIGO} caracteres)."))
            return r
        return _Analizador().analizar(fuente)
    except Exception as exc:  # defensa final: el programa nunca debe reventar
        r = Resultado()
        r.errores.append(Diagnostico(
            ERROR, "E-LEX-97", 1, 1,
            f"Error interno del analizador ({type(exc).__name__}: {exc}). El programa sigue activo."))
        return r


# ---------------------------------------------------------------------------
# Catálogo de mensajes (lo usa el Manual de uso): código -> (título, qué
# significa, cómo corregirlo). Todo código que emita el analizador debe estar
# aquí; las pruebas lo verifican.
# ---------------------------------------------------------------------------

CATALOGO = {
    "E-LEX-01": ("Comentario sin cerrar",
                 "Un comentario empieza con // pero no tiene el // de cierre en la misma línea.",
                 "Cierre el comentario con // en la misma línea: // esto es un comentario //"),
    "E-LEX-02": ("Cadena de texto mal cerrada",
                 "Un texto empieza con comillas pero no se cierra en la misma línea, o se cierra con otro tipo de comilla.",
                 "Cierre el texto con la misma comilla con que lo abrió, en la misma línea: \"Hola\"."),
    "E-LEX-04": ("Número mal formado",
                 "Un número tiene letras pegadas o quedó unido a un nombre (por ejemplo 5abc).",
                 "Separe el número del resto con un espacio o un símbolo. Los nombres no pueden empezar con un dígito."),
    "E-LEX-05": ("Decimal con punto",
                 "Los decimales de Costeñol se escriben con coma, no con punto.",
                 "Escriba 3,1416 en lugar de 3.1416."),
    "E-LEX-06": ("Coma decimal mal usada",
                 "El número tiene una coma sin dígitos después, o más de una coma.",
                 "Un real lleva una sola coma y al menos un dígito después: 3,5."),
    "E-LEX-07": ("Entero fuera de rango",
                 "El número entero es mayor que el máximo permitido (2147483647).",
                 "Use un número menor o igual a 2147483647."),
    "E-LEX-08": ("Número que empieza con punto",
                 "Un número como .5 no es válido.",
                 "Escriba el cero y use coma: 0,5."),
    "E-LEX-09": ("Ceros a la izquierda",
                 "Un número no puede empezar con ceros innecesarios (007).",
                 "Quite los ceros de la izquierda: 7."),
    "E-LEX-10": ("Nombre que empieza con guion bajo",
                 "Los nombres de variable deben empezar con una letra.",
                 "Empiece el nombre con una letra: x_1."),
    "E-LEX-11": ("Carácter no permitido en un nombre",
                 "El nombre tiene tildes u otros símbolos. Solo se aceptan letras sin tilde (y la ñ), dígitos y guion bajo.",
                 "Quite la tilde o el símbolo. Las palabras reservadas se escriben sin tilde (Logico)."),
    "E-LEX-12": ("Nombre demasiado largo",
                 "El nombre supera los 30 caracteres.",
                 "Use un nombre más corto."),
    "E-LEX-13": ("Operador no válido",
                 "Se escribió un operador que no existe (=>, =<, <>, ===, ! suelto).",
                 "Los operadores son: = == != < > <= >= + - * /"),
    "E-LEX-14": ("Carácter invisible",
                 "Hay un carácter de control o invisible, normalmente por copiar texto desde otro programa.",
                 "Borre el carácter y escriba de nuevo la línea."),
    "E-LEX-15": ("Carácter no válido",
                 "El símbolo no forma parte del lenguaje Costeñol.",
                 "Quítelo o reemplácelo. Fuera de textos y comentarios solo se aceptan letras, dígitos y: = < > ! + - * / ( ) ; ."),
    "E-LEX-97": ("Error interno del analizador léxico",
                 "Falló algo inesperado en el programa.",
                 "Vuelva a intentarlo; si se repite, avise al equipo desarrollador."),
    "E-LEX-98": ("Código demasiado grande",
                 "El código supera el tamaño máximo permitido (2 000 000 de caracteres).",
                 "Divida el programa en partes más pequeñas."),
    "A-LEX-01": ("Código vacío", "No hay nada que analizar.", "Escriba un programa."),
    "A-LEX-02": ("Solo comentarios", "El programa solo tiene comentarios, sin instrucciones.", "Agregue instrucciones."),
    "A-LEX-03": ("Espacio no estándar",
                 "Hay un espacio especial (por ejemplo de Word). Se tomó como un espacio normal.",
                 "Reemplácelo por un espacio normal."),
    "A-LEX-99": ("Demasiados errores", "Se alcanzó el máximo de 200 errores; los demás no se muestran.", "Corrija los primeros y vuelva a compilar."),
}


# ---------------------------------------------------------------------------
# Uso por consola
# ---------------------------------------------------------------------------

def _principal(argv):
    if len(argv) < 2:
        print("Uso: python costenol_lexico.py archivo.cst")
        return 2
    try:
        with open(argv[1], "r", encoding="utf-8-sig", errors="replace") as f:
            codigo = f.read()
    except OSError as exc:
        print(f"No se pudo leer el archivo: {exc}")
        return 2
    res = analizar(codigo)
    for t in res.tokens:
        print(f"{t.linea:>4}:{t.columna:<4} {t.tipo:<20} {t.valor}")
    for d in res.advertencias + res.errores:
        print(f"{d.nivel}: {d.texto()}")
    print(f"\n{len(res.tokens)} tokens, {len(res.errores)} errores, {len(res.advertencias)} advertencias.")
    return 0 if res.exitoso else 1


if __name__ == "__main__":
    sys.exit(_principal(sys.argv))
