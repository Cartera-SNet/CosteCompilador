# Manual de programador: compilador Costeñol

Este documento está escrito para **otro desarrollador** que reciba el proyecto y tenga que entenderlo, modificarlo o ampliarlo. Explica cómo está organizado (módulos y clases), cómo se nombran las cosas (prefijos y convenciones), cómo viaja un programa por el compilador y cómo agregar piezas nuevas. Al final hay una lista de preguntas frecuentes para la sustentación.

El manual del **usuario** está dentro del programa (botón *Manual de uso*, archivo `web/manual.html`).

---

## 1. Visión general

Costeñol es un lenguaje de programación educativo con instrucciones en español. El proyecto es un **compilador/intérprete con interfaz propia**:

```
 Navegador (web/)  ──HTTP/JSON──►  app.py  ──►  costenol_compilador.py
  editor, paneles                   servidor      │
                                                  ├─ 1. costenol_lexico.py       tokens
                                                  ├─ 2. costenol_sintactico.py   árbol (AST)
                                                  ├─ 3. costenol_semantico.py    tipos y variables
                                                  ├─ 4. costenol_ejecucion.py    ejecuta el AST
                                                  ├─ costenol_exportar.py        genera .py .js .html .java .jar
                                                  ├─ costenol_dialecto.py        mensajes en costeño
                                                  └─ costenol_asistente.py       asistente de IA (API de Anthropic)
```

* **Todo el análisis y la ejecución están en Python** (solo biblioteca estándar, sin paquetes externos).
* La carpeta `web/` (HTML, CSS y JavaScript) **solo dibuja** y llama a la API; no analiza código. Lo único de "lógica" que tiene el JavaScript es el resaltado de colores y el autocompletado (que son ayudas visuales).
* Una fase solo se ejecuta si la anterior terminó sin errores.

## 2. Estructura de carpetas ("paquetes")

| Ruta | Contenido |
|---|---|
| `app.py` | Servidor HTTP y arranque (modo local, modo nube, seguridad). Punto de entrada del `.exe` y de Railway. |
| `costenol_lexico.py` | **Fase 1.** Convierte el texto en tokens. |
| `costenol_sintactico.py` | **Fase 2.** Convierte los tokens en el árbol sintáctico. |
| `costenol_semantico.py` | **Fase 3.** Comprueba tipos, variables y condiciones; anota el árbol. |
| `costenol_ejecucion.py` | **Fase 4.** Intérprete: ejecuta el árbol (generador). |
| `costenol_compilador.py` | Une las fases (`compilar`) y maneja las sesiones de ejecución. |
| `costenol_dialecto.py` | Convierte cada error en una frase costeña. |
| `costenol_exportar.py` | Generadores de código para otros lenguajes. |
| `costenol_asistente.py` | Asistente de IA y su configuración. |
| `web/` | `index.html`, `estilos.css`, `app.js`, `movil.js`, `manual.html`, `manifest.webmanifest`, `assets/` (logos, íconos). |
| `ejemplos/` | Programas `.cst` de ejemplo (válidos y con errores). La primera línea es `// Ejemplo: Título //`. |
| `pruebas_*.py` | Pruebas automáticas (ver sección 10). |
| `ejecutar.bat`, `construir_exe.bat/.py` | Abrir en Windows y construir `Costenol.exe`. |
| `railway.json`, `Procfile`, `RAILWAY.md`… | Solo en el zip de Railway (ver sección 11). |

## 3. El lenguaje (gramática)

```
programa      := { instruccion }
instruccion   := declaracion | asignacion | lectura | mensaje | condicional
declaracion   := NOMBRE TIPO ;                      TIPO: Texto Entero Real Logico
asignacion    := NOMBRE = expresion ;
lectura       := NOMBRE = Captura . TIPO ( ) ;
mensaje       := Mensaje . Texto ( expresion ) ;
condicional   := Si ( expresion ) { instruccion } [ Sino { instruccion } ] FinSi
expresion     := aditiva [ OP_RELACIONAL aditiva ]
aditiva       := termino { (+ | -) termino }
termino       := unario { (* | /) unario }
unario        := [ + | - ] unario | primario
primario      := NUMERO | CADENA | Verdadero | Falso | NOMBRE | ( expresion )
```

