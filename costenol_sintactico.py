# -*- coding: utf-8 -*-
"""
Costeñol - Analizador sintáctico (fase 2)

Recibe los tokens del analizador léxico, comprueba que estén en el orden que
exige el lenguaje y construye el árbol sintáctico (AST).

Gramática (cada instrucción simple termina en ;):

    programa      := { instruccion }
    instruccion   := declaracion | asignacion | lectura | mensaje | condicional
    declaracion   := NOMBRE TIPO ;                        TIPO: Texto Entero Real Logico
    asignacion    := NOMBRE = expresion ;
    lectura       := NOMBRE = Captura . TIPO ( ) ;
    mensaje       := Mensaje . Texto ( expresion ) ;
    condicional   := Si  ( expresion )  { instruccion }  [ Sino { instruccion } ]  FinSi
    expresion     := aditiva [ OP_RELACIONAL aditiva ]
    aditiva       := termino { (+ | -) termino }
    termino       := unario { (* | /) unario }
    unario        := [ + | - ] unario | primario
    primario      := NUMERO | CADENA | Verdadero | Falso | NOMBRE | ( expresion )

Reglas del enunciado que se aplican al pie de la letra:
  * Si va seguido de un espacio y del paréntesis de apertura.
  * Sino y FinSi se escriben tal cual y solos en su línea (se permiten comentarios).
  * Todo Si termina con FinSi.
  * Las declaraciones van fuera de los Si.

El analizador nunca lanza excepciones: todo problema es un diagnóstico con su
línea y columna, y tras cada error se recupera para seguir buscando más.
"""

from costenol_lexico import (
    Diagnostico, ERROR, ADVERTENCIA, COMENTARIO, PALABRA_RESERVADA, IDENTIFICADOR,
    NUMERO_ENTERO, NUMERO_REAL, CADENA, VALOR_LOGICO, OPERADOR_ASIGNACION,
    OPERADOR_RELACIONAL, OPERADOR_ARITMETICO, PARENTESIS_APERTURA, PARENTESIS_CIERRE,
    PUNTO_Y_COMA, PUNTO, MAXIMO_ERRORES, _sugerencia_reservada,
)

TIPOS_DE_DATO = ("Texto", "Entero", "Real", "Logico")

# Límites para que ningún programa agote la memoria de llamadas.
MAXIMO_ANIDAMIENTO = 40        # paréntesis / signos / Si dentro de Si
MAXIMO_OPERACIONES = 150       # operadores en una misma instrucción


class _Falla(Exception):
    """Error ya registrado: sirve para salir de la instrucción y recuperarse."""


class _Abortar(Exception):
    """Error tan grave que se detiene todo el análisis sintáctico."""


def describir(t) -> str:
    """Describe un token en lenguaje natural para los mensajes."""
    if t is None:
        return "el final del programa"
    valor = t.valor if len(t.valor) <= 30 else t.valor[:27] + "…"
    if t.tipo == IDENTIFICADOR:
        return f"el nombre '{valor}'"
    if t.tipo == PALABRA_RESERVADA:
        return f"la palabra reservada '{valor}'"
    if t.tipo == VALOR_LOGICO:
        return f"el valor '{valor}'"
    if t.tipo in (NUMERO_ENTERO, NUMERO_REAL):
        return f"el número {valor}"
    if t.tipo == CADENA:
        return f"el texto {valor}"
    return f"el símbolo '{valor}'"


def _nodo(tipo, pos, **campos):
    linea, columna = pos
    d = {"nodo": tipo, "linea": linea, "columna": columna}
    d.update(campos)
    return d


