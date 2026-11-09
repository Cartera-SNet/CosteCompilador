# -*- coding: utf-8 -*-
"""
Costeñol - Compilador: une las fases en una sola llamada.

    1. Análisis léxico       (costenol_lexico.py)
    2. Análisis sintáctico   (costenol_sintactico.py)
    3. Análisis semántico    (costenol_semantico.py)
    4. Ejecución             (costenol_ejecucion.py)

Una fase solo se ejecuta si la anterior terminó sin errores.
"""

import os
import secrets
import threading
import time

import costenol_dialecto as dialecto
import costenol_ejecucion as ejecucion
import costenol_lexico as lexico
import costenol_semantico as semantico
import costenol_sintactico as sintactico

# Topes para que la respuesta nunca sea gigante (el análisis y la ejecución siguen siendo completos).
MAX_TOKENS_RESPUESTA = 20000
MAX_ADVERTENCIAS_RESPUESTA = 500
MAX_SIMBOLOS_RESPUESTA = 5000
MAX_NODOS_ARBOL_RESPUESTA = 20000

NOMBRES_FASES = (
    ("lexico", "Análisis léxico"),
    ("sintactico", "Análisis sintáctico"),
    ("semantico", "Análisis semántico"),
)


def _diag(d, fase):
    return {"fase": fase, "nivel": d.nivel, "codigo": d.codigo, "linea": d.linea,
            "columna": d.columna, "mensaje": d.mensaje,
            "mensaje_costeno": dialecto.frase(d.codigo, d.linea, d.mensaje)}


def contar_nodos(arbol) -> int:
    """Cantidad de nodos del árbol (sin recursión)."""
    total, pila = 0, [arbol]
    while pila:
        x = pila.pop()
        if isinstance(x, dict):
            total += 1 if "nodo" in x else 0
            pila.extend(v for v in x.values() if isinstance(v, (dict, list)))
        elif isinstance(x, list):
            pila.extend(x)
    return total


def publico(comp: dict) -> dict:
    """Versión de la compilación que se manda al navegador: sin un árbol gigantesco."""
    arbol = comp.get("arbol")
    if arbol is not None and contar_nodos(arbol) > MAX_NODOS_ARBOL_RESPUESTA:
        copia = dict(comp)
        copia["arbol"] = None
        copia["arbol_omitido"] = True
        return copia
    return comp


def compilar(codigo) -> dict:
    """Analiza el programa con las tres fases. Nunca lanza excepciones."""
    salida = {
        "exitoso": False, "fase_fallida": None, "lineas": 0,
        "tokens": [], "conteo": {}, "errores": [], "advertencias": [],
        "arbol": None, "simbolos": [], "fases": [],
    }
    estado = {k: "omitida" for k, _ in NOMBRES_FASES}

    # -- fase 1: léxico
    lex = lexico.analizar(codigo)
    d = lex.a_dict()
    salida["lineas"] = d["lineas"]
    salida["tokens_total"] = len(d["tokens"])
    salida["tokens"] = d["tokens"][:MAX_TOKENS_RESPUESTA]
    salida["conteo"] = d["conteo"]
    salida["errores"] += [_diag(x, "lexico") for x in lex.errores]
    salida["advertencias"] += [_diag(x, "lexico") for x in lex.advertencias]
    estado["lexico"] = "error" if lex.errores else "ok"

    # -- fase 2: sintáctico
    if not lex.errores:
        arbol, errs, avisos = sintactico.analizar_sintaxis(lex.tokens)
        salida["errores"] += [_diag(x, "sintactico") for x in errs]
        salida["advertencias"] += [_diag(x, "sintactico") for x in avisos]
        estado["sintactico"] = "error" if errs else "ok"

        # -- fase 3: semántico
        if not errs and arbol is not None:
            errs2, avisos2, simbolos = semantico.analizar_semantica(arbol)
            salida["errores"] += [_diag(x, "semantico") for x in errs2]
            salida["advertencias"] += [_diag(x, "semantico") for x in avisos2]
            salida["simbolos"] = simbolos
            estado["semantico"] = "error" if errs2 else "ok"
        if not errs:
            salida["arbol"] = arbol

    for k, nombre in NOMBRES_FASES:
        n = sum(1 for e in salida["errores"] if e["fase"] == k)
        salida["fases"].append({"id": k, "nombre": nombre, "estado": estado[k], "errores": n})
    for k, _ in NOMBRES_FASES:
        if estado[k] == "error":
            salida["fase_fallida"] = k
            break
    salida["errores"].sort(key=lambda e: (e["linea"], e["columna"]))
    salida["advertencias"].sort(key=lambda e: (e["linea"], e["columna"]))
    salida["advertencias_total"] = len(salida["advertencias"])
    salida["advertencias"] = salida["advertencias"][:MAX_ADVERTENCIAS_RESPUESTA]
    salida["simbolos_total"] = len(salida["simbolos"])
    salida["simbolos"] = salida["simbolos"][:MAX_SIMBOLOS_RESPUESTA]
    salida["exitoso"] = salida["fase_fallida"] is None
    return salida