Reglas que no se ven en la gramática (las implementan las fases indicadas):

| Regla | Fase | Código |
|---|---|---|
| Mayúsculas y minúsculas importan | léxica/sintáctica | E-SIN-26 |
| Un nombre no puede ser palabra reservada ni tipo (ni cambiando mayúsculas): `entero Entero;` es error | sintáctica | E-SIN-27 |
| `Si` va seguido de un espacio y `(`; `Sino` y `FinSi` solos en su línea; todo `Si` termina en `FinSi` | sintáctica | E-SIN-13/12/09 |
| Entre dos valores va un operador (`1(` es error); todo `(` se cierra | sintáctica | E-SIN-28/05 |
| Variables declaradas antes de usarse, una vez, fuera de los `Si` | sintáctica/semántica | E-SIN-16, E-SEM-01/02 |
| Tipos compatibles; `Entero` cabe en `Real`; `/` siempre da `Real` | semántica | E-SEM-03/04/06/07 |
| La condición del `Si` es `Logico` | semántica | E-SEM-05 |
| Una variable debe tener valor antes de usarse | semántica | E-SEM-09 |
| Decimales con coma; enteros hasta 2147483647 | léxica | E-LEX-05/07 |

## 4. Fase por fase: clases y funciones

### 4.1 `costenol_lexico.py`

| Elemento | Qué es |
|---|---|
| `Token(tipo, valor, linea, columna)` | Una pieza del programa. |
| `Diagnostico(nivel, codigo, linea, columna, mensaje)` | Error o advertencia (todas las fases lo usan). |
| `Resultado` | Tokens + errores + advertencias; método `a_dict()`. |
| `_Analizador` | Clase que recorre cada línea carácter por carácter (comentarios, cadenas, números, palabras, operadores). |
| `analizar(fuente)` | Función pública. **Nunca lanza excepciones.** |
| Constantes de tipos de token | `PALABRA_RESERVADA`, `IDENTIFICADOR`, `NUMERO_ENTERO`, `NUMERO_REAL`, `CADENA`, `VALOR_LOGICO`, `OPERADOR_ASIGNACION`, `OPERADOR_RELACIONAL`, `OPERADOR_ARITMETICO`, `PARENTESIS_APERTURA`, `PARENTESIS_CIERRE`, `PUNTO_Y_COMA`, `PUNTO`, `COMENTARIO`. |
| Constantes del lenguaje | `PALABRAS_RESERVADAS`, `VALORES_LOGICOS`, `OPERADORES_RELACIONALES`, `LONGITUD_MAXIMA_IDENTIFICADOR` (30), `ENTERO_MAXIMO`, `MAXIMO_ERRORES` (200). |

### 4.2 `costenol_sintactico.py`

| Elemento | Qué es |
|---|---|
| `Parser` | **Descenso recursivo.** Un método por regla de la gramática: `instrucciones`, `declaracion`, `asignacion`, `captura`, `mensaje`, `condicional`, `expresion`, `aditiva`, `termino`, `unario`, `primario`. |
| `_Falla` | Excepción interna: el error ya se registró; sirve para saltar a la recuperación. |
| `_Abortar` | Excepción interna para detener todo (programa demasiado anidado). |
| `sincronizar()` | **Recuperación de errores:** salta hasta el `;` o la siguiente instrucción para seguir buscando más errores sin llenar de falsos avisos. |
| `analizar_sintaxis(tokens)` | Función pública; devuelve `(arbol, errores, advertencias)`. |
| Límites | `MAXIMO_ANIDAMIENTO` (40) y `MAXIMO_OPERACIONES` (150) evitan desbordar la pila de Python. |

**Forma del árbol (AST).** Cada nodo es un diccionario con `nodo`, `linea` y `columna`:

| `nodo` | Campos propios |
|---|---|
| `Programa` | `instrucciones` |
| `Declaracion` | `nombre`, `tipo_dato` |
| `Asignacion` | `nombre`, `valor` (expresión) |
| `Lectura` | `nombre`, `tipo_dato` (el de `Captura.Tipo`) |
| `Mensaje` | `valor` |
| `Condicional` | `condicion`, `entonces`, `sino` (o `None`), `tiene_sino`, `linea_fin` |
| `Binario` | `op`, `izq`, `der` (aritmético o de comparación) |
| `Unario` | `op`, `operando` |
| `Numero` / `Cadena` / `Logico` / `Variable` | `valor` + `tipo_dato`, `valor`, `valor` (bool), `nombre` |

### 4.3 `costenol_semantico.py`

* `Analizador`: recorre el árbol con una **tabla de símbolos** (diccionario `nombre → {tipo, linea, usada, asignada}`).
* Calcula el tipo de cada expresión (`expr`) y **anota el árbol** con `tipo_expr` (lo usa el exportador) y `riesgosa` (variable que puede no tener valor).
* Análisis de flujo: conjuntos `definidas` (con valor en todos los caminos) y `posibles` (en algún camino) para detectar variables sin valor (error) o con valor solo en una rama (advertencia).
* `analizar_semantica(arbol)` → `(errores, advertencias, simbolos)`.

### 4.4 `costenol_ejecucion.py` (intérprete)

* `ejecutar(arbol)` es un **generador**: entrega eventos `{"evento": "salida", "texto": …}` y `{"evento": "entrada", "variable", "tipo_dato", "linea"}`; el que lo maneja le devuelve (con `send`) el dato leído.
* `evaluar(nodo, memoria)` evalúa expresiones. Errores de ejecución: `ErrorEjecucion` (códigos E-EJE-xx): variable sin valor, división por cero, entero/real fuera de rango, texto demasiado largo.
* `convertir_entrada(tipo, texto)` valida lo que escribe el usuario en `Captura` (si no sirve, se vuelve a pedir).
* `formato_real` / `a_texto`: cómo se muestran los números (coma decimal) y los lógicos.

### 4.5 `costenol_compilador.py`

* `compilar(codigo)` → diccionario con `exitoso`, `fase_fallida`, `tokens`, `errores`, `advertencias`, `arbol`, `simbolos`, `fases`. Corre las fases en orden y se detiene en la primera con errores.
* `Sesion` y `Sesiones`: una ejecución que puede **detenerse a pedir un dato** (se guarda el generador del intérprete entre peticiones HTTP). Tienen límite de cantidad y de vida.
* `publico(comp)` recorta lo que se manda al navegador (árbol enorme, etc.). Topes: 20 000 tokens, 500 advertencias, 5 000 símbolos, 20 000 nodos.
* `catalogo()` junta los `CATALOGO` de cada módulo (lo usa el manual).

### 4.6 `costenol_dialecto.py`

* `frase(codigo, linea, mensaje)` devuelve `"<reacción> en la línea N. Error <tipo>: <causa>"` (o `Advertencia:`). El formato es el que pidió el profesor.
* **Cada código tiene su propia reacción y su propia causa**, en las tablas `REACCIONES` y `CAUSAS`. La expresión costeña se escoge porque encaja con lo que pasó (falta algo → «Ajá, ¿y el…?»; algo no cuadra → «Ese cuento no me cuadra»; un límite → «Bájale dos»; un aviso → «Pilas»); lo que no encaja queda con «Ojo, compa». Las causas pueden usar `{q0}`, `{q1}` (lo que va entre comillas en el mensaje formal) y `{g1}`… (grupos de una expresión regular).
* `MENSAJES_PANTALLA` guarda las frases de la pantalla de salida (compilación limpia, ejecución terminada, dato no válido…); `web/app.js` usa esas mismas frases y una prueba comprueba que coincidan.
* «Tú eres la monda, manito» es un elogio y solo sale en `compilacion_limpia`; «¿Qué es esa monda, loco?» solo en cuatro errores. `PALABRAS_PROHIBIDAS` lista lo que nunca debe aparecer y `pruebas_dialecto.py` lo vigila.
* Si un código no tiene frase propia, se usa una reacción neutral y el mensaje formal como causa.

### 4.7 `costenol_exportar.py`

* `Generador` (clase base) recorre el árbol; cada subclase decide cómo se escribe cada cosa en su lenguaje:
  `GenPython`, `GenJS` (Node.js), `GenHTML` (hereda de `GenJS` y cambia la entrada/salida al navegador), `GenJava`.
