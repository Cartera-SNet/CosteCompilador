# -*- coding: utf-8 -*-
"""
Costeñol - Ejecución del programa

Recorre el árbol sintáctico (ya validado por las tres fases anteriores) y
ejecuta las instrucciones. Es un generador: cada vez que el programa muestra
un mensaje o necesita que el usuario escriba un dato (Captura), "entrega" un
evento a quien lo maneja:

    {"evento": "salida",  "texto": "Hola Mundo"}
    {"evento": "entrada", "variable": "edad", "tipo_dato": "Entero", "linea": 4}

Errores que solo pueden verse al ejecutar (nunca revientan el programa):
    E-EJE-01  variable sin valor (solo si se asignó en un Si que no se ejecutó)
    E-EJE-02  división por cero
    E-EJE-03  resultado fuera de rango (Entero más allá de ±2147483647 o Real infinito)
    E-EJE-04  texto demasiado largo (más de 1000000 de caracteres al unir textos)
"""

import math
import re

from costenol_lexico import ENTERO_MAXIMO

ENTRADA_ENTERO = re.compile(r"^[+-]?[0-9]+$")
ENTRADA_REAL = re.compile(r"^[+-]?[0-9]+([,.][0-9]+)?$")
MAXIMO_TEXTO_ENTRADA = 10_000
MAXIMO_TEXTO = 1_000_000          # largo máximo de un texto armado con +


class ErrorEjecucion(Exception):
    def __init__(self, codigo, linea, columna, mensaje):
        super().__init__(mensaje)
        self.codigo = codigo
        self.linea = linea
        self.columna = columna
        self.mensaje = mensaje


# ---------------------------------------------------------------------------
# Texto <-> valores
# ---------------------------------------------------------------------------

def formato_real(x: float) -> str:
    if abs(x) < 5e-11:
        return "0,0"
    s = f"{x:.10f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return s.replace(".", ",")


def a_texto(v) -> str:
    if isinstance(v, bool):
        return "Verdadero" if v else "Falso"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return formato_real(v)
    return str(v)


def convertir_entrada(tipo: str, texto: str):
    """Convierte lo que escribió el usuario. Devuelve (ok, valor_o_mensaje)."""
    t = (texto or "").strip()
    if tipo == "Texto":
        if len(texto or "") > MAXIMO_TEXTO_ENTRADA:
            return False, f"El texto es demasiado largo (máximo {MAXIMO_TEXTO_ENTRADA} caracteres)."
        return True, texto or ""
    if tipo == "Entero":
        if not ENTRADA_ENTERO.match(t):
            return False, "Se esperaba un número entero (por ejemplo 25), sin decimales ni letras."
        if len(t.lstrip("+-").lstrip("0") or "0") > 10 or abs(int(t)) > ENTERO_MAXIMO:
            return False, f"El entero está fuera de rango (máximo {ENTERO_MAXIMO})."
        return True, int(t)
    if tipo == "Real":
        if not ENTRADA_REAL.match(t):
            return False, "Se esperaba un número real, con coma decimal (por ejemplo 3,5)."
        v = float(t.replace(",", "."))
        if math.isinf(v) or math.isnan(v):
            return False, "El número está fuera de rango."
        return True, v
    if tipo == "Logico":
        m = t.lower()
        if m == "verdadero":
            return True, True
        if m == "falso":
            return True, False
        return False, "Se esperaba Verdadero o Falso."
    return False, "Tipo de dato desconocido."


# ---------------------------------------------------------------------------
# Evaluación de expresiones
# ---------------------------------------------------------------------------

