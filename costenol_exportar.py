# -*- coding: utf-8 -*-
"""
Costeñol - Exportar (generación de código)

Traduce un programa Costeñol (ya validado por las tres fases del compilador) a
otro lenguaje para poder ejecutarlo fuera del compilador:

    python       programa.py     se ejecuta con   python programa.py
    javascript   programa.js     se ejecuta con   node programa.js
    html         programa.html   se abre con doble clic en cualquier navegador
    java_fuente  Programa.java   se compila con   javac Programa.java
    java_jar     programa.jar    se ejecuta con   java -jar programa.jar
                                 (para construir el .jar el computador necesita un JDK)

El programa exportado se comporta igual que el compilador: mismos resultados,
mismo formato de números (decimales con coma), mismas validaciones al leer
datos y los mismos errores de ejecución (división por cero, enteros fuera de
rango...). Las pruebas (pruebas_exportar.py) lo comprueban comparando el
resultado de cada formato con el del intérprete.

Se usa el tipo de cada expresión que anotó el análisis semántico (tipo_expr).
Todas las variables se llaman v_nombre en el código generado, para que nunca
choquen con palabras reservadas del otro lenguaje.
"""

import json
import os
import shutil
import subprocess
import tempfile

from costenol_lexico import ENTERO_MAXIMO

NUMERICOS = ("Entero", "Real")
OPERADORES_COMPARACION = ("==", "!=", "<", ">", "<=", ">=")
MAXIMO_TEXTO_ENTRADA = 10_000
MAXIMO_TEXTO = 1_000_000