* Usa `tipo_expr` (puesto por la fase semántica) para elegir conversiones y comparaciones exactas.
* `construir_jar()` llama a `javac` y `jar` del JDK (si existe). `formatos()` informa qué formatos hay disponibles. `exportar(arbol, formato, nombre)` devuelve el archivo.
* **Garantía:** cada formato se comporta igual que el intérprete (misma salida, mismos errores). `pruebas_exportar.py` lo comprueba comparando ambos.

### 4.8 `costenol_asistente.py`

* `INSTRUCCIONES`: texto con **todas las reglas del lenguaje** que recibe el modelo. Hay que actualizarlo cuando cambie el lenguaje.
* `responder(config, mensajes, codigo, errores)`: llama a la API de Anthropic, **compila el código que devuelve el modelo** y, si falla, se lo devuelve para que lo corrija (hasta 2 veces).
* `Configuracion`: guarda/lee la clave (`ia_config.json` o variable `ANTHROPIC_API_KEY`) y el modelo. La clave nunca se manda al navegador.

### 4.9 `app.py`

* `Manejador` (hereda de `BaseHTTPRequestHandler`): rutas, seguridad y respuestas JSON. `Estado`: datos compartidos (sesiones, modo, limitador). `Limitador`: límites de uso del asistente en la nube.
* Seguridad: se rechaza un `Host` ajeno (modo local), un `Origin` de otro sitio, y se envían cabeceras CSP y de protección. En la nube: la clave de IA no se puede cambiar desde la página, hay límites por persona y por día, y clave de acceso opcional (`ACCESO_USUARIO` + `ACCESO_CLAVE`).

## 5. Flujo de un programa

**Compilar / Ejecutar:** `app.js` → `POST /api/ejecutar` → `compilar()` (fases 1-3) → si no hay errores se crea una `Sesion` y se corre el generador de la fase 4 hasta que termine o pida un dato → respuesta JSON → el navegador pinta la salida. Si pide un dato: `POST /api/entrada` continúa la misma sesión.

**Exportar:** `POST /api/exportar` → `compilar()` → `exportar(arbol, formato)` → archivo en base64 → el navegador pregunta dónde guardarlo.

**Asistente:** `POST /api/asistente` → `responder()` → API de Anthropic → se compila el código de la respuesta → se devuelve el texto y el estado de cada bloque.

## 6. Convenciones y prefijos

**Idioma:** todo en español (nombres, mensajes, comentarios), sin tildes en identificadores de código.

**En el código Python**

| Convención | Ejemplo |
|---|---|
| Clases en `CamelCase` | `Parser`, `Analizador`, `GenPython` |
| Funciones y variables en `snake_case` | `analizar_sintaxis`, `tipo_expr` |
| Constantes en `MAYUSCULAS` | `ENTERO_MAXIMO`, `CATALOGO` |
| Prefijo `_` = privado de la clase o del módulo | `_Falla`, `_numero()` |
| Códigos de mensajes `E-FASE-nn` (error) y `A-FASE-nn` (advertencia) | `E-SIN-01`, `A-SEM-03` |
| Fases: `LEX` léxica, `SIN` sintáctica, `SEM` semántica, `EJE` ejecución | `E-EJE-02` |
| Tipos de token en `MAYUSCULAS_CON_GUION_BAJO` y en español | `NUMERO_REAL` |

**Prefijos en los programas exportados**

| Prefijo | Significa |
|---|---|
| `v_` | Toda variable de Costeñol (`edad` → `v_edad`), para que nunca choque con palabras reservadas del otro lenguaje. |
| `ok_` | (Java) bandera de «esta variable ya tiene valor». |
| `_` + nombre corto | (Python/JS) funciones de apoyo del programa exportado: `_ent`, `_real`, `_dividir`, `_cat`, `_fmt`, `_leer_entero`… |
| `ent`, `real`, `dividir`, `cat`, `fmt`… | Las mismas funciones de apoyo en Java. |

