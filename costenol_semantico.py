# -*- coding: utf-8 -*-
"""
Costeñol - Analizador semántico (fase 3)

Recorre el árbol sintáctico y comprueba que el programa tenga sentido:

  * toda variable se declara antes de usarse y una sola vez;
  * los valores guardados corresponden al tipo de la variable;
  * las operaciones y comparaciones se hacen entre tipos compatibles;
  * la condición de Si es Verdadero o Falso (tipo Logico);
  * Captura.Tipo() corresponde al tipo de la variable que recibe el dato;
  * una variable no se usa antes de darle un valor;
  * no se divide por un cero escrito en el código.

Tipos y reglas:
    Entero  (+ - * entre Entero da Entero; / siempre da Real)
    Real    (si se mezcla Entero con Real, el resultado es Real)
    Texto   (+ une textos; si un lado es Texto, el otro se convierte a texto)
    Logico  (Verdadero / Falso y el resultado de las comparaciones)

    Se puede guardar un Entero en una variable Real; nada más se convierte solo.
    == y != comparan números con números, Texto con Texto, Logico con Logico.
    < > <= >= solo comparan números.
"""

from costenol_lexico import Diagnostico, ERROR, ADVERTENCIA, MAXIMO_ERRORES

NUMERICOS = ("Entero", "Real")
OPERADORES_RELACIONALES = ("==", "!=", "<", ">", "<=", ">=")
ORDEN = ("<", ">", "<=", ">=")


def compatible(destino, origen) -> bool:
    return destino == origen or (destino == "Real" and origen == "Entero")