class Parser:
    def __init__(self, tokens):
        self.t = [x for x in tokens if x.tipo != COMENTARIO]
        self.i = 0
        self.errores = []
        self.avisos = []
        self._lleno = False
        self.prof = 0          # anidamiento actual
        self.ops = 0           # operadores de la instrucción actual

    # -- utilidades -------------------------------------------------------------
    def actual(self, k=0):
        j = self.i + k
        return self.t[j] if 0 <= j < len(self.t) else None

    def avanzar(self):
        t = self.actual()
        self.i += 1
        return t

    def es(self, t, tipo, valor=None):
        return t is not None and t.tipo == tipo and (valor is None or t.valor == valor)

    def es_reservada(self, t, *valores):
        return t is not None and t.tipo == PALABRA_RESERVADA and t.valor in valores

    def _fin_anterior(self):
        if not self.t:
            return (1, 1)
        p = self.t[min(self.i, len(self.t)) - 1] if self.i > 0 else self.t[0]
        if self.i == 0:
            return (p.linea, p.columna)
        return (p.linea, p.columna + len(p.valor))

    def _pos(self, x):
        if isinstance(x, tuple):
            return x
        if x is None:
            return self._fin_anterior()
        return (x.linea, x.columna)

    def error(self, codigo, donde, mensaje):
        if len(self.errores) >= MAXIMO_ERRORES:
            if not self._lleno:
                self._lleno = True
                linea, col = self._pos(donde)
                self.avisos.append(Diagnostico(
                    ADVERTENCIA, "A-SIN-99", linea, col,
                    f"Se alcanzó el máximo de {MAXIMO_ERRORES} errores; los siguientes no se muestran."))
            return
        linea, col = self._pos(donde)
        self.errores.append(Diagnostico(ERROR, codigo, linea, col, mensaje))

    def fallar(self, codigo, donde, mensaje):
        self.error(codigo, donde, mensaje)
        raise _Falla()

    def sincronizar(self):
        """Salta hasta el final de la instrucción que falló."""
        inicio = self.i
        while True:
            t = self.actual()
            if t is None:
                return
            if t.tipo == PUNTO_Y_COMA:
                self.avanzar()
                return
            if self.i > inicio:
                if self.es_reservada(t, "Si", "Sino", "FinSi", "Mensaje"):
                    return
                anterior = self.t[self.i - 1]
                if t.tipo == IDENTIFICADOR and anterior.linea < t.linea:
                    return
            self.avanzar()

    def entrar(self, donde):
        self.prof += 1
        if self.prof > MAXIMO_ANIDAMIENTO:
            self.prof -= 1
            self.error("E-SIN-25", donde,
                       f"El programa es demasiado complejo: más de {MAXIMO_ANIDAMIENTO} niveles de "
                       "paréntesis o de Si dentro de Si. Se detuvo el análisis.")
            raise _Abortar()

    def salir(self):
        self.prof -= 1

    def contar_operacion(self, donde):
        self.ops += 1
        if self.ops > MAXIMO_OPERACIONES:
            self.fallar("E-SIN-25", donde,
                        f"La expresión es demasiado larga: más de {MAXIMO_OPERACIONES} operaciones en una "
                        "sola instrucción. Divídala en varias.")

    def nombre_reservado(self, tok):
        """Un nombre no puede ser una palabra reservada ni un tipo de dato, ni siquiera
        cambiando las mayúsculas (entero Entero; es un error)."""
        sug = _sugerencia_reservada(tok.valor)
        if sug is None:
            return False
        tipo = "un tipo de dato" if sug in TIPOS_DE_DATO else "una palabra reservada"
        mi = "mi" + sug
        self.error("E-SIN-27", tok,
                   f"El nombre '{tok.valor}' no es válido: una variable no puede llamarse como {tipo} "
                   f"('{sug}'), ni siquiera cambiando las mayúsculas o minúsculas. Use otro nombre, "
                   f"por ejemplo '{mi}'.")
        return True

    @staticmethod
    def _fin_de_operando(t):
        return t.tipo in (NUMERO_ENTERO, NUMERO_REAL, CADENA, VALOR_LOGICO, IDENTIFICADOR, PARENTESIS_CIERRE)

    @staticmethod
    def _inicio_de_operando(t):
        return t.tipo in (NUMERO_ENTERO, NUMERO_REAL, CADENA, VALOR_LOGICO, IDENTIFICADOR, PARENTESIS_APERTURA)

    def verificar_pegado(self, instruccion=True):
        """Dos valores seguidos sin operador (1(  5 5  a b  (1+2)(3)) son un error."""
        t = self.actual()
        p = self.t[self.i - 1] if self.i > 0 else None
        if t is None or p is None or t.linea != p.linea:
            return
        if self._fin_de_operando(p) and self._inicio_de_operando(t):
            extra = ""
            if t.tipo == PARENTESIS_APERTURA:
                extra = (" Un paréntesis no puede ir pegado a un valor: escriba un operador antes, por ejemplo "
                         "1 * (2 + 3).")
            elif instruccion:
                extra = " Si eran dos instrucciones distintas, lo que falta es el ';' después del primer valor."
            self.fallar("E-SIN-28", t,
                        f"Falta un operador (+ - * /) entre {describir(p)} y {describir(t)}.{extra}")

    def verificar_solo(self, tok):
        """Sino y FinSi deben ir solos en su línea (se permiten comentarios)."""
        sig = self.actual()
        if sig is not None and sig.linea == tok.linea:
            self.error("E-SIN-12", sig,
                       f"'{tok.valor}' debe ir solo en su línea (después solo puede haber un comentario). "
                       f"Se encontró {describir(sig)} a continuación.")

    # -- programa -----------------------------------------------------------------
    def programa(self):
        instrucciones = self.instrucciones(False)
        return _nodo("Programa", (1, 1), instrucciones=instrucciones)

    def instrucciones(self, dentro_de_si):
        lista = []
        while self.actual() is not None:
            t = self.actual()
            if self.es_reservada(t, "Sino", "FinSi"):
                if dentro_de_si:
                    break
                self.error("E-SIN-10", t,
                           f"'{t.valor}' aparece sin un Si abierto antes. "
                           f"{'Sino' if t.valor == 'Sino' else 'FinSi'} solo se usa dentro de Si (condición) … FinSi.")
                self.avanzar()
                self.verificar_solo(t)
                continue
            if t.tipo == IDENTIFICADOR:
                sug = _sugerencia_reservada(t.valor)
                sig = self.actual(1)
                if sug in ("Si", "Sino", "FinSi") and (
                        sig is None or sig.linea > t.linea or self.es(sig, PARENTESIS_APERTURA)):
                    self.error("E-SIN-26", t,
                               f"'{t.valor}' no es una instrucción de Costeñol. ¿Quiso decir '{sug}'? "
                               "Las mayúsculas y minúsculas importan: las palabras reservadas se escriben exactamente así.")
                    self.t[self.i] = type(t)(PALABRA_RESERVADA, sug, t.linea, t.columna)   # se sigue como si estuviera bien
                    continue
            inicio = self.i
            n = self.instruccion(dentro_de_si)
            if n is not None:
                lista.append(n)
            if self.i == inicio:          # garantía de progreso
                self.avanzar()
        return lista

    def instruccion(self, dentro_de_si):
        t = self.actual()
        self.ops = 0
        try:
            if t.tipo == PALABRA_RESERVADA:
                if t.valor == "Si":
                    return self.condicional()
                if t.valor == "Mensaje":
                    return self.mensaje()
                if t.valor == "Captura":
                    self.fallar("E-SIN-14", t,
                                "El valor leído con Captura debe guardarse en una variable: "
                                "nombre = Captura.Tipo(); (por ejemplo edad = Captura.Entero();).")
                if t.valor in TIPOS_DE_DATO:
                    self.fallar("E-SIN-23", t,
                                f"'{t.valor}' es un tipo de dato: no puede ser el nombre de una variable ni ir al "
                                f"principio de una instrucción. La forma correcta es: nombre {t.valor};")
            if t.tipo == IDENTIFICADOR:
                sig = self.actual(1)
                if sig is not None and sig.tipo == PALABRA_RESERVADA and sig.valor in TIPOS_DE_DATO:
                    return self.declaracion(dentro_de_si)
                if sig is not None and sig.tipo == OPERADOR_ASIGNACION:
                    return self.asignacion()
                self._identificador_suelto(t, sig)
            if t.tipo == PUNTO_Y_COMA:
                self.error("E-SIN-22", t, "Hay un ';' de más: no hay ninguna instrucción antes de él.")
                self.avanzar()
                return None
            if t.tipo == PALABRA_RESERVADA or t.tipo == VALOR_LOGICO:
                self.fallar("E-SIN-19", t,
                            f"{describir(t).capitalize()} no puede iniciar una instrucción aquí. "
                            "Una instrucción empieza con un nombre de variable, Mensaje o Si.")
            self.fallar("E-SIN-02", t,
                        f"Una instrucción no puede empezar con {describir(t)}. "
                        "Debe empezar con un nombre de variable, Mensaje o Si.")
        except _Falla:
            self.sincronizar()
            return None

    def _identificador_suelto(self, t, sig):
        nombre = t.valor
        sugerida = _sugerencia_reservada(nombre)
        if sugerida is not None:
            self.fallar("E-SIN-26", t,
                        f"'{nombre}' no es una instrucción de Costeñol. ¿Quiso decir '{sugerida}'? "
                        "Las mayúsculas y minúsculas importan: las palabras reservadas se escriben exactamente así.")
        if sig is not None and sig.tipo == IDENTIFICADOR:
            tipo_sugerido = _sugerencia_reservada(sig.valor)
            if tipo_sugerido in TIPOS_DE_DATO:
                self.fallar("E-SIN-26", sig,
                            f"'{sig.valor}' no es un tipo de dato válido porque las mayúsculas importan: "
                            f"se escribe {tipo_sugerido}. La forma correcta es: {nombre} {tipo_sugerido};")
        if sig is not None and sig.tipo == OPERADOR_RELACIONAL and sig.valor == "==":
            self.fallar("E-SIN-03", sig,
                        f"Para darle un valor a '{nombre}' use un solo =. El doble == es solo para comparar dentro de Si.")
        if sig is not None and sig.tipo == PARENTESIS_APERTURA:
            self.fallar("E-SIN-20", t,
                        f"'{nombre}' no es una instrucción de Costeñol. Las únicas con paréntesis son "
                        "Captura.Tipo() y Mensaje.Texto(...).")
        if sig is not None and sig.tipo == PUNTO:
            self.fallar("E-SIN-20", t,
                        f"'{nombre}.' no es válido: solo Captura y Mensaje llevan punto "
                        "(Captura.Entero(), Mensaje.Texto(...)).")
        self.fallar("E-SIN-03", sig if sig is not None else self._fin_anterior(),
                    f"Después del nombre '{nombre}' se esperaba un tipo de dato (Texto, Entero, Real o Logico) "
                    f"para declararla, o el signo = para asignarle un valor; se encontró {describir(sig)}.")

    # -- instrucciones simples ------------------------------------------------------
    def fin_instruccion(self):
        t = self.actual()
        if t is not None and t.tipo == PUNTO_Y_COMA:
            self.avanzar()
            return
        if t is not None and t.tipo == PARENTESIS_CIERRE:
            self.fallar("E-SIN-05", t, "Sobra un paréntesis de cierre ')': no hay un '(' que lo abra.")
        anterior = self.t[self.i - 1] if self.i > 0 else None
        mismo_renglon = t is not None and anterior is not None and t.linea == anterior.linea
        self.error("E-SIN-01", self._fin_anterior(),
                   f"Falta el ';' al final de la instrucción (se encontró {describir(t)}).")
        if mismo_renglon:
            raise _Falla()

    def declaracion(self, dentro_de_si):
        nombre = self.avanzar()
        tipo = self.avanzar()
        self.nombre_reservado(nombre)
        if dentro_de_si:
            self.error("E-SIN-16", nombre,
                       f"La variable '{nombre.valor}' se declara dentro de un Si. "
                       "Las variables se declaran al inicio del programa, fuera de los Si.")
        self.fin_instruccion()
        return _nodo("Declaracion", (nombre.linea, nombre.columna), nombre=nombre.valor, tipo_dato=tipo.valor)

    def asignacion(self):
        nombre = self.avanzar()
        igual = self.avanzar()
        self.nombre_reservado(nombre)
        t = self.actual()
        if self.es_reservada(t, "Captura"):
            tipo = self.captura()
            sig = self.actual()
            if sig is not None and sig.tipo in (OPERADOR_ARITMETICO, OPERADOR_RELACIONAL):
                self.fallar("E-SIN-24", sig,
                            "El valor leído con Captura debe guardarse solo, sin operaciones en la misma instrucción. "
                            f"Primero escriba {nombre.valor} = Captura.{tipo}(); y luego use la variable.")
            self.fin_instruccion()
            return _nodo("Lectura", (nombre.linea, nombre.columna), nombre=nombre.valor, tipo_dato=tipo)
        valor = self.expresion(tras_igual=igual)
        self.verificar_pegado()
        self.fin_instruccion()
        return _nodo("Asignacion", (nombre.linea, nombre.columna), nombre=nombre.valor, valor=valor)

    def captura(self):
        self.avanzar()  # Captura
        t = self.actual()
        if not self.es(t, PUNTO):
            self.fallar("E-SIN-14", t if t is not None else self._fin_anterior(),
                        "Después de Captura debe ir un punto y el tipo: Captura.Texto(), Captura.Entero(), "
                        f"Captura.Real() o Captura.Logico(). Se encontró {describir(t)}.")
        self.avanzar()
        t = self.actual()
        if t is not None and t.tipo == PALABRA_RESERVADA and t.valor in TIPOS_DE_DATO:
            tipo = t.valor
            self.avanzar()
        else:
            pista = ""
            if t is not None and t.tipo == IDENTIFICADOR and _sugerencia_reservada(t.valor) in TIPOS_DE_DATO:
                pista = (f" ¿Quiso decir '{_sugerencia_reservada(t.valor)}'? "
                         "Las mayúsculas importan: el tipo se escribe con la primera letra en mayúscula.")
            self.fallar("E-SIN-14", t if t is not None else self._fin_anterior(),
                        f"Captura no tiene la opción {t.valor if t is not None else 'indicada'}"
                        f"{'' if t is not None else ' (se encontró el final del programa)'}. "
                        f"Las opciones son Texto, Entero, Real y Logico.{pista}")
        t = self.actual()
        if not self.es(t, PARENTESIS_APERTURA):
            self.fallar("E-SIN-14", t if t is not None else self._fin_anterior(),
                        f"Falta el paréntesis de apertura: Captura.{tipo}(). Se encontró {describir(t)}.")
        self.avanzar()
        t = self.actual()
        if not self.es(t, PARENTESIS_CIERRE):
            self.fallar("E-SIN-14", t if t is not None else self._fin_anterior(),
                        f"Captura.{tipo}() lleva los paréntesis vacíos y cerrados. Se encontró {describir(t)}.")
        self.avanzar()
        return tipo

    def mensaje(self):
        m = self.avanzar()
        t = self.actual()
        if not self.es(t, PUNTO):
            self.fallar("E-SIN-15", t if t is not None else self._fin_anterior(),
                        f"Después de Mensaje debe ir un punto y Texto: Mensaje.Texto(\"...\"). Se encontró {describir(t)}.")
        self.avanzar()
        t = self.actual()
        if not self.es_reservada(t, "Texto"):
            pista = ""
            if t is not None and t.tipo == IDENTIFICADOR and _sugerencia_reservada(t.valor) == "Texto":
                pista = " Las mayúsculas importan: se escribe Texto con la T mayúscula."
            self.fallar("E-SIN-15", t if t is not None else self._fin_anterior(),
                        f"Mensaje solo tiene la opción Texto: Mensaje.Texto(...). Se encontró {describir(t)}.{pista}")
        self.avanzar()
        t = self.actual()
        if not self.es(t, PARENTESIS_APERTURA):
            self.fallar("E-SIN-15", t if t is not None else self._fin_anterior(),
                        f"Falta el paréntesis de apertura: Mensaje.Texto(...). Se encontró {describir(t)}.")
        abre = self.avanzar()
        if self.es(self.actual(), PARENTESIS_CIERRE):
            self.fallar("E-SIN-15", self.actual(),
                        "Mensaje.Texto() está vacío: escriba entre los paréntesis el texto o el valor que quiere "
                        "mostrar, por ejemplo Mensaje.Texto(\"Hola\");")
        valor = self.expresion()
        self.verificar_pegado(False)
        t = self.actual()
        if not self.es(t, PARENTESIS_CIERRE):
            self.fallar("E-SIN-05", self._fin_anterior(),
                        f"Falta el paréntesis de cierre ')' de Mensaje.Texto( (se encontró {describir(t)}).")
        self.avanzar()
        self.fin_instruccion()
        return _nodo("Mensaje", (m.linea, m.columna), valor=valor)

    # -- condicional ---------------------------------------------------------------
    def condicional(self):
        t_si = self.avanzar()
        sig = self.actual()
        condicion = None
        if not self.es(sig, PARENTESIS_APERTURA):
            self.error("E-SIN-06", (t_si.linea, t_si.columna + len(t_si.valor)),
                       "Después de Si debe ir un espacio y la condición entre paréntesis: Si (condición). "
                       f"Se encontró {describir(sig)}.")
            self._saltar_renglon(t_si.linea)
        else:
            if sig.linea == t_si.linea and sig.columna == t_si.columna + len(t_si.valor):
                self.error("E-SIN-13", sig,
                           "Falta un espacio entre Si y el paréntesis: se escribe Si (condición), "
                           "con un espacio antes del '('.")
            abre = self.avanzar()
            try:
                if self.es(self.actual(), PARENTESIS_CIERRE):
                    self.fallar("E-SIN-07", self.actual(),
                                "La condición está vacía: escriba algo entre los paréntesis, "
                                "por ejemplo Si (edad >= 18).")
                condicion = self.expresion()
                self.verificar_pegado(False)
                t = self.actual()
                if self.es(t, OPERADOR_ASIGNACION):
                    self.fallar("E-SIN-17", t,
                                "Dentro de Si, un solo = es asignación. Para comparar use == (igual), "
                                "!= (distinto), <, >, <= o >=.")
                if self.es(t, PARENTESIS_CIERRE):
                    self.avanzar()
                else:
                    self.fallar("E-SIN-08", self._fin_anterior(),
                                f"Falta el paréntesis de cierre ')' de la condición (se encontró {describir(t)}).")
            except _Falla:
                condicion = condicion if isinstance(condicion, dict) else None
                self._saltar_renglon(t_si.linea)

        self.entrar(t_si)
        entonces = self.instrucciones(True)
        sino = None
        linea_sino = None
        while self.es_reservada(self.actual(), "Sino"):
            t_sino = self.avanzar()
            self.verificar_solo(t_sino)
            if linea_sino is not None:
                self.error("E-SIN-11", t_sino,
                           f"Este Si ya tiene un Sino (línea {linea_sino}); solo se permite uno por cada Si.")
            else:
                linea_sino = t_sino.linea
            bloque = self.instrucciones(True)
            if sino is None:
                sino = bloque
        self.salir()
        t = self.actual()
        if self.es_reservada(t, "FinSi"):
            self.avanzar()
            self.verificar_solo(t)
            linea_fin = t.linea
        else:
            self.error("E-SIN-09", t_si,
                       "Este Si no tiene su FinSi: todo Si debe terminar con FinSi, solo, en su propia línea.")
            linea_fin = None
        return _nodo("Condicional", (t_si.linea, t_si.columna), condicion=condicion,
                     entonces=entonces, sino=sino, tiene_sino=linea_sino is not None, linea_fin=linea_fin)

    def _saltar_renglon(self, linea):
        while self.actual() is not None and self.actual().linea == linea:
            self.avanzar()

    # -- expresiones ---------------------------------------------------------------
    def expresion(self, tras_igual=None):
        if tras_igual is not None and self.es(self.actual(), PUNTO_Y_COMA):
            self.fallar("E-SIN-04", self.actual(),
                        "Falta el valor que se asigna: escriba algo después del = (un número, un texto, "
                        "Verdadero/Falso, otra variable o una operación).")
        izq = self.aditiva()
        t = self.actual()
        if self.es(t, OPERADOR_RELACIONAL):
            op = self.avanzar()
            self.contar_operacion(op)
            der = self.aditiva()
            nodo = _nodo("Binario", (op.linea, op.columna), op=op.valor, izq=izq, der=der)
            if self.es(self.actual(), OPERADOR_RELACIONAL):
                self.fallar("E-SIN-18", self.actual(),
                            "No se pueden encadenar comparaciones (a < b < c). Haga una sola comparación por condición.")
            return nodo
        return izq

    def aditiva(self):
        izq = self.termino()
        while self.es(self.actual(), OPERADOR_ARITMETICO) and self.actual().valor in "+-":
            op = self.avanzar()
            self.contar_operacion(op)
            der = self.termino()
            izq = _nodo("Binario", (op.linea, op.columna), op=op.valor, izq=izq, der=der)
        return izq

    def termino(self):
        izq = self.unario()
        while self.es(self.actual(), OPERADOR_ARITMETICO) and self.actual().valor in "*/":
            op = self.avanzar()
            self.contar_operacion(op)
            der = self.unario()
            izq = _nodo("Binario", (op.linea, op.columna), op=op.valor, izq=izq, der=der)
        return izq

    def unario(self):
        t = self.actual()
        if self.es(t, OPERADOR_ARITMETICO) and t.valor in "+-":
            op = self.avanzar()
            self.contar_operacion(op)
            self.entrar(op)
            operando = self.unario()
            self.salir()
            return _nodo("Unario", (op.linea, op.columna), op=op.valor, operando=operando)
        return self.primario()

    def primario(self):
        t = self.actual()
        if t is None:
            self.fallar("E-SIN-04", self._fin_anterior(),
                        "Falta un valor: el programa termina antes de completar la expresión.")
        if t.tipo == NUMERO_ENTERO:
            self.avanzar()
            return _nodo("Numero", (t.linea, t.columna), valor=t.valor, tipo_dato="Entero")
        if t.tipo == NUMERO_REAL:
            self.avanzar()
            return _nodo("Numero", (t.linea, t.columna), valor=t.valor, tipo_dato="Real")
        if t.tipo == CADENA:
            self.avanzar()
            return _nodo("Cadena", (t.linea, t.columna), valor=t.valor[1:-1])
        if t.tipo == VALOR_LOGICO:
            self.avanzar()
            return _nodo("Logico", (t.linea, t.columna), valor=(t.valor == "Verdadero"))
        if t.tipo == IDENTIFICADOR:
            sig = self.actual(1)
            sugerida = _sugerencia_reservada(t.valor)
            if sugerida in ("Captura", "Mensaje") and self.es(sig, PUNTO):
                self.fallar("E-SIN-26", t,
                            f"'{t.valor}' no es válido: ¿quiso decir '{sugerida}'? "
                            "Las mayúsculas y minúsculas importan.")
            if self.es(sig, PARENTESIS_APERTURA):
                self.fallar("E-SIN-20", t,
                            f"'{t.valor}' no es una función de Costeñol. Las únicas con paréntesis son "
                            "Captura.Tipo() y Mensaje.Texto(...).")
            if self.nombre_reservado(t):
                raise _Falla()
            self.avanzar()
            return _nodo("Variable", (t.linea, t.columna), nombre=t.valor)
        if t.tipo == PARENTESIS_APERTURA:
            self.avanzar()
            if self.es(self.actual(), PARENTESIS_CIERRE):
                self.fallar("E-SIN-04", self.actual(), "Los paréntesis están vacíos: falta el valor que va dentro.")
            sig = self.actual()
            if sig is None or self.es(sig, PUNTO_Y_COMA):
                self.fallar("E-SIN-05", sig if sig is not None else self._fin_anterior(),
                            f"Falta completar y cerrar el paréntesis que se abrió en la línea {t.linea}, "
                            f"columna {t.columna}: después del '(' debe ir un valor y luego el ')'.")
            self.entrar(t)
            e = self.expresion()
            self.salir()
            if self.es(self.actual(), PARENTESIS_CIERRE):
                self.avanzar()
                return e
            self.fallar("E-SIN-05", self._fin_anterior(),
                        f"Falta cerrar el paréntesis que se abrió en la línea {t.linea}, columna {t.columna} "
                        f"(se encontró {describir(self.actual())}).")
        if t.tipo == PALABRA_RESERVADA:
            if t.valor in ("Captura", "Mensaje"):
                que = ("Captura solo puede usarse así: variable = Captura.Tipo();"
                       if t.valor == "Captura" else
                       "Mensaje.Texto(...) muestra un valor pero no devuelve ninguno, así que no se puede usar dentro de una expresión.")
                self.fallar("E-SIN-21", t, que)
            self.fallar("E-SIN-19", t,
                        f"'{t.valor}' es una palabra reservada: no se puede usar como nombre de variable ni como valor.")
        if t.tipo == PUNTO_Y_COMA:
            self.fallar("E-SIN-04", self._fin_anterior(), "Falta un valor antes del ';'.")
        if t.tipo == PARENTESIS_CIERRE:
            self.fallar("E-SIN-04", t, "Falta un valor antes del paréntesis de cierre ')'.")
        self.fallar("E-SIN-04", t,
                    "Se esperaba un valor (número, texto, Verdadero/Falso, nombre de variable o paréntesis) "
                    f"y se encontró {describir(t)}.")