**En la interfaz (`web/`)**: los `id` llevan prefijo según su función: `btn-` botones, `chk-` casillas, `pane-` paneles, `cnt-` contadores, `dlg-` ventanas, `asi-` asistente, `exp-` exportar, `sug-` autocompletado, `est-` barra de estado. Los datos guardados en el navegador usan la clave `costenol.…`. Las variables de entorno son `ANTHROPIC_API_KEY`, `COSTENOL_*`, `IA_LIMITE_*` y `ACCESO_*`.

### Diseño responsive (celular y tableta)

* `web/movil.js` se carga en la cabecera (antes de dibujar) y pone la clase `movil` en `<html>` cuando la pantalla mide 820 px o menos, o es un celular girado (`max-height: 520px` y `pointer: coarse`). También calcula `--alto-visible` (alto sin el teclado en pantalla) y pone la clase `teclado` cuando el teclado ocupa más de una cuarta parte.
* Todo el CSS del celular está al final de `web/estilos.css`, en el bloque **MODO RESPONSIVE**, y cuelga de `html.movil …`. La tableta (821 a 1100 px) usa una `@media`.
* En el celular `.principal` muestra una sola vista según `data-vista` (`editor`, `salida` o `resultados`); el asistente es una capa fija a pantalla completa y el menú lateral pasa a ser un cajón. `app.js` maneja esto con `esMovil()`, `setVista()`, `abrirMenu()` y `actualizarInsignia()`.
* Los elementos que solo existen en el celular llevan la clase `solo-movil` (`btn-menu`, `barra-movil`). Si agrega un botón nuevo a la barra de herramientas, revise cómo se ve con el texto oculto (en el celular solo se muestra el ícono).
* Cuidado con los nombres de clase repetidos: `asistente` es a la vez el panel del asistente y la burbuja de respuesta; por eso las reglas del panel usan `#asistente`.
* Probado con el emulador de móvil de Chromium (iPhone, Android, tableta y celular girado); el teclado en pantalla real de iOS/Android no se ha probado en aparatos físicos.

## 7. API HTTP

| Método y ruta | Para qué |
|---|---|
| `POST /api/analizar` | Compila (sin ejecutar). |
| `POST /api/ejecutar` | Compila y ejecuta; puede quedar esperando un dato. |
| `POST /api/entrada` | Envía el dato que pidió el programa. |
| `POST /api/detener` | Cancela una ejecución. |
| `POST /api/exportar`, `GET /api/exportar/formatos` | Exportar. |
| `POST /api/asistente`, `GET /api/ia/estado`, `POST /api/ia/config`, `POST /api/ia/borrar` | Asistente de IA. |
| `GET /api/ejemplos`, `GET /api/catalogo`, `GET /api/modo`, `GET /api/salud` | Datos de apoyo y comprobación de salud. |
| `POST /api/latido`, `POST /api/cerrar` | Solo modo local: la ventana avisa que sigue abierta o que se cerró. |

## 8. Cómo agregar cosas

**Una palabra reservada o un tipo:** constantes de `costenol_lexico.py` → regla en `costenol_sintactico.py` → tipo en `costenol_semantico.py` → comportamiento en `costenol_ejecucion.py` → los 4 generadores de `costenol_exportar.py` → `INSTRUCCIONES` del asistente → `web/manual.html` y el resaltado de `web/app.js`.

**Un operador:** reconocerlo en `_Analizador` (léxico), darle precedencia en `Parser` (`aditiva`/`termino`), tipos en `Analizador.binario`, cálculo en `_binario` del intérprete y en cada generador.

**Un mensaje de error:** emitirlo con `self.error("E-XXX-nn", …)`, **agregarlo al `CATALOGO` del módulo** (una prueba falla si falta) y agregar su reacción y su causa en `REACCIONES` y `CAUSAS` de `costenol_dialecto.py` (otra prueba lo exige). Escoja una expresión del diccionario solo si encaja con lo que pasó.

**Un formato de exportación:** subclase de `Generador` (implementar los métodos de la clase base), registrarla en `exportar()` y `formatos()`, y agregar el formato a `pruebas_exportar.py`.

**El habla costeña:** editar `REACCIONES`, `CAUSAS` y `MENSAJES_PANTALLA` de `costenol_dialecto.py` (y, si cambia una frase de la pantalla, la misma frase en `web/app.js`).