def catalogo() -> list:
    """Todos los mensajes que puede dar el compilador (para el Manual de uso)."""
    fuentes = (
        ("Análisis léxico", lexico.CATALOGO),
        ("Análisis sintáctico", sintactico.CATALOGO),
        ("Análisis semántico", semantico.CATALOGO),
        ("Ejecución", ejecucion.CATALOGO),
    )
    lista = []
    for fase, cat in fuentes:
        for codigo in sorted(cat):
            titulo, significa, corregir = cat[codigo]
            lista.append({"fase": fase, "codigo": codigo,
                          "tipo": "Advertencia" if codigo.startswith("A-") else "Error",
                          "titulo": titulo, "significa": significa, "corregir": corregir})
    return lista


# ---------------------------------------------------------------------------
# Sesiones de ejecución (el programa puede detenerse a pedir datos)
# ---------------------------------------------------------------------------

try:
    LIMITE_SESIONES = max(5, int(os.environ.get("COSTENOL_MAX_SESIONES", "30")))
except ValueError:
    LIMITE_SESIONES = 30
VIDA_SESION = 15 * 60          # segundos


class Sesion:
    def __init__(self, arbol):
        self.gen = ejecucion.ejecutar(arbol)
        self.iniciada = False
        self.pendiente = None
        self.terminada = False
        self.ultimo_uso = time.time()
        self.cerrojo = threading.Lock()

    def _correr(self, enviar=None):
        salida = []
        error = None
        espera = None
        try:
            if not self.iniciada:
                self.iniciada = True
                ev = next(self.gen)
            else:
                ev = self.gen.send(enviar)
            while True:
                if ev["evento"] == "salida":
                    salida.append(ev["texto"])
                    ev = next(self.gen)
                else:
                    espera = ev
                    break
        except StopIteration:
            self.terminada = True
        except ejecucion.ErrorEjecucion as e:
            self.terminada = True
            error = {"codigo": e.codigo, "linea": e.linea, "columna": e.columna, "mensaje": e.mensaje,
                     "mensaje_costeno": dialecto.frase(e.codigo, e.linea, e.mensaje)}
        except Exception as e:  # defensa final
            self.terminada = True
            msg = f"Error interno al ejecutar ({type(e).__name__}: {e})."
            error = {"codigo": "E-EJE-97", "linea": 1, "columna": 1, "mensaje": msg,
                     "mensaje_costeno": dialecto.frase("E-EJE-97", 1, msg)}
        self.pendiente = espera
        return {"salida": salida, "espera": espera, "terminado": self.terminada, "error": error}

    def iniciar(self):
        with self.cerrojo:
            self.ultimo_uso = time.time()
            return self._correr()

    def entregar(self, texto):
        """Valida y entrega un dato. Devuelve el mismo formato que iniciar()."""
        with self.cerrojo:
            self.ultimo_uso = time.time()
            if self.terminada or self.pendiente is None:
                return {"salida": [], "espera": None, "terminado": True, "error": None}
            ok, valor = ejecucion.convertir_entrada(self.pendiente["tipo_dato"], texto)
            if not ok:
                return {"salida": [], "espera": self.pendiente, "terminado": False,
                        "error": None, "invalida": valor}
            return self._correr(valor)


class Sesiones:
    def __init__(self):
        self._datos = {}
        self._cerrojo = threading.Lock()

    def crear(self, arbol):
        with self._cerrojo:
            ahora = time.time()
            for k in [k for k, s in self._datos.items() if ahora - s.ultimo_uso > VIDA_SESION or s.terminada]:
                del self._datos[k]
            while len(self._datos) >= LIMITE_SESIONES:
                viejo = min(self._datos, key=lambda k: self._datos[k].ultimo_uso)
                del self._datos[viejo]
            sid = secrets.token_hex(8)
            self._datos[sid] = Sesion(arbol)
            return sid, self._datos[sid]

    def obtener(self, sid):
        with self._cerrojo:
            return self._datos.get(sid)

    def cerrar(self, sid):
        with self._cerrojo:
            self._datos.pop(sid, None)