class Analizador:
    def __init__(self):
        self.tabla = {}
        self.minusculas = {}        # nombre en minúsculas -> primera variable con ese nombre
        self.errores = []
        self.avisos = []
        self.definidas = set()      # variables con valor en TODOS los caminos
        self.posibles = set()       # variables con valor en ALGÚN camino
        self._avisadas = set()
        self._lleno = False

    # -- diagnósticos -----------------------------------------------------------
    def error(self, codigo, nodo, mensaje):
        if len(self.errores) >= MAXIMO_ERRORES:
            if not self._lleno:
                self._lleno = True
                self.avisos.append(Diagnostico(
                    ADVERTENCIA, "A-SEM-99", nodo["linea"], nodo["columna"],
                    f"Se alcanzó el máximo de {MAXIMO_ERRORES} errores; los siguientes no se muestran."))
            return
        self.errores.append(Diagnostico(ERROR, codigo, nodo["linea"], nodo["columna"], mensaje))

    def aviso(self, codigo, nodo, mensaje):
        self.avisos.append(Diagnostico(ADVERTENCIA, codigo, nodo["linea"], nodo["columna"], mensaje))

    # -- programa -----------------------------------------------------------------
    def analizar(self, arbol):
        self.bloque(arbol["instrucciones"])
        for s in self.tabla.values():
            nodo = {"linea": s["linea"], "columna": s["columna"]}
            if not s["usada"] and not s["asignada"]:
                self.aviso("A-SEM-01", nodo, f"La variable '{s['nombre']}' se declara pero nunca se usa.")
            elif s["asignada"] and not s["usada"]:
                self.aviso("A-SEM-03", nodo,
                           f"A la variable '{s['nombre']}' se le asigna un valor, pero nunca se usa "
                           "(no se muestra ni se compara).")
        self.avisos.sort(key=lambda d: (d.linea, d.columna))

    def bloque(self, instrucciones):
        for ins in instrucciones:
            self.instruccion(ins)

    def instruccion(self, n):
        k = n["nodo"]
        if k == "Declaracion":
            self.declaracion(n)
        elif k == "Asignacion":
            self.asignacion(n)
        elif k == "Lectura":
            self.lectura(n)
        elif k == "Mensaje":
            self.expr(n["valor"])
        elif k == "Condicional":
            self.condicional(n)

    # -- instrucciones --------------------------------------------------------------
    def declaracion(self, n):
        nombre = n["nombre"]
        previa = self.tabla.get(nombre)
        if previa is not None:
            self.error("E-SEM-02", n,
                       f"La variable '{nombre}' ya fue declarada en la línea {previa['linea']} "
                       f"(como {previa['tipo']}). Cada variable se declara una sola vez.")
            return
        parecida = self.minusculas.get(nombre.lower())
        if parecida is not None:
            self.aviso("A-SEM-05", n,
                       f"'{nombre}' se parece a '{parecida['nombre']}' (línea {parecida['linea']}): "
                       "Costeñol distingue mayúsculas y minúsculas, por eso son variables distintas.")
        else:
            self.minusculas[nombre.lower()] = {"nombre": nombre, "linea": n["linea"]}
        self.tabla[nombre] = {"nombre": nombre, "tipo": n["tipo_dato"], "linea": n["linea"],
                              "columna": n["columna"], "usada": False, "asignada": False}

    def asignacion(self, n):
        tipo_valor = self.expr(n["valor"])
        simbolo = self.simbolo_destino(n)
        if simbolo is None:
            return
        if tipo_valor is not None and not compatible(simbolo["tipo"], tipo_valor):
            self.error("E-SEM-03", n,
                       f"No se puede guardar un valor {tipo_valor} en '{n['nombre']}', que es {simbolo['tipo']}."
                       f"{self._ayuda_tipos(simbolo['tipo'], tipo_valor)}")
        self.marcar_asignada(simbolo)

    def lectura(self, n):
        simbolo = self.simbolo_destino(n)
        if simbolo is None:
            return
        if not compatible(simbolo["tipo"], n["tipo_dato"]):
            self.error("E-SEM-08", n,
                       f"Captura.{n['tipo_dato']}() lee un valor {n['tipo_dato']}, pero '{n['nombre']}' es "
                       f"{simbolo['tipo']}. Use Captura.{simbolo['tipo']}().")
        self.marcar_asignada(simbolo)

    def simbolo_destino(self, n):
        simbolo = self.tabla.get(n["nombre"])
        if simbolo is None:
            self.error("E-SEM-01", n,
                       f"La variable '{n['nombre']}' no fue declarada. Decláresela antes con: "
                       f"{n['nombre']} Tipo;  (por ejemplo {n['nombre']} Entero;)")
        return simbolo

    def marcar_asignada(self, simbolo):
        simbolo["asignada"] = True
        self.definidas.add(simbolo["nombre"])
        self.posibles.add(simbolo["nombre"])

    def condicional(self, n):
        cond = n.get("condicion")
        if cond is not None:
            tipo = self.expr(cond)
            if tipo is not None and tipo != "Logico":
                self.error("E-SEM-05", cond,
                           f"La condición de Si debe dar Verdadero o Falso (tipo Logico), pero aquí es {tipo}. "
                           "Use una comparación, por ejemplo Si (edad >= 18).")
        antes_def, antes_pos = set(self.definidas), set(self.posibles)
        self.bloque(n["entonces"])
        def_then, pos_then = set(self.definidas), set(self.posibles)
        self.definidas, self.posibles = set(antes_def), set(antes_pos)
        if n.get("sino") is not None:
            self.bloque(n["sino"])
        def_else, pos_else = set(self.definidas), set(self.posibles)
        self.definidas = def_then & def_else
        self.posibles = pos_then | pos_else

    # -- expresiones ----------------------------------------------------------------
    def expr(self, n):
        """Devuelve el tipo de la expresión, o None si hubo un error.
        Además anota el nodo con su tipo (tipo_expr): lo usa el exportador."""
        t = self._expr(n)
        n["tipo_expr"] = t
        return t

    def _expr(self, n):
        k = n["nodo"]
        if k == "Numero":
            return n["tipo_dato"]
        if k == "Cadena":
            return "Texto"
        if k == "Logico":
            return "Logico"
        if k == "Variable":
            return self.variable(n)
        if k == "Unario":
            t = self.expr(n["operando"])
            if t is None:
                return None
            if t not in NUMERICOS:
                self.error("E-SEM-04", n,
                           f"El signo '{n['op']}' solo se puede usar con números, no con {t}.")
                return None
            return t
        if k == "Binario":
            return self.binario(n)
        return None

    def variable(self, n):
        simbolo = self.tabla.get(n["nombre"])
        if simbolo is None:
            self.error("E-SEM-01", n,
                       f"La variable '{n['nombre']}' no fue declarada. Decláresela antes con: "
                       f"{n['nombre']} Tipo;  (por ejemplo {n['nombre']} Entero;)")
            return None
        simbolo["usada"] = True
        if n["nombre"] not in self.definidas:
            if n["nombre"] in self.posibles:
                n["riesgosa"] = True       # puede no tener valor: el exportador la revisa al ejecutar
                if n["nombre"] not in self._avisadas:
                    self._avisadas.add(n["nombre"])
                    self.aviso("A-SEM-02", n,
                               f"La variable '{n['nombre']}' solo recibe valor en algunos caminos del programa "
                               "(dentro de un Si). Si no lo recibe, la ejecución se detendrá con un error.")
            else:
                self.error("E-SEM-09", n,
                           f"La variable '{n['nombre']}' se usa antes de asignarle un valor. "
                           f"Asígnele un valor ({n['nombre']} = ...;) o léalo con Captura antes de usarla.")
        return simbolo["tipo"]

    def binario(self, n):
        op = n["op"]
        izq = self.expr(n["izq"])
        der = self.expr(n["der"])
        if op == "/":
            self._division_por_cero(n)
        if izq is None or der is None:
            return None
        if op in OPERADORES_RELACIONALES:
            return self.comparacion(n, op, izq, der)
        if op == "+" and (izq == "Texto" or der == "Texto"):
            return "Texto"
        if izq in NUMERICOS and der in NUMERICOS:
            if op == "/":
                return "Real"
            return "Entero" if (izq == "Entero" and der == "Entero") else "Real"
        self.error("E-SEM-04", n,
                   f"El operador '{op}' solo se puede usar con números"
                   f"{' (o con Texto para unir textos)' if op == '+' else ''}; "
                   f"aquí se usa con {izq} y {der}.")
        return None

    def comparacion(self, n, op, izq, der):
        if op in ORDEN:
            if izq in NUMERICOS and der in NUMERICOS:
                return "Logico"
            self.error("E-SEM-07", n,
                       f"El operador '{op}' solo compara números; aquí se usa con {izq} y {der}. "
                       "Para Texto y Logico solo existen == y !=.")
            return None
        if (izq in NUMERICOS and der in NUMERICOS) or izq == der:
            return "Logico"
        self.error("E-SEM-06", n, f"No se puede comparar {izq} con {der}: deben ser del mismo tipo.")
        return None

    def _division_por_cero(self, n):
        der = n["der"]
        if der["nodo"] == "Numero" and float(der["valor"].replace(",", ".")) == 0:
            self.error("E-SEM-10", n, "División por cero: el divisor es 0.")

    @staticmethod
    def _ayuda_tipos(destino, origen):
        if destino == "Entero" and origen == "Real":
            return " Un Real no cabe en un Entero; declare la variable como Real."
        if destino == "Texto":
            return " Para guardar un texto, escríbalo entre comillas."
        if origen == "Texto":
            return " Un texto no se puede guardar en una variable que no sea Texto."
        return ""