**Siempre:** correr todas las pruebas y actualizar `web/manual.html`. Cuando se publique una versión nueva (hoy la 1.0 aún no se ha lanzado), agregar su fila al historial de cambios y subir el número en `web/index.html` (barra de estado y ventana *Acerca de*).

## 9. Límites que protegen al programa ("sin fallos")

| Límite | Valor |
|---|---|
| Tamaño del programa | 2 000 000 de caracteres |
| Errores mostrados por fase | 200 |
| Nombres de variable | 30 caracteres |
| Enteros | ±2147483647 |
| Anidamiento de paréntesis/`Si` | 40 niveles |
| Operaciones por instrucción | 150 |
| Largo de un texto armado con `+` | 1 000 000 de caracteres |
| Texto escrito por el usuario en `Captura.Texto` | 10 000 caracteres |
| Cuerpo de una petición HTTP | 4 000 000 de bytes |

Ninguna entrada debe hacer fallar el programa: toda fase termina con un diagnóstico y las excepciones internas se convierten en un error (`E-XXX-97`). Hay pruebas con entradas «locas» (basura, caracteres invisibles, programas enormes, datos inválidos).

## 10. Pruebas

| Archivo | Qué comprueba |
|---|---|
| `pruebas_lexico.py` | Tokens y errores léxicos. |
| `pruebas_compilador.py` | Sintaxis, semántica, ejecución, notas de clase del profesor, topes, entradas inesperadas, ejemplos del manual y de la carpeta `ejemplos/`. |
| `pruebas_dialecto.py` | Formato de los mensajes en costeño y que cada código tenga su frase. |
| `pruebas_asistente.py` | El asistente con un servidor falso de la API (sin gastar dinero). |
| `pruebas_servidor.py` | Rutas, seguridad, modo nube, límites. |
| `pruebas_nube.py` | Arranque real en modo nube y archivos de Railway. |
| `pruebas_exportar.py` | Cada formato exportado contra el intérprete (usa Node.js y JDK si están instalados). |

Ejecutar cada una con `python pruebas_xxx.py`.

## 11. Despliegue

* **Escritorio:** `ejecutar.bat` (necesita Python). `construir_exe.bat` crea `Costenol.exe` con PyInstaller y deja `ia_config.json` junto al `.exe`.
* **Railway:** `python app.py --nube` escucha en el puerto de `PORT`, no hace nada en segundo plano (para que el modo *Serverless/sleep* pueda dormirlo) y usa `/api/salud` como comprobación de salud. Ver `RAILWAY.md`.

---

## 12. Preguntas frecuentes para la sustentación

**¿Qué es un compilador y qué hace el de ustedes?**
Un programa que lee un lenguaje fuente, lo valida y lo convierte o lo ejecuta. El nuestro valida Costeñol en tres fases (léxica, sintáctica, semántica), lo ejecuta, y además lo exporta a Python, JavaScript, HTML y Java.

**¿Qué hace cada fase?**
Léxica: separa el texto en tokens y rechaza símbolos o palabras que no existen. Sintáctica: comprueba el orden (gramática) y construye el árbol. Semántica: comprueba el sentido (variables declaradas, tipos compatibles). Ejecución: recorre el árbol y hace lo que dice el programa.

**¿Qué es un token? Muestre uno.**
La pieza más pequeña con significado. En `edad = 20;` hay cuatro: `edad` (IDENTIFICADOR), `=` (OPERADOR_ASIGNACION), `20` (NUMERO_ENTERO) y `;` (PUNTO_Y_COMA). Se ven en la pestaña *Reporte*.

**¿Qué es el árbol sintáctico y dónde se ve?**
La estructura del programa como un árbol (por ejemplo una asignación con la operación como hija). Pestaña *Árbol Sintáctico*.

**¿Qué es la tabla de símbolos?**
La lista de variables con su tipo y datos de uso. Pestaña *Tabla de Símbolos*.

**¿Cómo detectan los errores y cómo evitan llenar de avisos falsos?**
Cada fase registra errores con línea y columna y se recupera (`sincronizar`) para seguir buscando; por eso muestra varios errores a la vez. Si una fase falla, no se ejecuta la siguiente.