def _es_entero(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _verificar_rango(v, nodo):
    if _es_entero(v):
        if abs(v) > ENTERO_MAXIMO:
            raise ErrorEjecucion("E-EJE-03", nodo["linea"], nodo["columna"],
                                 f"El resultado {v} está fuera del rango de un Entero "
                                 f"(máximo {ENTERO_MAXIMO}).")
    elif isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
        raise ErrorEjecucion("E-EJE-03", nodo["linea"], nodo["columna"],
                             "El resultado de la operación es demasiado grande para un Real.")
    return v


def evaluar(n, memoria):
    k = n["nodo"]
    if k == "Numero":
        if n["tipo_dato"] == "Entero":
            return int(n["valor"])
        return float(n["valor"].replace(",", "."))
    if k == "Cadena":
        return n["valor"]
    if k == "Logico":
        return n["valor"]
    if k == "Variable":
        if n["nombre"] not in memoria:
            raise ErrorEjecucion("E-EJE-01", n["linea"], n["columna"],
                                 f"La variable '{n['nombre']}' no tiene valor en este punto de la ejecución.")
        return memoria[n["nombre"]]
    if k == "Unario":
        v = evaluar(n["operando"], memoria)
        return _verificar_rango(-v if n["op"] == "-" else v, n)
    if k == "Binario":
        return _binario(n, memoria)
    raise ErrorEjecucion("E-EJE-03", n.get("linea", 1), n.get("columna", 1), "Expresión desconocida.")


def _binario(n, memoria):
    op = n["op"]
    a = evaluar(n["izq"], memoria)
    b = evaluar(n["der"], memoria)
    if op == "+" and (isinstance(a, str) or isinstance(b, str)):
        r = a_texto(a) + a_texto(b)
        if len(r) > MAXIMO_TEXTO:
            raise ErrorEjecucion("E-EJE-04", n["linea"], n["columna"],
                                 f"El texto resultante es demasiado largo (máximo {MAXIMO_TEXTO} de caracteres).")
        return r
    if op in ("+", "-", "*"):
        r = a + b if op == "+" else a - b if op == "-" else a * b
        return _verificar_rango(r, n)
    if op == "/":
        if b == 0:
            raise ErrorEjecucion("E-EJE-02", n["linea"], n["columna"], "División por cero.")
        return _verificar_rango(float(a) / float(b), n)
    if op in ("==", "!="):
        if isinstance(a, float) or isinstance(b, float):
            igual = math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
        else:
            igual = a == b
        return igual if op == "==" else not igual
    if op == "<":
        return a < b and not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    if op == ">":
        return a > b and not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    if op == "<=":
        return a <= b or math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    if op == ">=":
        return a >= b or math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    raise ErrorEjecucion("E-EJE-03", n["linea"], n["columna"], f"Operador desconocido '{op}'.")


# ---------------------------------------------------------------------------
# Ejecución de instrucciones (generador)
# ---------------------------------------------------------------------------

def ejecutar(arbol):
    memoria = {}
    tipos = {}
    yield from _bloque(arbol["instrucciones"], memoria, tipos)


def _bloque(instrucciones, memoria, tipos):
    for n in instrucciones:
        k = n["nodo"]
        if k == "Declaracion":
            tipos[n["nombre"]] = n["tipo_dato"]
            memoria.pop(n["nombre"], None)
        elif k == "Asignacion":
            v = evaluar(n["valor"], memoria)
            if tipos.get(n["nombre"]) == "Real" and _es_entero(v):
                v = float(v)
            memoria[n["nombre"]] = v
        elif k == "Lectura":
            valor = yield {"evento": "entrada", "variable": n["nombre"],
                           "tipo_dato": n["tipo_dato"], "linea": n["linea"]}
            if tipos.get(n["nombre"]) == "Real" and _es_entero(valor):
                valor = float(valor)
            memoria[n["nombre"]] = valor
        elif k == "Mensaje":
            yield {"evento": "salida", "texto": a_texto(evaluar(n["valor"], memoria))}
        elif k == "Condicional":
            cond = evaluar(n["condicion"], memoria)
            if cond:
                yield from _bloque(n["entonces"], memoria, tipos)
            elif n.get("sino") is not None:
                yield from _bloque(n["sino"], memoria, tipos)


CATALOGO = {
    "E-EJE-01": ("Variable sin valor al ejecutar",
                 "La variable solo recibe valor dentro de un Si que no se ejecutó.",
                 "Asígnele un valor inicial antes del Si."),
    "E-EJE-02": ("División por cero",
                 "El divisor valió 0 al ejecutar.",
                 "Compruebe que el divisor no sea 0 antes de dividir."),
    "E-EJE-04": ("Texto demasiado largo",
                 "Al unir textos con + el resultado superó el máximo permitido (1000000 de caracteres).",
                 "No siga duplicando el texto: use textos más cortos."),
    "E-EJE-97": ("Error interno al ejecutar",
                 "Falló algo inesperado mientras se ejecutaba el programa.",
                 "Vuelva a intentarlo; si se repite, avise al equipo desarrollador."),
    "E-EJE-03": ("Resultado fuera de rango",
                 "El resultado de una operación es demasiado grande para un Entero (±2147483647) o un Real.",
                 "Use números más pequeños."),
}