def analizar_semantica(arbol):
    """Devuelve (errores, advertencias, simbolos). Nunca lanza excepciones."""
    try:
        a = Analizador()
        a.analizar(arbol)
        simbolos = [dict(s) for s in a.tabla.values()]
        return a.errores, a.avisos, simbolos
    except Exception as exc:  # defensa final
        err = Diagnostico(ERROR, "E-SEM-97", 1, 1,
                          f"Error interno del analizador semántico ({type(exc).__name__}: {exc}). "
                          "El programa sigue activo.")
        return [err], [], []


CATALOGO = {
    "E-SEM-01": ("Variable no declarada",
                 "Se usa una variable que no se declaró antes.",
                 "Declárela al inicio: edad Entero;"),
    "E-SEM-02": ("Variable declarada dos veces",
                 "Ya existe una variable con ese nombre.",
                 "Use otro nombre o borre la declaración repetida."),
    "E-SEM-03": ("Tipos incompatibles al asignar",
                 "Se intenta guardar un valor de un tipo en una variable de otro tipo (por ejemplo un Texto en un Entero). Solo un Entero puede guardarse en un Real.",
                 "Use una variable del tipo correcto o cambie el valor."),
    "E-SEM-04": ("Operación no válida para esos tipos",
                 "Se usó + - * / con tipos que no lo permiten (por ejemplo restar Texto).",
                 "Las operaciones aritméticas son solo para números; + también une textos."),
    "E-SEM-05": ("La condición no es Verdadero/Falso",
                 "La condición de Si debe dar un valor Logico (una comparación o una variable Logico).",
                 "Use una comparación: Si (edad >= 18)"),
    "E-SEM-06": ("Comparación entre tipos distintos",
                 "Se comparan valores de tipos que no se pueden comparar (por ejemplo Texto con Entero).",
                 "Compare números con números, Texto con Texto, Logico con Logico."),
    "E-SEM-07": ("Orden entre tipos no numéricos",
                 "< > <= >= solo funcionan con números.",
                 "Para Texto y Logico use == o !=."),
    "E-SEM-08": ("Captura no coincide con la variable",
                 "El tipo de Captura.Tipo() no corresponde al de la variable que recibe el dato.",
                 "Use Captura con el mismo tipo de la variable: edad = Captura.Entero();"),
    "E-SEM-09": ("Variable sin valor",
                 "Se usa una variable antes de asignarle o leerle un valor.",
                 "Asigne un valor (x = 0;) o léalo (x = Captura.Entero();) antes de usarla."),
    "E-SEM-10": ("División por cero",
                 "El divisor escrito en el código es 0.",
                 "Cambie el divisor."),
    "E-SEM-97": ("Error interno del analizador semántico",
                 "Falló algo inesperado en el programa.",
                 "Vuelva a intentarlo; si se repite, avise al equipo desarrollador."),
    "A-SEM-01": ("Variable que nunca se usa", "La variable se declara pero no se usa para nada.", "Úsela o bórrela."),
    "A-SEM-02": ("Variable que puede no tener valor",
                 "Solo recibe valor dentro de un Si; si ese camino no se ejecuta, no tendrá valor.",
                 "Asígnele un valor inicial antes del Si."),
    "A-SEM-03": ("Valor que nunca se usa", "Se le asigna un valor a la variable pero nunca se muestra ni se compara.", "Muéstrela con Mensaje.Texto o bórrela."),
    "A-SEM-05": ("Nombres que solo cambian en las mayúsculas",
                 "Dos variables se escriben igual salvo por mayúsculas/minúsculas; son distintas.",
                 "Use nombres claramente diferentes para evitar confusiones."),
    "A-SEM-99": ("Demasiados errores", "Se alcanzó el máximo de 200 errores semánticos.", "Corrija los primeros y vuelva a compilar."),
}