**¿Cómo se maneja «entero Entero;»?**
Se rechaza (E-SIN-27): una variable no puede llamarse como un tipo de dato ni como una palabra reservada, tampoco cambiando mayúsculas.

**¿Cómo se aplican mayúsculas y minúsculas?**
El lenguaje distingue mayúsculas. `si` o `entero` en minúscula dan error con la sugerencia de la palabra correcta (E-SIN-26). `edad` y `Edad` son variables distintas.

**¿Qué pasa con `num = 1(`?**
Error E-SIN-28: falta un operador entre el número y el paréntesis. `1 + (` sin completar da E-SIN-05. Todo paréntesis debe cerrarse.

**¿Qué pasa si asigno a una variable no declarada?**
Error semántico E-SEM-01.

**¿Qué pasa si escribo cualquier locura o un dato inesperado?**
El programa no se cae: toda entrada termina en un diagnóstico, los datos de `Captura` se validan y se vuelven a pedir, hay topes (texto, tamaño, anidamiento) y las excepciones internas se convierten en errores. Hay pruebas automáticas con entradas «locas».

**¿Por qué Python?**
Es claro de leer, trae manejo de texto y servidor HTTP en la biblioteca estándar, y permite que todo el compilador sea un solo lenguaje sin dependencias externas.

**¿Por qué la interfaz es web si el compilador es de escritorio?**
El análisis y la ejecución son Python; el navegador solo dibuja la ventana. Así la misma interfaz funciona en el computador (`.bat` o `.exe`) y en la nube (Railway).

**¿Cómo garantizan que lo exportado hace lo mismo?**
Hay pruebas que ejecutan el mismo programa con el intérprete y con cada formato exportado, con los mismos datos, y comparan la salida y los errores.

**¿Cómo se ejecuta fuera de su computador?**
Con `Costenol.exe`, con el botón *Exportar* (el archivo generado corre solo) o en línea en Railway.

**¿Qué falta o qué mejorarían?**
Ciclos, listas y funciones; los operadores lógicos (y, o, no); y pulir el habla costeña con más frases. Hay reglas propuestas por el equipo (por ejemplo los operadores de comparación y `Verdadero`/`Falso`) que se deben confirmar con el profesor.

---

## 13. Casos de prueba para la presentación («cualquier locura»)

Escriba cada caso en el editor y presione *Ejecutar*. Todos deben dar un mensaje claro y **nunca** hacer fallar el programa.

| Escribo | Debe pasar |
|---|---|
| `entero Entero;` | Error sintáctico E-SIN-27 (nombre igual al tipo) |
| `a entero;` | E-SIN-26 (mayúsculas) |
| `x = 5;` | Error semántico E-SEM-01 (variable no declarada) |
| `n Entero;` + `n = 1(;` | E-SIN-28 (falta operador) |
| `n Entero;` + `n = 1 + (;` | E-SIN-05 (paréntesis sin completar) |
| `n Entero;` + `n = (1 + 2;` | E-SIN-05 (falta cerrar) |
| `edad Entero` (sin `;`) | E-SIN-01 |
| `Si (x > 1)` sin `FinSi` | E-SIN-09 |
| `x Entero;` + `x = "hola";` | E-SEM-03 (tipos) |
| `x Entero;` + `Mensaje.Texto(x);` | E-SEM-09 (variable sin valor) |
| `r Real;` + `r = 5 / 0;` | E-SEM-10 |
| `x Entero;` + `x = Captura.Entero();` y escribir `0` en `10 / x` | Error de ejecución E-EJE-02 |
| `x = 3.14;` | E-LEX-05 (decimal con punto) |
| `Mensaje.Texto("sin cerrar);` | E-LEX-02 |
| `x = 5 @ 3;` | E-LEX-15 |
| Pegar 400 KB de basura en el editor | Muestra errores; sigue funcionando |
| Escribir letras cuando pide un `Entero` | «Valor no válido» y lo vuelve a pedir |
| Un texto que se duplica 25 veces (`t = t + t;`) | E-EJE-04 (texto demasiado largo) |