class ErrorExportacion(Exception):
    def __init__(self, mensaje, estado=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado = estado


# ---------------------------------------------------------------------------
# Formatos disponibles
# ---------------------------------------------------------------------------

def _herramienta(nombre):
    ruta = shutil.which(nombre)
    if ruta:
        return ruta
    casa = os.environ.get("JAVA_HOME")
    if casa:
        candidata = os.path.join(casa, "bin", nombre + (".exe" if os.name == "nt" else ""))
        if os.path.isfile(candidata):
            return candidata
    return None


def jdk_disponible():
    return bool(_herramienta("javac") and _herramienta("jar"))


def formatos():
    jdk = jdk_disponible()
    return [
        {"id": "python", "nombre": "Python", "extension": ".py", "disponible": True,
         "descripcion": "Un script de Python.",
         "como": "Se ejecuta con:  python {archivo}"},
        {"id": "javascript", "nombre": "JavaScript (Node.js)", "extension": ".js", "disponible": True,
         "descripcion": "Un programa de JavaScript para Node.js.",
         "como": "Se ejecuta con:  node {archivo}"},
        {"id": "html", "nombre": "Página web", "extension": ".html", "disponible": True,
         "descripcion": "Un archivo que se abre con doble clic en cualquier navegador; no necesita instalar nada.",
         "como": "Ábralo con doble clic."},
        {"id": "java_jar", "nombre": "Java ejecutable", "extension": ".jar", "disponible": jdk,
         "descripcion": ("Un archivo .jar listo para ejecutar." if jdk else
                         "Un archivo .jar. Para construirlo hace falta un JDK (javac y jar) y no se encontró uno en este computador."),
         "como": "Se ejecuta con:  java -jar {archivo}"},
        {"id": "java_fuente", "nombre": "Java (código fuente)", "extension": ".java", "disponible": True,
         "descripcion": "El código fuente en Java; se compila con un JDK.",
         "como": "Se compila con:  javac Programa.java   y se ejecuta con:  java Programa"},
    ]


# ---------------------------------------------------------------------------
# Generador común
# ---------------------------------------------------------------------------

class Generador:
    SANGRIA = "    "

    def __init__(self, arbol):
        self.arbol = arbol
        self.vars = {}             # nombre -> tipo
        self.riesgosas = set()     # variables que pueden no tener valor al leerlas
        self.lineas = []
        self._explorar(arbol["instrucciones"])

    # -- exploración previa -------------------------------------------------------
    def _explorar(self, lista):
        for n in lista or []:
            k = n["nodo"]
            if k == "Declaracion":
                self.vars[n["nombre"]] = n["tipo_dato"]
            elif k in ("Asignacion", "Mensaje"):
                self._explorar_expr(n["valor"])
            elif k == "Condicional":
                self._explorar_expr(n["condicion"])
                self._explorar(n["entonces"])
                self._explorar(n["sino"])

    def _explorar_expr(self, e):
        if e["nodo"] == "Variable" and e.get("riesgosa"):
            self.riesgosas.add(e["nombre"])
        for clave in ("izq", "der", "operando"):
            if clave in e:
                self._explorar_expr(e[clave])

    # -- instrucciones -----------------------------------------------------------
    def emitir(self, texto, nivel):
        self.lineas.append(self.SANGRIA * nivel + texto if texto else "")

    def bloque(self, lista, nivel):
        if not lista:
            self.vacio(nivel)
            return
        for n in lista:
            k = n["nodo"]
            if k == "Declaracion":
                self.decl(n, nivel)
            elif k == "Asignacion":
                self.asig(n, nivel)
            elif k == "Lectura":
                self.lect(n, nivel)
            elif k == "Mensaje":
                self.msg(n, nivel)
            elif k == "Condicional":
                self.si(n, nivel)

    def valor_para(self, nombre, n):
        """Código del valor de n, convertido a Real si la variable es Real."""
        c = self.expr(n)
        if self.vars[nombre] == "Real" and n["tipo_expr"] == "Entero":
            return self.a_real(c)
        return c

    # -- expresiones ---------------------------------------------------------------
    def expr(self, n):
        k = n["nodo"]
        if k == "Numero":
            return self.lit_num(n["valor"], n["tipo_dato"])
        if k == "Cadena":
            return self.lit_txt(n["valor"])
        if k == "Logico":
            return self.lit_log(n["valor"])
        if k == "Variable":
            return self.leer_var(n)
        if k == "Unario":
            c = self.expr(n["operando"])
            if n["op"] == "+":
                return c
            return self.negar(c, n["tipo_expr"], n["linea"])
        return self.binario(n)

    def texto_de(self, n):
        c = self.expr(n)
        t = n["tipo_expr"]
        return c if t == "Texto" else self.conv_texto(c, t)

    def binario(self, n):
        op, izq, der, linea = n["op"], n["izq"], n["der"], n["linea"]
        ti, td = izq["tipo_expr"], der["tipo_expr"]
        if op in OPERADORES_COMPARACION:
            a, b = self.expr(izq), self.expr(der)
            if ti in NUMERICOS and td in NUMERICOS:
                return self.cmp_num(op, a, b, ti == "Real" or td == "Real")
            if ti == "Texto":
                return self.cmp_txt(op, a, b)
            return self.cmp_log(op, a, b)
        if op == "+" and (ti == "Texto" or td == "Texto"):
            return self.concat(self.texto_de(izq), self.texto_de(der), linea)
        a, b = self.expr(izq), self.expr(der)
        if op == "/":
            return self.dividir(a, b, linea)
        if n["tipo_expr"] == "Entero":
            return self.arit_ent(op, a, b, linea)
        return self.arit_real(op, a, b, linea)

    def generar(self):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

PY_EJECUCION = '''\
import math
import re
import sys

try:                                     # que las tildes y la ñ salgan bien en cualquier consola
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass

_MAX = %(MAX)d


class _Error(Exception):
    def __init__(self, linea, mensaje):
        Exception.__init__(self, mensaje)
        self.linea = linea
        self.mensaje = mensaje


class _Fin(Exception):
    pass


def _ent(v, l):
    if abs(v) > _MAX:
        raise _Error(l, "El resultado %%d está fuera del rango de un Entero (máximo %%d)." %% (v, _MAX))
    return v


def _real(v, l):
    if math.isinf(v) or math.isnan(v):
        raise _Error(l, "El resultado de la operación es demasiado grande para un Real.")
    return v


def _dividir(a, b, l):
    if b == 0:
        raise _Error(l, "División por cero.")
    return _real(float(a) / float(b), l)


def _cerca(a, b):
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def _cat(s, l):
    if len(s) > %(MAXTXTO)d:
        raise _Error(l, "El texto resultante es demasiado largo (máximo %(MAXTXTO)d de caracteres).")
    return s


def _fmt(x):
    if abs(x) < 5e-11:
        return "0,0"
    s = ("%%.10f" %% x).rstrip("0")
    if s.endswith("."):
        s += "0"
    return s.replace(".", ",")


def _fmtl(b):
    return "Verdadero" if b else "Falso"


def _v(valor, nombre, l):
    if valor is None:
        raise _Error(l, "La variable '%%s' no tiene valor en este punto de la ejecución." %% nombre)
    return valor


def _linea():
    s = sys.stdin.readline()
    if s == "":
        raise _Fin()
    return s.rstrip("\\r\\n")


def _pedir(validar):
    while True:
        ok, valor = validar(_linea())
        if ok:
            return valor
        print("Valor no válido: " + valor)


def _val_entero(t):
    t = t.strip()
    if not re.fullmatch(r"[+-]?[0-9]+", t):
        return False, "Se esperaba un número entero (por ejemplo 25), sin decimales ni letras."
    if len(t.lstrip("+-").lstrip("0") or "0") > 10 or abs(int(t)) > _MAX:
        return False, "El entero está fuera de rango (máximo %%d)." %% _MAX
    return True, int(t)


def _val_real(t):
    t = t.strip()
    if not re.fullmatch(r"[+-]?[0-9]+([,.][0-9]+)?", t):
        return False, "Se esperaba un número real, con coma decimal (por ejemplo 3,5)."
    v = float(t.replace(",", "."))
    if math.isinf(v) or math.isnan(v):
        return False, "El número está fuera de rango."
    return True, v


def _val_logico(t):
    m = t.strip().lower()
    if m == "verdadero":
        return True, True
    if m == "falso":
        return True, False
    return False, "Se esperaba Verdadero o Falso."


def _val_texto(t):
    if len(t) > %(MAXTXT)d:
        return False, "El texto es demasiado largo (máximo %(MAXTXT)d caracteres)."
    return True, t


def _leer_entero():
    return _pedir(_val_entero)


def _leer_real():
    return _pedir(_val_real)


def _leer_logico():
    return _pedir(_val_logico)


def _leer_texto():
    return _pedir(_val_texto)

''' % {"MAX": ENTERO_MAXIMO, "MAXTXT": MAXIMO_TEXTO_ENTRADA, "MAXTXTO": MAXIMO_TEXTO}


class GenPython(Generador):
    def lit_num(self, valor, tipo):
        return valor if tipo == "Entero" else valor.replace(",", ".")

    def lit_txt(self, t):
        return repr(t)

    def lit_log(self, b):
        return "True" if b else "False"

    def leer_var(self, n):
        v = "v_" + n["nombre"]
        return f'_v({v}, {n["nombre"]!r}, {n["linea"]})' if n.get("riesgosa") else v

    def negar(self, c, tipo, linea):
        return f"_ent(-{c}, {linea})" if tipo == "Entero" else f"(-{c})"

    def arit_ent(self, op, a, b, linea):
        return f"_ent(({a} {op} {b}), {linea})"

    def arit_real(self, op, a, b, linea):
        return f"_real(({a} {op} {b}), {linea})"

    def dividir(self, a, b, linea):
        return f"_dividir({a}, {b}, {linea})"

    def concat(self, a, b, linea):
        return f"_cat(({a} + {b}), {linea})"

    def conv_texto(self, c, tipo):
        return {"Entero": f"str({c})", "Real": f"_fmt({c})", "Logico": f"_fmtl({c})"}[tipo]

    def a_real(self, c):
        return f"float({c})"

    def cmp_num(self, op, a, b, real):
        if not real:
            return f"({a} {op} {b})"
        return {
            "==": f"_cerca({a}, {b})", "!=": f"(not _cerca({a}, {b}))",
            "<": f"({a} < {b} and not _cerca({a}, {b}))", ">": f"({a} > {b} and not _cerca({a}, {b}))",
            "<=": f"({a} <= {b} or _cerca({a}, {b}))", ">=": f"({a} >= {b} or _cerca({a}, {b}))",
        }[op]

    def cmp_txt(self, op, a, b):
        return f"({a} {op} {b})"

    cmp_log = cmp_txt

    def vacio(self, nivel):
        self.emitir("pass", nivel)

    def decl(self, n, nivel):
        self.emitir(f'v_{n["nombre"]} = None', nivel)

    def asig(self, n, nivel):
        self.emitir(f'v_{n["nombre"]} = {self.valor_para(n["nombre"], n["valor"])}', nivel)

    def lect(self, n, nivel):
        c = {"Entero": "_leer_entero()", "Real": "_leer_real()", "Texto": "_leer_texto()",
             "Logico": "_leer_logico()"}[n["tipo_dato"]]
        if self.vars[n["nombre"]] == "Real" and n["tipo_dato"] == "Entero":
            c = f"float({c})"
        self.emitir(f'v_{n["nombre"]} = {c}', nivel)

    def msg(self, n, nivel):
        self.emitir(f'print({self.texto_de(n["valor"])})', nivel)

    def si(self, n, nivel):
        self.emitir(f'if {self.expr(n["condicion"])}:', nivel)
        self.bloque(n["entonces"], nivel + 1)
        if n.get("sino"):
            self.emitir("else:", nivel)
            self.bloque(n["sino"], nivel + 1)

    def generar(self):
        self.emitir("def principal():", 0)
        if self.arbol["instrucciones"]:
            self.bloque(self.arbol["instrucciones"], 1)
        else:
            self.emitir("pass", 1)
        cuerpo = "\n".join(self.lineas)
        return (
            "#!/usr/bin/env python3\n"
            "# -*- coding: utf-8 -*-\n"
            "# Programa generado por el compilador Costeñol.\n"
            "# Para ejecutarlo:  python programa.py\n\n"
            + PY_EJECUCION +
            "\n" + cuerpo + "\n\n\n"
            "def _main():\n"
            "    try:\n"
            "        principal()\n"
            "    except _Error as e:\n"
            '        print("Error de ejecución (línea %d): %s" % (e.linea, e.mensaje), file=sys.stderr)\n'
            "        sys.exit(1)\n"
            "    except _Fin:\n"
            '        print("Error de ejecución: el programa esperaba un dato y no hay más datos.", file=sys.stderr)\n'
            "        sys.exit(1)\n"
            "    except KeyboardInterrupt:\n"
            "        sys.exit(130)\n\n\n"
            'if __name__ == "__main__":\n'
            "    _main()\n"
        )


# ---------------------------------------------------------------------------
# JavaScript (Node.js y navegador)
# ---------------------------------------------------------------------------

JS_COMUN = '''\
const _MAX = %(MAX)d;

class _Error extends Error {
  constructor(linea, mensaje) { super(mensaje); this.linea = linea; this.mensaje = mensaje; }
}
class _Fin extends Error {}

function _ent(v, l) {
  if (Math.abs(v) > _MAX) throw new _Error(l, "El resultado " + v + " está fuera del rango de un Entero (máximo " + _MAX + ").");
  return v;
}
function _real(v, l) {
  if (!Number.isFinite(v)) throw new _Error(l, "El resultado de la operación es demasiado grande para un Real.");
  return v;
}
function _dividir(a, b, l) {
  if (b === 0) throw new _Error(l, "División por cero.");
  return _real(a / b, l);
}
function _cerca(a, b) {
  return Math.abs(a - b) <= Math.max(1e-9 * Math.max(Math.abs(a), Math.abs(b)), 1e-12);
}
function _cat(s, l) {
  if (s.length > %(MAXTXTO)d) throw new _Error(l, "El texto resultante es demasiado largo (máximo %(MAXTXTO)d de caracteres).");
  return s;
}
function _fmt(x) {
  if (Math.abs(x) < 5e-11) return "0,0";
  let s;
  if (Math.abs(x) >= 1e21) {
    s = BigInt(x).toString() + ".0";
  } else {
    s = x.toFixed(10);
    const t = x.toFixed(100);                       // desarrollo decimal exacto
    const p = t.indexOf(".");
    if (/^50*$/.test(t.slice(p + 11))) {             // empate exacto: se redondea al par (como en Python)
      const base = t.slice(0, p + 11);
      if ((base.charCodeAt(base.length - 1) - 48) %% 2 === 0) s = base;
    }
    s = s.replace(/0+$/, "");
  }
  if (s.endsWith(".")) s += "0";
  return s.replace(".", ",");
}
function _fmtl(b) { return b ? "Verdadero" : "Falso"; }
function _v(valor, nombre, l) {
  if (valor === undefined) throw new _Error(l, "La variable '" + nombre + "' no tiene valor en este punto de la ejecución.");
  return valor;
}

async function _pedir(validar) {
  for (;;) {
    const r = validar(await _leerLinea());
    if (r[0]) return r[1];
    _escribir("Valor no válido: " + r[1]);
  }
}
function _valEntero(t) {
  t = t.trim();
  if (!/^[+-]?[0-9]+$/.test(t)) return [false, "Se esperaba un número entero (por ejemplo 25), sin decimales ni letras."];
  const dig = t.replace(/^[+-]/, "").replace(/^0+/, "") || "0";
  if (dig.length > 10 || Math.abs(Number(t)) > _MAX) return [false, "El entero está fuera de rango (máximo " + _MAX + ")."];
  return [true, Number(t)];
}
function _valReal(t) {
  t = t.trim();
  if (!/^[+-]?[0-9]+([,.][0-9]+)?$/.test(t)) return [false, "Se esperaba un número real, con coma decimal (por ejemplo 3,5)."];
  const v = Number(t.replace(",", "."));
  if (!Number.isFinite(v)) return [false, "El número está fuera de rango."];
  return [true, v];
}
function _valLogico(t) {
  const m = t.trim().toLowerCase();
  if (m === "verdadero") return [true, true];
  if (m === "falso") return [true, false];
  return [false, "Se esperaba Verdadero o Falso."];
}
function _valTexto(t) {
  if (t.length > %(MAXTXT)d) return [false, "El texto es demasiado largo (máximo %(MAXTXT)d caracteres)."];
  return [true, t];
}
const _leerEntero = () => _pedir(_valEntero);
const _leerReal = () => _pedir(_valReal);
const _leerLogico = () => _pedir(_valLogico);
const _leerTexto = () => _pedir(_valTexto);
''' % {"MAX": ENTERO_MAXIMO, "MAXTXT": MAXIMO_TEXTO_ENTRADA, "MAXTXTO": MAXIMO_TEXTO}

JS_NODE = '''\
const _rl = require("readline").createInterface({ input: process.stdin, terminal: false });
const _it = _rl[Symbol.asyncIterator]();
function _escribir(t) { console.log(t); }
async function _leerLinea() {
  const r = await _it.next();
  if (r.done) throw new _Fin();
  return r.value;
}
'''

JS_NODE_FINAL = '''
(async () => {
  let codigo = 0;
  try {
    await principal();
  } catch (e) {
    if (e instanceof _Error) console.error("Error de ejecución (línea " + e.linea + "): " + e.mensaje);
    else if (e instanceof _Fin) console.error("Error de ejecución: el programa esperaba un dato y no hay más datos.");
    else throw e;
    codigo = 1;
  } finally {
    _rl.close();
  }
  process.exitCode = codigo;
})();
'''

JS_HTML = '''\
const _salida = document.getElementById("salida");
function _linea_html(texto, clase) {
  const d = document.createElement("div");
  d.className = "l" + (clase ? " " + clase : "");
  d.textContent = texto;
  _salida.appendChild(d);
  window.scrollTo(0, document.body.scrollHeight);
  return d;
}
function _escribir(t) { _linea_html(t, ""); }
function _leerLinea() {
  return new Promise((resolver) => {
    const fila = document.createElement("div");
    fila.className = "l entrada";
    fila.appendChild(document.createTextNode("› "));
    const campo = document.createElement("input");
    campo.type = "text";
    campo.autocomplete = "off";
    campo.spellcheck = false;
    fila.appendChild(campo);
    _salida.appendChild(fila);
    campo.focus();
    campo.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const valor = campo.value;
      const s = document.createElement("span");
      s.textContent = valor;
      campo.replaceWith(s);
      resolver(valor);
    });
  });
}
'''

JS_HTML_FINAL = '''
(async () => {
  try {
    await principal();
    _linea_html("", "");
    _linea_html("Proceso finalizado correctamente.", "ok");
  } catch (e) {
    _linea_html("", "");
    if (e instanceof _Error) _linea_html("Error de ejecución (línea " + e.linea + "): " + e.mensaje, "mal");
    else if (e instanceof _Fin) _linea_html("Error de ejecución: el programa esperaba un dato.", "mal");
    else _linea_html("Error inesperado: " + e, "mal");
  }
})();
'''


def _lit_json(t):
    # Literal de cadena válido en JavaScript y Java (los caracteres raros van como \\uXXXX)
    return json.dumps(t, ensure_ascii=True)


class GenJS(Generador):
    def lit_num(self, valor, tipo):
        return valor if tipo == "Entero" else valor.replace(",", ".")

    def lit_txt(self, t):
        return _lit_json(t)

    def lit_log(self, b):
        return "true" if b else "false"

    def leer_var(self, n):
        v = "v_" + n["nombre"]
        return f'_v({v}, {_lit_json(n["nombre"])}, {n["linea"]})' if n.get("riesgosa") else v

    def negar(self, c, tipo, linea):
        return f"_ent(-{c}, {linea})" if tipo == "Entero" else f"(-{c})"

    def arit_ent(self, op, a, b, linea):
        return f"_ent(({a} {op} {b}), {linea})"

    def arit_real(self, op, a, b, linea):
        return f"_real(({a} {op} {b}), {linea})"

    def dividir(self, a, b, linea):
        return f"_dividir({a}, {b}, {linea})"

    def concat(self, a, b, linea):
        return f"_cat(({a} + {b}), {linea})"

    def conv_texto(self, c, tipo):
        return {"Entero": f"String({c})", "Real": f"_fmt({c})", "Logico": f"_fmtl({c})"}[tipo]

    def a_real(self, c):
        return c

    def cmp_num(self, op, a, b, real):
        if not real:
            return f"({a} {op} {b})"
        return {
            "==": f"_cerca({a}, {b})", "!=": f"(!_cerca({a}, {b}))",
            "<": f"({a} < {b} && !_cerca({a}, {b}))", ">": f"({a} > {b} && !_cerca({a}, {b}))",
            "<=": f"({a} <= {b} || _cerca({a}, {b}))", ">=": f"({a} >= {b} || _cerca({a}, {b}))",
        }[op]

    def cmp_txt(self, op, a, b):
        return f"({a} {'===' if op == '==' else '!=='} {b})"

    cmp_log = cmp_txt

    def vacio(self, nivel):
        pass

    def decl(self, n, nivel):
        self.emitir(f'let v_{n["nombre"]};', nivel)

    def asig(self, n, nivel):
        self.emitir(f'v_{n["nombre"]} = {self.valor_para(n["nombre"], n["valor"])};', nivel)

    def lect(self, n, nivel):
        c = {"Entero": "_leerEntero()", "Real": "_leerReal()", "Texto": "_leerTexto()",
             "Logico": "_leerLogico()"}[n["tipo_dato"]]
        self.emitir(f'v_{n["nombre"]} = await {c};', nivel)

    def msg(self, n, nivel):
        self.emitir(f'_escribir({self.texto_de(n["valor"])});', nivel)

    def si(self, n, nivel):
        self.emitir(f'if ({self.expr(n["condicion"])}) {{', nivel)
        self.bloque(n["entonces"], nivel + 1)
        if n.get("sino"):
            self.emitir("} else {", nivel)
            self.bloque(n["sino"], nivel + 1)
        self.emitir("}", nivel)

    def cuerpo(self):
        self.emitir("async function principal() {", 0)
        self.bloque(self.arbol["instrucciones"], 1)
        self.emitir("}", 0)
        return "\n".join(self.lineas)

    def generar(self):
        return (
            "#!/usr/bin/env node\n"
            "// Programa generado por el compilador Costeñol.\n"
            "// Para ejecutarlo:  node programa.js\n"
            '"use strict";\n\n' + JS_COMUN + "\n" + JS_NODE + "\n" + self.cuerpo() + "\n" + JS_NODE_FINAL
        )


PLANTILLA_HTML = '''\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Programa Costeñol</title>
<style>
  body { margin: 0; background: #0b1220; color: #e8eefc; font-family: "Segoe UI", system-ui, sans-serif; }
  header { background: #0b3a78; padding: 0.8rem 1.2rem; font-weight: 600; }
  header small { font-weight: 400; opacity: 0.8; margin-left: 0.6rem; }
  #salida { background: #000; min-height: 60vh; padding: 1rem 1.2rem; font: 1.05rem/1.5 Consolas, "Cascadia Mono", monospace; }
  .l { white-space: pre-wrap; word-break: break-word; min-height: 1.5em; }
  .ok { color: #4cf06f; } .mal { color: #ff6b61; }
  .entrada { color: #6fd3ff; }
  .entrada input { font: inherit; color: #fff; background: #0b1424; border: 1px solid #2d5ea8; border-radius: 4px; padding: 0 0.4rem; width: 60%%; }
  footer { padding: 0.8rem 1.2rem; }
  button { font: inherit; padding: 0.4rem 1rem; border-radius: 6px; border: 1px solid #2d5ea8; background: #12408a; color: #fff; cursor: pointer; }
</style>
</head>
<body>
<header>Programa Costeñol<small>generado por el compilador</small></header>
<div id="salida"></div>
<footer><button onclick="location.reload()">Ejecutar de nuevo</button></footer>
<script>
"use strict";
%(codigo)s
</script>
</body>
</html>
'''


class GenHTML(GenJS):
    def generar(self):
        codigo = JS_COMUN + "\n" + JS_HTML + "\n" + self.cuerpo() + "\n" + JS_HTML_FINAL
        # nada dentro del script puede cerrar la etiqueta <script> ni abrir un comentario HTML
        codigo = codigo.replace("</", "<\\/").replace("<!--", "<\\!--")
        return PLANTILLA_HTML % {"codigo": codigo}


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------

JAVA_RUNTIME = '''\
    static final long MAX = %(MAX)dL;

    static class ErrorEjecucion extends RuntimeException {
        final int linea;
        ErrorEjecucion(int linea, String mensaje) { super(mensaje); this.linea = linea; }
    }
    static class Fin extends RuntimeException {}

    static PrintStream out;
    static BufferedReader in;

    static long ent(long v, int l) {
        if (Math.abs(v) > MAX) throw new ErrorEjecucion(l, "El resultado " + v + " está fuera del rango de un Entero (máximo " + MAX + ").");
        return v;
    }
    static double real(double v, int l) {
        if (Double.isInfinite(v) || Double.isNaN(v)) throw new ErrorEjecucion(l, "El resultado de la operación es demasiado grande para un Real.");
        return v;
    }
    static double dividir(double a, double b, int l) {
        if (b == 0) throw new ErrorEjecucion(l, "División por cero.");
        return real(a / b, l);
    }
    static boolean cerca(double a, double b) {
        return Math.abs(a - b) <= Math.max(1e-9 * Math.max(Math.abs(a), Math.abs(b)), 1e-12);
    }
    static String fmt(double x) {
        if (Math.abs(x) < 5e-11) return "0,0";
        String s = new BigDecimal(x).setScale(10, RoundingMode.HALF_EVEN).toPlainString();
        int fin = s.length();
        while (fin > 0 && s.charAt(fin - 1) == '0') fin--;
        s = s.substring(0, fin);
        if (s.endsWith(".")) s += "0";
        return s.replace('.', ',');
    }
    static String fmtl(boolean b) { return b ? "Verdadero" : "Falso"; }
    static String cat(String s, int l) {
        if (s.length() > %(MAXTXTO)d) throw new ErrorEjecucion(l, "El texto resultante es demasiado largo (máximo %(MAXTXTO)d de caracteres).");
        return s;
    }

    static long val(boolean ok, long v, String n, int l) { exigir(ok, n, l); return v; }
    static double val(boolean ok, double v, String n, int l) { exigir(ok, n, l); return v; }
    static String val(boolean ok, String v, String n, int l) { exigir(ok, n, l); return v; }
    static boolean val(boolean ok, boolean v, String n, int l) { exigir(ok, n, l); return v; }
    static void exigir(boolean ok, String n, int l) {
        if (!ok) throw new ErrorEjecucion(l, "La variable '" + n + "' no tiene valor en este punto de la ejecución.");
    }

    static String linea() throws IOException {
        String s = in.readLine();
        if (s == null) throw new Fin();
        return s;
    }
    static boolean digitos(String t, boolean decimal) {
        int i = 0, n = t.length();
        if (i < n && (t.charAt(i) == '+' || t.charAt(i) == '-')) i++;
        int ini = i;
        while (i < n && t.charAt(i) >= '0' && t.charAt(i) <= '9') i++;
        if (i == ini) return false;
        if (i == n) return true;
        if (!decimal || (t.charAt(i) != ',' && t.charAt(i) != '.')) return false;
        i++;
        int ini2 = i;
        while (i < n && t.charAt(i) >= '0' && t.charAt(i) <= '9') i++;
        return i > ini2 && i == n;
    }
    static long leerEntero() throws IOException {
        for (;;) {
            String t = linea().strip();
            if (!digitos(t, false)) { out.println("Valor no válido: Se esperaba un número entero (por ejemplo 25), sin decimales ni letras."); continue; }
            String d = t.replaceFirst("^[+-]", "").replaceFirst("^0+", "");
            if (d.isEmpty()) d = "0";
            if (d.length() > 10 || Math.abs(Long.parseLong(t.startsWith("+") ? t.substring(1) : t)) > MAX) {
                out.println("Valor no válido: El entero está fuera de rango (máximo " + MAX + ")."); continue;
            }
            return Long.parseLong(t.startsWith("+") ? t.substring(1) : t);
        }
    }
    static double leerReal() throws IOException {
        for (;;) {
            String t = linea().strip();
            if (!digitos(t, true)) { out.println("Valor no válido: Se esperaba un número real, con coma decimal (por ejemplo 3,5)."); continue; }
            double v = Double.parseDouble(t.replace(',', '.'));
            if (Double.isInfinite(v) || Double.isNaN(v)) { out.println("Valor no válido: El número está fuera de rango."); continue; }
            return v;
        }
    }
    static boolean leerLogico() throws IOException {
        for (;;) {
            String m = linea().strip().toLowerCase(java.util.Locale.ROOT);
            if (m.equals("verdadero")) return true;
            if (m.equals("falso")) return false;
            out.println("Valor no válido: Se esperaba Verdadero o Falso.");
        }
    }
    static String leerTexto() throws IOException {
        for (;;) {
            String t = linea();
            if (t.length() > %(MAXTXT)d) { out.println("Valor no válido: El texto es demasiado largo (máximo %(MAXTXT)d caracteres)."); continue; }
            return t;
        }
    }
''' % {"MAX": ENTERO_MAXIMO, "MAXTXT": MAXIMO_TEXTO_ENTRADA, "MAXTXTO": MAXIMO_TEXTO}

TIPOS_JAVA = {"Entero": "long", "Real": "double", "Texto": "String", "Logico": "boolean"}


class GenJava(Generador):
    def lit_num(self, valor, tipo):
        return valor + "L" if tipo == "Entero" else valor.replace(",", ".")

    def lit_txt(self, t):
        return _lit_json(t)

    def lit_log(self, b):
        return "true" if b else "false"

    def leer_var(self, n):
        v = "v_" + n["nombre"]
        if n.get("riesgosa"):
            return f'val(ok_{n["nombre"]}, {v}, {_lit_json(n["nombre"])}, {n["linea"]})'
        return v

    def negar(self, c, tipo, linea):
        return f"ent(-{c}, {linea})" if tipo == "Entero" else f"(-{c})"

    def arit_ent(self, op, a, b, linea):
        return f"ent(({a} {op} {b}), {linea})"

    def arit_real(self, op, a, b, linea):
        return f"real(({a} {op} {b}), {linea})"

    def dividir(self, a, b, linea):
        return f"dividir((double) {a}, (double) {b}, {linea})"

    def concat(self, a, b, linea):
        return f"cat(({a} + {b}), {linea})"

    def conv_texto(self, c, tipo):
        return {"Entero": f"String.valueOf({c})", "Real": f"fmt({c})", "Logico": f"fmtl({c})"}[tipo]

    def a_real(self, c):
        return f"(double) {c}"

    def cmp_num(self, op, a, b, real):
        if not real:
            return f"({a} {op} {b})"
        return {
            "==": f"cerca({a}, {b})", "!=": f"(!cerca({a}, {b}))",
            "<": f"({a} < {b} && !cerca({a}, {b}))", ">": f"({a} > {b} && !cerca({a}, {b}))",
            "<=": f"({a} <= {b} || cerca({a}, {b}))", ">=": f"({a} >= {b} || cerca({a}, {b}))",
        }[op]

    def cmp_txt(self, op, a, b):
        return f"{a}.equals({b})" if op == "==" else f"(!{a}.equals({b}))"

    def cmp_log(self, op, a, b):
        return f"({a} {op} {b})"

    def vacio(self, nivel):
        pass

    def decl(self, n, nivel):
        pass            # las variables son campos estáticos (se declaran arriba)

    def _marcar(self, nombre, nivel):
        if nombre in self.riesgosas:
            self.emitir(f"ok_{nombre} = true;", nivel)

    def asig(self, n, nivel):
        self.emitir(f'v_{n["nombre"]} = {self.valor_para(n["nombre"], n["valor"])};', nivel)
        self._marcar(n["nombre"], nivel)

    def lect(self, n, nivel):
        c = {"Entero": "leerEntero()", "Real": "leerReal()", "Texto": "leerTexto()",
             "Logico": "leerLogico()"}[n["tipo_dato"]]
        if self.vars[n["nombre"]] == "Real" and n["tipo_dato"] == "Entero":
            c = f"(double) {c}"
        self.emitir(f'v_{n["nombre"]} = {c};', nivel)
        self._marcar(n["nombre"], nivel)

    def msg(self, n, nivel):
        self.emitir(f'out.println({self.texto_de(n["valor"])});', nivel)

    def si(self, n, nivel):
        self.emitir(f'if ({self.expr(n["condicion"])}) {{', nivel)
        self.bloque(n["entonces"], nivel + 1)
        if n.get("sino"):
            self.emitir("} else {", nivel)
            self.bloque(n["sino"], nivel + 1)
        self.emitir("}", nivel)

    def generar(self):
        campos = []
        for nombre, tipo in self.vars.items():
            campos.append(f"    static {TIPOS_JAVA[tipo]} v_{nombre};")
            if nombre in self.riesgosas:
                campos.append(f"    static boolean ok_{nombre};")
        self.emitir("    static void principal() throws IOException {", 0)
        self.bloque(self.arbol["instrucciones"], 2)
        self.emitir("    }", 0)
        principal = "\n".join(self.lineas)
        return (
            "// Programa generado por el compilador Costeñol.\n"
            "// Para compilarlo y ejecutarlo:  javac Programa.java   y luego   java Programa\n"
            "// (En Windows, si ve símbolos raros en lugar de tildes, escriba antes:  chcp 65001)\n"
            "import java.io.*;\n"
            "import java.math.BigDecimal;\n"
            "import java.math.RoundingMode;\n"
            "import java.nio.charset.StandardCharsets;\n\n"
            "public class Programa {\n"
            + JAVA_RUNTIME + "\n" + "\n".join(campos) + "\n\n" + principal + "\n\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        out = new PrintStream(new FileOutputStream(FileDescriptor.out), true, \"UTF-8\");\n"
            "        in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));\n"
            "        try {\n"
            "            principal();\n"
            "        } catch (ErrorEjecucion e) {\n"
            "            System.err.println(\"Error de ejecución (línea \" + e.linea + \"): \" + e.getMessage());\n"
            "            System.exit(1);\n"
            "        } catch (Fin e) {\n"
            "            System.err.println(\"Error de ejecución: el programa esperaba un dato y no hay más datos.\");\n"
            "            System.exit(1);\n"
            "        }\n"
            "    }\n"
            "}\n"
        )


def construir_jar(fuente_java):
    """Compila Programa.java y lo empaqueta en un .jar ejecutable. Devuelve los bytes."""
    javac, jar = _herramienta("javac"), _herramienta("jar")
    if not (javac and jar):
        raise ErrorExportacion(
            "Para crear el .jar hace falta un JDK (los programas javac y jar) y no se encontró en este computador. "
            "Instale un JDK, o exporte «Java (código fuente)» y compílelo donde tenga uno.", 501)
    ocultar = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    with tempfile.TemporaryDirectory() as carpeta:
        fuente = os.path.join(carpeta, "Programa.java")
        with open(fuente, "w", encoding="utf-8", newline="\n") as f:
            f.write(fuente_java)
        try:
            r = subprocess.run([javac, "-encoding", "UTF-8", "-d", carpeta, fuente], cwd=carpeta,
                               capture_output=True, text=True, timeout=90, **ocultar)
        except (OSError, subprocess.TimeoutExpired):
            raise ErrorExportacion("No se pudo ejecutar el compilador de Java (javac).", 500)
        if r.returncode != 0:
            raise ErrorExportacion("El compilador de Java rechazó el código generado: " + (r.stderr or r.stdout)[:400], 500)
        clases = sorted(n for n in os.listdir(carpeta) if n.endswith(".class"))
        destino = os.path.join(carpeta, "salida.jar")
        try:
            r = subprocess.run([jar, "cfe", destino, "Programa"] + clases, cwd=carpeta,
                               capture_output=True, text=True, timeout=60, **ocultar)
        except (OSError, subprocess.TimeoutExpired):
            raise ErrorExportacion("No se pudo ejecutar la herramienta jar.", 500)
        if r.returncode != 0 or not os.path.isfile(destino):
            raise ErrorExportacion("No se pudo crear el archivo .jar: " + (r.stderr or r.stdout)[:400], 500)
        with open(destino, "rb") as f:
            return f.read()


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def nombre_base(nombre):
    base = os.path.splitext(os.path.basename(str(nombre or "")))[0]
    limpio = "".join(c if (c.isalnum() or c in "_-") and ord(c) < 128 or c in "ñÑ" else "_" for c in base).strip("_")
    return (limpio or "programa")[:60]


def exportar(arbol, formato, nombre=None):
    """Genera el archivo. Devuelve {archivo, contenido (bytes), mime, aviso, como}."""
    base = nombre_base(nombre)
    info = {f["id"]: f for f in formatos()}.get(formato)
    if info is None:
        raise ErrorExportacion("Formato de exportación desconocido.", 400)

    if formato == "python":
        texto, mime = GenPython(arbol).generar(), "text/x-python; charset=utf-8"
    elif formato == "javascript":
        texto, mime = GenJS(arbol).generar(), "text/javascript; charset=utf-8"
    elif formato == "html":
        texto, mime = GenHTML(arbol).generar(), "text/html; charset=utf-8"
    else:
        texto, mime = GenJava(arbol).generar(), "text/x-java-source; charset=utf-8"

    if formato == "java_jar":
        contenido, mime = construir_jar(texto), "application/java-archive"
        archivo = base + ".jar"
    elif formato == "java_fuente":
        contenido, archivo = texto.encode("utf-8"), "Programa.java"      # el nombre debe coincidir con la clase
    else:
        contenido, archivo = texto.encode("utf-8"), base + info["extension"]

    return {"archivo": archivo, "contenido": contenido, "mime": mime,
            "como": info["como"].format(archivo=archivo)}