def analizar_sintaxis(tokens):
    """Devuelve (arbol, errores, advertencias). Nunca lanza excepciones."""
    try:
        p = Parser(tokens)
        try:
            arbol = p.programa()
        except _Abortar:
            return None, p.errores, p.avisos
        return arbol, p.errores, p.avisos
    except Exception as exc:  # defensa final
        err = Diagnostico(ERROR, "E-SIN-97", 1, 1,
                          f"Error interno del analizador sintáctico ({type(exc).__name__}: {exc}). "
                          "El programa sigue activo.")
        return None, [err], []


CATALOGO = {
    "E-SIN-01": ("Falta el punto y coma",
                 "Toda instrucción simple (declarar, asignar, leer, mostrar) termina con ;",
                 "Agregue ; al final de la instrucción."),
    "E-SIN-02": ("Instrucción mal iniciada",
                 "Una instrucción empezó con un símbolo, número o texto que no corresponde.",
                 "Empiece con el nombre de una variable, Mensaje o Si."),
    "E-SIN-03": ("Falta el tipo o el signo =",
                 "Después del nombre de una variable debe ir un tipo (para declararla) o = (para asignarle un valor).",
                 "Declare así: edad Entero;   Asigne así: edad = 5;"),
    "E-SIN-04": ("Falta un valor",
                 "Se esperaba un número, texto, Verdadero/Falso, variable o paréntesis y no estaba.",
                 "Complete la expresión: x = 5 + 3;"),
    "E-SIN-05": ("Paréntesis sin pareja",
                 "Falta cerrar un paréntesis, o sobra uno de cierre.",
                 "Cuente los paréntesis: cada ( debe tener su )."),
    "E-SIN-06": ("Falta el paréntesis después de Si",
                 "Después de Si debe ir un espacio y la condición entre paréntesis.",
                 "Escriba: Si (condición)"),
    "E-SIN-07": ("Condición vacía",
                 "Los paréntesis de Si no tienen nada dentro.",
                 "Escriba una condición: Si (edad >= 18)"),
    "E-SIN-08": ("Falta el paréntesis de cierre de la condición",
                 "La condición de Si no se cierra con ).",
                 "Cierre el paréntesis: Si (edad >= 18)"),
    "E-SIN-09": ("Si sin FinSi",
                 "Todo Si debe terminar con FinSi.",
                 "Agregue FinSi (solo, en su línea) donde termina el condicional."),
    "E-SIN-10": ("Sino o FinSi sin Si",
                 "Aparece Sino o FinSi sin que haya un Si abierto antes.",
                 "Quítelo, o agregue el Si que le corresponde."),
    "E-SIN-11": ("Sino repetido",
                 "Un Si solo puede tener un Sino.",
                 "Deje un solo Sino por cada Si."),
    "E-SIN-12": ("Sino/FinSi no está solo en su línea",
                 "Sino y FinSi se escriben tal cual, solos en su línea (se permite un comentario después).",
                 "Ponga lo que sigue en la línea de abajo."),
    "E-SIN-13": ("Falta el espacio después de Si",
                 "Si va seguido de un espacio y luego el paréntesis.",
                 "Escriba Si (condición) y no Si(condición)."),
    "E-SIN-14": ("Captura mal escrita",
                 "Captura se usa así: variable = Captura.Tipo(); con Tipo = Texto, Entero, Real o Logico.",
                 "Ejemplo: edad = Captura.Entero();"),
    "E-SIN-15": ("Mensaje mal escrito",
                 "Mensaje se usa así: Mensaje.Texto(valor);",
                 "Ejemplo: Mensaje.Texto(\"Hola Mundo\");"),
    "E-SIN-16": ("Variable declarada dentro de un Si",
                 "Las variables se declaran al inicio del programa, fuera de los Si.",
                 "Mueva la declaración antes del Si."),
    "E-SIN-17": ("Un solo = dentro de la condición",
                 "Dentro de Si, = es asignación y no comparación.",
                 "Use == para comparar igualdad: Si (a == 5)"),
    "E-SIN-18": ("Comparaciones encadenadas",
                 "No se puede escribir a < b < c.",
                 "Haga una sola comparación por condición."),
    "E-SIN-19": ("Palabra reservada mal usada",
                 "Una palabra reservada se usó como nombre, valor o inicio de instrucción.",
                 "Use otro nombre para la variable."),
    "E-SIN-20": ("Función inexistente",
                 "Costeñol solo tiene Captura.Tipo() y Mensaje.Texto(...); no hay otras funciones.",
                 "Use solo esas instrucciones."),
    "E-SIN-21": ("Captura/Mensaje dentro de una expresión",
                 "Captura y Mensaje no pueden usarse dentro de operaciones o dentro de otro Mensaje.",
                 "Guarde primero el valor en una variable y luego úsela."),
    "E-SIN-22": ("Punto y coma de más",
                 "Hay un ; sin instrucción antes.",
                 "Borre el ; sobrante."),
    "E-SIN-23": ("Un tipo de dato al inicio de la instrucción",
                 "La instrucción empieza con un tipo (Entero, Texto…) en lugar del nombre de la variable. Un tipo de dato no puede usarse como nombre.",
                 "Escriba primero el nombre: edad Entero;"),
    "E-SIN-24": ("Operación junto a Captura",
                 "El valor leído con Captura debe guardarse solo, sin operar en la misma línea.",
                 "Escriba n = Captura.Entero(); y en otra línea m = n + 1;"),
    "E-SIN-25": ("Programa demasiado complejo",
                 "Hay demasiados paréntesis o Si anidados (máximo 40), o más de 150 operaciones en una instrucción.",
                 "Divida la instrucción en varias."),
    "E-SIN-26": ("Mayúsculas o minúsculas mal escritas",
                 "Una palabra reservada o un tipo de dato se escribió con otras mayúsculas (por ejemplo entero en vez de Entero). Costeñol distingue mayúsculas y minúsculas.",
                 "Escriba la palabra exactamente así: Entero, Texto, Real, Logico, Captura, Mensaje, Si, Sino, FinSi."),
    "E-SIN-27": ("Nombre igual a una palabra reservada o a un tipo",
                 "Una variable no puede llamarse como un tipo de dato (Entero, Texto, Real, Logico) ni como otra palabra reservada, tampoco cambiando mayúsculas o minúsculas: entero Entero; es un error.",
                 "Use otro nombre: miEntero Entero;"),
    "E-SIN-28": ("Falta un operador entre dos valores",
                 "Hay dos valores seguidos sin operador entre ellos: por ejemplo 1( o 5 5. Un número no puede ir pegado a un paréntesis ni a otro valor.",
                 "Escriba un operador: 1 * (2 + 3)   o   5 + 5. Si eran dos instrucciones, agregue el ;"),
    "E-SIN-97": ("Error interno del analizador sintáctico",
                 "Falló algo inesperado en el programa.",
                 "Vuelva a intentarlo; si se repite, avise al equipo desarrollador."),
    "A-SIN-99": ("Demasiados errores",
                 "Se alcanzó el máximo de 200 errores sintácticos.",
                 "Corrija los primeros y vuelva a compilar."),
}
