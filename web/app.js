/* MiCompilador - interfaz del compilador Costeñol.
   Este archivo solo dibuja la interfaz y se comunica con Python:
   el análisis (léxico, sintáctico y semántico) y la ejecución del programa
   se hacen en el servidor local escrito en Python. */
(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

  const E = {
    codigo: $('#codigo'),
    resaltado: $('#resaltado'),
    numeros: $('#numeros'),
    marcas: $('#marcas'),
    lineaActual: $('#linea-actual'),
    area: $('#area-codigo'),
    tira: $('#tira-archivos'),
    consola: $('#consola'),
    btnCompilar: $('#btn-compilar'),
    btnEjecutar: $('#btn-ejecutar'),
    chkReporte: $('#chk-reporte'),
    chkAuto: $('#chk-autoanalisis'),
  };

  const CLAVE_DOCS = 'costenol.docs.v2';
  const CLAVE_CONFIG = 'costenol.config';
  const CLAVE_MANUAL = 'costenol.manual_visto';
  const MUESTRA = '// Hola Mundo //\nMensaje.Texto("Hola Mundo");\n';

  let docs = [];
  let activoId = null;
  let contadorDocs = 1;
  let ultima = null;                 // último resultado de compilación
  let marcasError = new Set();
  let marcasAviso = new Set();
  let lineasMostradas = 0;
  let temporizadorAuto = null;
  let sesionId = null;               // ejecución en curso (esperando datos)
  let ocupado = false;
  let resultadoVigente = false;      // ¿los resultados corresponden al código actual?
  let cerrando = false;
  let modoNube = false;              // versión en línea (Railway): sin latido, sin cerrar el servidor
  let sug = null;                    // sugerencia activa del autocompletado
  let fantasma = null;               // texto gris que se muestra tras el cursor
  let autocompletar = true;
  let modoCosteno = true;            // mensajes de error en costeño (formato del profesor)
  let aceptando = false;

  const NOMBRE_FASE = { lexico: 'léxico', sintactico: 'sintáctico', semantico: 'semántico' };
  // Texto de la pantalla según el modo: español formal o costeño (las frases costeñas están en costenol_dialecto.py).
  const segunModo = (formal, costeno) => (modoCosteno ? costeno : formal);

  /* ===================================================================== */
  /*  Resaltado de sintaxis (solo colores; el análisis real es de Python)   */
  /* ===================================================================== */
  const RE_RESALTADO = new RegExp(
    '(\\/\\/.*?\\/\\/|\\/\\/.*$)' +
    '|("[^"\\n]*"?|\\u201c[^\\u201d\\n]*\\u201d?)' +
    '|((?<![\\p{L}\\d_])(?:Entero|Texto|Real|Logico|Captura|Mensaje|Si|Sino|FinSi|Verdadero|Falso)(?![\\p{L}\\d_]))',
    'gmu'
  );

  function resaltar(texto) {
    let salida = '';
    let ultimo = 0;
    let m;
    RE_RESALTADO.lastIndex = 0;
    while ((m = RE_RESALTADO.exec(texto)) !== null) {
      if (m[0].length === 0) { RE_RESALTADO.lastIndex++; continue; }
      salida += esc(texto.slice(ultimo, m.index));
      const clase = m[1] ? 'com' : m[2] ? 'cad' : 'pal';
      salida += `<span class="${clase}">${esc(m[0])}</span>`;
      ultimo = m.index + m[0].length;
    }
    return salida + esc(texto.slice(ultimo));
  }

  /* ===================================================================== */
  /*  Editor                                                                */
  /* ===================================================================== */
  function construirNumeros(n) {
    let html = '';
    for (let i = 1; i <= n; i++) html += `<div>${i}</div>`;
    E.numeros.innerHTML = html;
    lineasMostradas = n;
    pintarNumerosMarcados();
  }

  function pintarNumerosMarcados() {
    const hijos = E.numeros.children;
    marcasError.forEach((l) => { if (hijos[l - 1]) hijos[l - 1].classList.add('con-error'); });
    marcasAviso.forEach((l) => {
      if (hijos[l - 1] && !marcasError.has(l)) hijos[l - 1].classList.add('con-aviso');
    });
  }

  function pintarMarcasLineas() {
    $$('.marca-error, .marca-aviso', E.marcas).forEach((n) => n.remove());
    const crear = (l, clase) => {
      const d = document.createElement('div');
      d.className = clase;
      d.style.top = `calc(0.4rem + ${l - 1} * var(--alto-linea))`;
      E.marcas.appendChild(d);
    };
    marcasAviso.forEach((l) => { if (!marcasError.has(l)) crear(l, 'marca-aviso'); });
    marcasError.forEach((l) => crear(l, 'marca-error'));
    $$('.con-error, .con-aviso', E.numeros).forEach((n) => n.classList.remove('con-error', 'con-aviso'));
    pintarNumerosMarcados();
  }

  function quitarMarcas() {
    marcasError = new Set();
    marcasAviso = new Set();
    pintarMarcasLineas();
  }

  function refrescarEditor() {
    const t = E.codigo.value;
    if (fantasma && fantasma.pos <= t.length) {
      E.resaltado.innerHTML = resaltar(t.slice(0, fantasma.pos)) +
        `<span class="fantasma">${esc(fantasma.texto)}</span>` + resaltar(t.slice(fantasma.pos)) + '\n';
    } else {
      E.resaltado.innerHTML = resaltar(t) + '\n';
    }
    const n = t.split('\n').length;
    if (n !== lineasMostradas) construirNumeros(n);
    actualizarCursor();
  }

  function posicionCursor() {
    const pos = E.codigo.selectionStart || 0;
    const antes = E.codigo.value.slice(0, pos);
    const salto = antes.lastIndexOf('\n');
    let linea = 1;
    for (let i = antes.indexOf('\n'); i !== -1; i = antes.indexOf('\n', i + 1)) linea++;
    return { linea, columna: pos - (salto + 1) + 1 };
  }

  function actualizarCursor() {
    const { linea, columna } = posicionCursor();
    E.lineaActual.style.top = `calc(0.4rem + ${linea - 1} * var(--alto-linea))`;
    $('#est-linea').textContent = linea;
    $('#est-col').textContent = columna;
  }

  function medirCaracter() {
    const cs = getComputedStyle(E.codigo);
    const lienzo = medirCaracter.lienzo || (medirCaracter.lienzo = document.createElement('canvas'));
    const ctx = lienzo.getContext('2d');
    ctx.font = `${cs.fontSize} ${cs.fontFamily}`;
    return ctx.measureText('M').width || 10;
  }

  function irA(linea, columna) {
    if (esMovil() && PRINCIPAL.dataset.vista !== 'editor') {       // el editor estaba oculto: se muestra y se vuelve a intentar
      setVista('editor');
      requestAnimationFrame(() => irA(linea, columna));
      return;
    }
    const lineas = E.codigo.value.split('\n');
    if (linea < 1 || linea > lineas.length) return;
    let desplazamiento = 0;
    for (let i = 0; i < linea - 1; i++) desplazamiento += lineas[i].length + 1;
    const col = Math.min(Math.max(columna - 1, 0), lineas[linea - 1].length);
    desplazamiento += col;
    E.codigo.focus();
    const fin = Math.min(desplazamiento + 1, E.codigo.value.length);
    E.codigo.setSelectionRange(desplazamiento, fin);
    const alto = parseFloat(getComputedStyle(E.codigo).lineHeight);
    const arriba = (linea - 1) * alto;
    const a = E.area;
    if (arriba < a.scrollTop) a.scrollTop = Math.max(0, arriba - alto * 2);
    else if (arriba + alto * 3 > a.scrollTop + a.clientHeight) a.scrollTop = arriba + alto * 3 - a.clientHeight;
    const x = col * medirCaracter() + E.numeros.offsetWidth + 24;
    if (x < a.scrollLeft + E.numeros.offsetWidth) a.scrollLeft = Math.max(0, x - E.numeros.offsetWidth - 60);
    else if (x > a.scrollLeft + a.clientWidth) a.scrollLeft = x - a.clientWidth + 80;
    actualizarCursor();
  }

  function mantenerCursorVisible() {
    const t = E.codigo.value;
    const pos = E.codigo.selectionEnd;
    const linea = t.slice(0, pos).split('\n').length;
    const colTexto = t.slice(t.lastIndexOf('\n', pos - 1) + 1, pos);
    const cs = getComputedStyle(E.codigo);
    const alto = parseFloat(cs.lineHeight);
    const arriba = parseFloat(cs.paddingTop) + (linea - 1) * alto;
    const a = E.area;
    if (arriba < a.scrollTop) a.scrollTop = Math.max(0, arriba - alto);
    else if (arriba + alto * 1.6 > a.scrollTop + a.clientHeight) a.scrollTop = arriba + alto * 1.6 - a.clientHeight;
    const x = E.numeros.offsetWidth + parseFloat(cs.paddingLeft) + anchoVisual(colTexto) * medirCaracter();
    if (x < a.scrollLeft + E.numeros.offsetWidth + 10) a.scrollLeft = Math.max(0, x - E.numeros.offsetWidth - 40);
    else if (x + 12 > a.scrollLeft + a.clientWidth) a.scrollLeft = x + 12 - a.clientWidth + 40;
  }

  function insertarTexto(t) {
    if (!document.execCommand('insertText', false, t)) {
      const s = E.codigo.selectionStart;
      E.codigo.setRangeText(t, s, E.codigo.selectionEnd, 'end');
      E.codigo.dispatchEvent(new Event('input'));
    }
  }

  E.codigo.addEventListener('input', (e) => {
    resultadoVigente = false;
    if (aceptando) { sug = null; fantasma = null; }
    else if (autocompletar && e.inputType === 'insertText') calcularSugerencias();
    else { sug = null; fantasma = null; }
    refrescarEditor();
    pintarSugerencias();
    mantenerCursorVisible();
    if (marcasError.size || marcasAviso.size) quitarMarcas();
    guardarDocs();
    if (E.chkAuto.checked) {
      clearTimeout(temporizadorAuto);
      temporizadorAuto = setTimeout(() => compilar(true), 900);
    }
  });
  ['keyup', 'click', 'focus', 'select'].forEach((ev) => E.codigo.addEventListener(ev, actualizarCursor));
  E.codigo.addEventListener('click', () => ocultarSugerencias());
  E.codigo.addEventListener('blur', () => ocultarSugerencias());
  E.codigo.addEventListener('keyup', (e) => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(e.key)) ocultarSugerencias();
  });
  E.area.addEventListener('scroll', () => { if (sug) pintarSugerencias(); });
  document.addEventListener('selectionchange', () => { if (document.activeElement === E.codigo) actualizarCursor(); });

  E.codigo.addEventListener('keydown', (e) => {
    if (sug) {
      if (e.key === 'Tab' && !e.shiftKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); aceptarSugerencia(); return; }
      if (e.key === 'Escape') { e.preventDefault(); ocultarSugerencias(); return; }
      if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && sug.items.length > 1) {
        e.preventDefault();
        sug.i = (sug.i + (e.key === 'ArrowDown' ? 1 : sug.items.length - 1)) % sug.items.length;
        prepararFantasma();
        refrescarEditor();
        pintarSugerencias();
        return;
      }
    }
    if (e.key === 'Tab' && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      insertarTexto('    ');
    } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      ejecutar();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'F5') { e.preventDefault(); ejecutar(); }
    else if (e.key === 'F7') { e.preventDefault(); compilar(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); guardar(); }
  });

  /* ===================================================================== */
  /*  Autocompletado: texto predictivo gris + lista; Tab completa            */
  /* ===================================================================== */
  const COMANDOS = [
    { et: 'Mensaje.Texto', ins: 'Mensaje.Texto("|");', det: 'Muestra un texto, número o variable' },
    { et: 'Captura.Entero', ins: 'Captura.Entero();', det: 'Lee un número entero' },
    { et: 'Captura.Real', ins: 'Captura.Real();', det: 'Lee un número real (con coma)' },
    { et: 'Captura.Texto', ins: 'Captura.Texto();', det: 'Lee un texto' },
    { et: 'Captura.Logico', ins: 'Captura.Logico();', det: 'Lee Verdadero o Falso' },
    { et: 'Si', ins: 'Si (|)\n    \nFinSi', det: 'Condicional completo (Si … FinSi)', bloque: true },
    { et: 'Sino', ins: 'Sino', det: 'Rama contraria del Si' },
    { et: 'FinSi', ins: 'FinSi', det: 'Cierra el Si' },
    { et: 'Verdadero', ins: 'Verdadero', det: 'Valor lógico' },
    { et: 'Falso', ins: 'Falso', det: 'Valor lógico' },
  ];
  const TIPOS_DATO = [['Entero', 'Números sin decimales'], ['Texto', 'Palabras y frases'],
    ['Real', 'Números con decimales'], ['Logico', 'Verdadero o Falso']];
  const PALABRAS_INICIO = ['Si', 'Sino', 'FinSi', 'Mensaje', 'Captura'];
  const RE_PALABRA = /[A-Za-zñÑ_][A-Za-z0-9ñÑ_]*(?:\.[A-Za-z0-9ñÑ_]*)?$/;
  const LETRA_O_DIGITO = /[A-Za-z0-9ñÑ_.]/;

  function contextoDeLinea(antes) {
    let cadena = null;               // cierre esperado de la cadena abierta
    let comentario = false;
    for (let i = 0; i < antes.length; i++) {
      const c = antes[i];
      if (cadena) { if (c === cadena) cadena = null; continue; }
      if (comentario) { if (c === '/' && antes[i + 1] === '/') { comentario = false; i++; } continue; }
      if (c === '/' && antes[i + 1] === '/') { comentario = true; i++; continue; }
      if (c === '"') cadena = '"';
      else if (c === '\u201c') cadena = '\u201d';
    }
    return cadena ? 'cadena' : comentario ? 'comentario' : 'codigo';
  }

  function variablesDelPrograma() {
    const re = /(?:^|[\s;])([A-Za-zñÑ_][A-Za-z0-9ñÑ_]*)[ \t]+(Entero|Texto|Real|Logico)[ \t]*;/g;
    const vistos = new Map();
    let m;
    const t = E.codigo.value;
    while ((m = re.exec(t)) !== null) {
      if (!/^(Si|Sino|FinSi|Mensaje|Captura|Verdadero|Falso)$/.test(m[1])) vistos.set(m[1], m[2]);
    }
    return Array.from(vistos, ([nombre, tipo]) => ({ nombre, tipo }));
  }

  function candidatosPara(palabra, antes) {
    const p = palabra.toLowerCase();
    const primera = (antes.match(/^\s*([A-Za-zñÑ_][A-Za-z0-9ñÑ_]*)\s+[A-Za-zñÑ]*$/) || [])[1];
    // "edad En" → tipos de dato
    if (primera && !PALABRAS_INICIO.includes(primera) && !palabra.includes('.')) {
      return TIPOS_DATO.filter(([t]) => t.toLowerCase().startsWith(p) && t !== palabra)
        .map(([t, det]) => ({ et: t, ins: t + ';', det }));
    }
    const lista = COMANDOS.filter((c) => c.et.toLowerCase().startsWith(p) && (c.et !== palabra || c.ins !== c.et));
    if (!palabra.includes('.')) {
      variablesDelPrograma().forEach((v) => {
        if (v.nombre.toLowerCase().startsWith(p) && v.nombre !== palabra) lista.push({ et: v.nombre, ins: v.nombre, det: `Variable ${v.tipo}` });
      });
    }
    return lista;
  }

  function calcularSugerencias() {
    sug = null;
    fantasma = null;
    const pos = E.codigo.selectionStart;
    if (pos !== E.codigo.selectionEnd) return;
    const t = E.codigo.value;
    const inicioLinea = t.lastIndexOf('\n', pos - 1) + 1;
    const antes = t.slice(inicioLinea, pos);
    if (contextoDeLinea(antes) !== 'codigo') return;
    if (LETRA_O_DIGITO.test(t.charAt(pos))) return;          // el cursor está en medio de una palabra
    const m = antes.match(RE_PALABRA);
    if (!m) return;
    const inicio = pos - m[0].length;
    if (inicio > 0 && LETRA_O_DIGITO.test(t.charAt(inicio - 1))) return;
    const items = candidatosPara(m[0], antes).slice(0, 6);
    if (!items.length) return;
    sug = { inicio, fin: pos, palabra: m[0], items, i: 0 };
    prepararFantasma();
  }

  function prepararFantasma() {
    fantasma = null;
    if (!sug) return;
    const c = sug.items[sug.i];
    const t = E.codigo.value;
    const finLinea = t.indexOf('\n', sug.fin);
    const resto = t.slice(sug.fin, finLinea === -1 ? t.length : finLinea);
    if (resto.trim() !== '') return;                          // no se muestra gris sobre texto existente
    if (!c.et.startsWith(sug.palabra) && !c.ins.startsWith(sug.palabra)) return;   // otra combinación de mayúsculas
    let texto;
    if (c.bloque) texto = c.et.slice(sug.palabra.length) + ' (…) … FinSi';
    else texto = c.ins.replace('|', '').split('\n')[0].slice(sug.palabra.length);
    if (texto) fantasma = { pos: sug.fin, texto };
  }

  function anchoCaracter() { return medirCaracter(); }

  function anchoVisual(texto) {
    let col = 0;
    for (const ch of texto) col = ch === '\t' ? Math.floor(col / 4 + 1) * 4 : col + 1;
    return col;
  }

  function pintarSugerencias() {
    const caja = $('#sug-lista');
    if (!sug || sug.items.length < 1 || (sug.items.length === 1 && fantasma && !esTactil())) { caja.hidden = true; return; }
    caja.innerHTML = sug.items.map((c, i) =>
      `<div class="sug-item${i === sug.i ? ' activo' : ''}" role="option" data-i="${i}"><span class="sug-et">${esc(c.et)}</span><span class="sug-det">${esc(c.det)}</span></div>`).join('') +
      (esTactil() ? '<div class="sug-pie">Toca una opción para completar</div>'
        : sug.items.length > 1 ? '<div class="sug-pie">Tab completa · ↑ ↓ cambian · Esc cierra</div>' : '<div class="sug-pie">Tab completa · Esc cierra</div>');
    caja.hidden = false;
    const t = E.codigo.value;
    const linea = t.slice(0, sug.inicio).split('\n').length;
    const colIni = anchoVisual(t.slice(t.lastIndexOf('\n', sug.inicio - 1) + 1, sug.inicio));
    const cs = getComputedStyle(E.codigo);
    const alto = parseFloat(cs.lineHeight);
    const relleno = parseFloat(cs.paddingLeft);
    const arriba = parseFloat(cs.paddingTop);
    caja.style.left = `${relleno + colIni * anchoCaracter()}px`;
    let y = arriba + linea * alto;
    const a = E.area;
    if (y + caja.offsetHeight > a.scrollTop + a.clientHeight) y = arriba + (linea - 1) * alto - caja.offsetHeight;
    caja.style.top = `${Math.max(0, y)}px`;
  }

  function ocultarSugerencias() {
    if (!sug && !fantasma) return;
    sug = null;
    fantasma = null;
    $('#sug-lista').hidden = true;
    refrescarEditor();
  }

  function aceptarSugerencia(indice) {
    if (!sug) return;
    const s = sug;
    const c = s.items[indice === undefined ? s.i : indice];
    const t = E.codigo.value;
    const inicioLinea = t.lastIndexOf('\n', s.inicio - 1) + 1;
    const sangria = (t.slice(inicioLinea).match(/^[ \t]*/) || [''])[0];
    let texto = c.ins.split('\n').map((l, i) => (i ? sangria + l : l)).join('\n');
    const marca = texto.indexOf('|');
    texto = texto.replace('|', '');
    const desplazamiento = marca >= 0 ? marca : texto.length;
    sug = null;
    fantasma = null;
    $('#sug-lista').hidden = true;
    aceptando = true;
    E.codigo.focus();
    E.codigo.setSelectionRange(s.inicio, s.fin);
    insertarTexto(texto);
    aceptando = false;
    const nueva = s.inicio + desplazamiento;
    E.codigo.setSelectionRange(nueva, nueva);
    refrescarEditor();
    actualizarCursor();
  }

  $('#sug-lista').addEventListener('pointerdown', (e) => {
    e.preventDefault();                                       // no quita el foco del editor (ni cierra el teclado)
    const item = e.target.closest('.sug-item');
    if (item) aceptarSugerencia(Number(item.dataset.i));
  });

  /* ===================================================================== */
  /*  Documentos (pestañas del editor)                                      */
  /* ===================================================================== */
  function docActual() { return docs.find((d) => d.id === activoId); }

  function guardarDocs() {
    const d = docActual();
    if (d) d.codigo = E.codigo.value;
    try {
      localStorage.setItem(CLAVE_DOCS, JSON.stringify({ docs, activo: activoId, contador: contadorDocs }));
    } catch (_) { /* almacenamiento no disponible: se ignora */ }
  }

  function renderTabs() {
    E.tira.innerHTML = docs.map((d) =>
      `<div class="pestana-archivo${d.id === activoId ? ' activa' : ''}" data-id="${d.id}" title="${esc(d.nombre)}">` +
      `<span>${esc(d.nombre)}</span><button type="button" class="x" data-cerrar="${d.id}" aria-label="Cerrar ${esc(d.nombre)}">&#10005;</button></div>`
    ).join('') + '<button type="button" class="btn-mas" id="btn-mas" title="Pestaña nueva en blanco" aria-label="Pestaña nueva"><svg><use href="#i-mas"/></svg></button>' +
      '<button type="button" class="btn-limpiar-codigo" id="btn-limpiar-codigo" title="Limpiar el código: borra todo lo escrito en esta pestaña (Ctrl+Z lo recupera)"><svg style="--hueco-icono:#f4f8ff"><use href="#i-basura"/></svg>Limpiar código</button>';
  }

  function mostrarDoc() {
    const d = docActual();
    E.codigo.value = d ? d.codigo : '';
    quitarMarcas();
    refrescarEditor();
    E.area.scrollTop = 0;
    E.area.scrollLeft = 0;
    E.codigo.setSelectionRange(0, 0);
    actualizarCursor();
    renderTabs();
  }

  function nuevoDoc(nombre, codigo) {
    guardarDocs();
    const id = 'd' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
    docs.push({ id, nombre: nombre || `sin_titulo_${contadorDocs++}.cst`, codigo: codigo || '' });
    activoId = id;
    limpiarResultados();
    mostrarDoc();
    guardarDocs();
    if (esMovil()) setVista('editor');
    else E.codigo.focus();
  }

  function activarDoc(id) {
    if (id === activoId) return;
    guardarDocs();
    activoId = id;
    limpiarResultados();
    mostrarDoc();
    guardarDocs();
  }

  function limpiarCodigo() {
    if (!E.codigo.value) { E.codigo.focus(); return; }
    E.codigo.focus();
    E.codigo.select();
    if (!document.execCommand('delete')) {                     // alternativa si el navegador no deja deshacer
      E.codigo.value = '';
      E.codigo.dispatchEvent(new Event('input'));
    }
    limpiarResultados();
    setEstado('Código borrado (Ctrl+Z lo recupera)', '');
    E.codigo.focus();
  }

  function cerrarDoc(id) {
    const d = docs.find((x) => x.id === id);
    if (!d) return;
    const contenido = id === activoId ? E.codigo.value : d.codigo;
    if (contenido.trim() && !confirm(`¿Cerrar «${d.nombre}»? Si no lo guardó con el botón Guardar, se perderá su contenido.`)) return;
    const pos = docs.indexOf(d);
    docs.splice(pos, 1);
    if (!docs.length) docs.push({ id: 'd' + Date.now().toString(36), nombre: `sin_titulo_${contadorDocs++}.cst`, codigo: '' });
    if (id === activoId) {
      activoId = docs[Math.min(pos, docs.length - 1)].id;
      limpiarResultados();
    }
    mostrarDoc();
    guardarDocs();
  }

  E.tira.addEventListener('click', (e) => {
    const x = e.target.closest('[data-cerrar]');
    if (x) { e.stopPropagation(); cerrarDoc(x.dataset.cerrar); return; }
    if (e.target.closest('#btn-mas')) { nuevoDoc(); return; }
    if (e.target.closest('#btn-limpiar-codigo')) { limpiarCodigo(); return; }
    const t = e.target.closest('.pestana-archivo');
    if (t) activarDoc(t.dataset.id);
  });

  /* ===================================================================== */
  /*  Pestañas inferiores                                                   */
  /* ===================================================================== */
  function activarPestana(grupo, nombre) {
    const cont = $(`[data-grupo="${grupo}"]`);
    if (!cont) return;
    $$('.pestana', cont).forEach((b) => b.classList.toggle('activa', b.dataset.tab === nombre));
    $$('.panel', cont).forEach((p) => p.classList.toggle('activo', p.dataset.pane === nombre));
  }
  $$('[data-grupo] .pestana').forEach((b) => {
    b.addEventListener('click', () => activarPestana(b.closest('[data-grupo]').dataset.grupo, b.dataset.tab));
  });

  /* ===================================================================== */
  /*  Salida del programa (consola)                                         */
  /* ===================================================================== */
  function consolaLimpiar() { E.consola.innerHTML = ''; }

  function linea(texto, clase = '') {
    const s = document.createElement('span');
    s.className = 'l ' + clase;
    s.textContent = texto;
    E.consola.appendChild(s);
    E.consola.scrollTop = E.consola.scrollHeight;
    return s;
  }

  function consolaInicial() {
    consolaLimpiar();
    linea(segunModo('Listo.', 'Listo, compa.'), 'verde');
    linea(segunModo('Escriba un programa y presione Ejecutar (F5).', 'Escribe tu programa y presiona Ejecutar (F5).'), 'gris');
    linea('Aquí aparecerá lo que muestre su programa.', 'gris');
  }

  function setEstado(texto, clase) {
    $('#est-texto').textContent = texto;
    $('#est-punto').className = 'punto' + (clase ? ' ' + clase : '');
  }

  function setBotones(activo) {
    E.btnCompilar.disabled = !activo;
    E.btnEjecutar.disabled = !activo;
  }

  /* ===================================================================== */
  /*  Comunicación con Python                                               */
  /* ===================================================================== */
  async function llamar(ruta, cuerpo) {
    // En la nube el servicio puede estar "dormido": la primera petición puede fallar con 502/503/504
    // mientras despierta; se reintenta unos segundos antes de rendirse.
    const intentos = modoNube ? 4 : 1;
    for (let n = 1; ; n++) {
      let resp = null;
      try {
        resp = await fetch(ruta, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(cuerpo),
        });
      } catch (err) {
        if (n < intentos) { await new Promise((r) => setTimeout(r, 2500)); continue; }
        throw err;
      }
      if ([502, 503, 504].includes(resp.status) && n < intentos) { await new Promise((r) => setTimeout(r, 2500)); continue; }
      let datos = null;
      try { datos = await resp.json(); } catch (_) { /* sin cuerpo */ }
      if (!resp.ok) throw new Error(datos && datos.error ? datos.error : `El servidor respondió ${resp.status}`);
      return datos;
    }
  }

  function fallo(err) {
    setEstado('Sin conexión con el compilador', 'error');
    const ayuda = modoNube
      ? 'El servicio puede estar despertando o sin conexión: espere unos segundos y vuelva a intentarlo.'
      : 'Verifique que la ventana negra (consola) del compilador siga abierta.';
    $('#pane-mensajes').innerHTML =
      `<div class="banner mal"><svg><use href="#i-error"/></svg>No se pudo contactar el compilador de Python (${esc(err.message)}). ${ayuda}</div>`;
    activarPestana('inferior', 'mensajes');
    consolaLimpiar();
    linea('No se pudo contactar el compilador.', 'rojo');
    linea(modoNube ? 'El servicio no respondió; vuelva a intentarlo.' : 'La consola de Python parece estar cerrada.', 'gris');
  }

  async function detenerSesion() {
    const id = sesionId;
    sesionId = null;
    $$('.pregunta input', E.consola).forEach((i) => { i.disabled = true; });
    if (id) { try { await llamar('/api/detener', { sesion: id }); } catch (_) { /* ya terminó */ } }
  }

  /* ---- Compilar: solo revisa ---- */
  async function compilar(automatico) {
    clearTimeout(temporizadorAuto);
    if (ocupado) return;
    if (automatico !== true && esMovil()) setVista('salida');      // en el celular se muestra la salida
    ocupado = true; setBotones(false);
    await detenerSesion();
    setEstado('Compilando…', 'trabajando');
    try {
      const c = await llamar('/api/analizar', { codigo: E.codigo.value });
      ultima = c;
      pintarCompilacion(c);
      consolaLimpiar();
      if (c.exitoso) {
        const limpia = !c.advertencias.length;
        linea(segunModo('> Compilación exitosa.', '> ' + (limpia
          ? 'Tú eres la monda, manito: compiló limpio, sin errores ni advertencias.'
          : 'Ahí vamos: compiló, pero ojo con las advertencias.')), 'verde');
        linea('El programa no tiene errores.', '');
        linea(segunModo('Presione Ejecutar (F5) para correrlo.', 'Presiona Ejecutar (F5) para correrlo.'), 'gris');
        linea('', '');
        linea(`Tokens: ${c.tokens.length} (pestaña Reporte, abajo).`, 'gris');
        linea('Estructura: pestaña Árbol Sintáctico.', 'gris');
        linea('Variables: pestaña Tabla de Símbolos.', 'gris');
        setEstado(c.advertencias.length ? 'Compilación exitosa con advertencias' : 'Compilación exitosa', '');
      } else {
        erroresEnConsola(c, 'compilar');
        setEstado(`Compilación con ${plural(c.errores.length, 'error', 'errores')}`, 'error');
      }
      if (E.chkReporte.checked) descargarReporte(c);
    } catch (err) {
      fallo(err);
    } finally {
      ocupado = false; setBotones(true);
    }
  }

  /* ---- Ejecutar: compila y, si no hay errores, corre el programa ---- */
  async function ejecutar() {
    clearTimeout(temporizadorAuto);
    if (ocupado) return;
    if (esMovil()) setVista('salida');
    ocupado = true; setBotones(false);
    await detenerSesion();
    consolaLimpiar();
    setEstado('Ejecutando…', 'trabajando');
    try {
      const r = await llamar('/api/ejecutar', { codigo: E.codigo.value });
      ultima = r.compilacion;
      pintarCompilacion(r.compilacion);
      if (E.chkReporte.checked) descargarReporte(r.compilacion);
      if (!r.compilacion.exitoso) {
        erroresEnConsola(r.compilacion, 'ejecutar');
        setEstado(`Compilación con ${plural(r.compilacion.errores.length, 'error', 'errores')}`, 'error');
        return;
      }
      sesionId = r.sesion;
      manejarRespuesta(r);
    } catch (err) {
      fallo(err);
    } finally {
      ocupado = false; setBotones(true);
    }
  }

  function manejarRespuesta(r) {
    (r.salida || []).forEach((t) => linea(t));
    if (r.invalida) {
      linea(segunModo('Valor no válido: ' + r.invalida,
        'Eche, compa, ese dato no sirve: ' + r.invalida.charAt(0).toLowerCase() + r.invalida.slice(1)), 'rojo');
    }
    if (r.error) {
      linea('', '');
      linea(modoCosteno && r.error.mensaje_costeno ? r.error.mensaje_costeno
        : `Error de ejecución (línea ${r.error.linea}): ${r.error.mensaje}`, 'rojo');
      linea(segunModo('Proceso finalizado con errores.', 'Se formó el bololó: el proceso terminó con errores.'), 'rojo');
      marcasError.add(r.error.linea);
      pintarMarcasLineas();
      sesionId = null;
      setEstado('Error al ejecutar el programa', 'error');
      return;
    }
    if (r.espera) {
      pedirEntrada(r.espera);
      setEstado('El programa espera un dato…', 'trabajando');
      return;
    }
    if (r.terminado) {
      linea('', '');
      linea(segunModo('Proceso finalizado correctamente.', 'Todo bien, compa: el programa quedó al pelo.'), 'verde');
      sesionId = null;
      setEstado('Ejecución terminada', '');
    }
  }

  const PEDIDO = {
    Texto: 'un texto',
    Entero: 'un entero',
    Real: 'un real (con coma, ej. 3,5)',
    Logico: 'Verdadero o Falso',
  };

  function pedirEntrada(ev) {
    // Solo una casilla para escribir: el propio programa dice qué pide con Mensaje.Texto.
    const fila = document.createElement('span');
    fila.className = 'l pregunta';
    fila.append('› ');
    const inp = document.createElement('input');
    inp.type = 'text';
    inp.autocomplete = 'off';
    inp.spellcheck = false;
    inp.title = `${PEDIDO[ev.tipo_dato] || ev.tipo_dato} para «${ev.variable}»`;
    inp.setAttribute('aria-label', `Valor para ${ev.variable}`);
    fila.appendChild(inp);
    E.consola.appendChild(fila);
    E.consola.scrollTop = E.consola.scrollHeight;
    inp.focus();
    inp.addEventListener('keydown', async (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (inp.disabled || !sesionId) return;
        const valor = inp.value;
        inp.disabled = true;
        const span = document.createElement('span');
        span.className = 'valor';
        span.textContent = valor;
        inp.replaceWith(span);
        try {
          manejarRespuesta(await llamar('/api/entrada', { sesion: sesionId, valor }));
        } catch (err) {
          linea('No se pudo enviar el dato: ' + err.message, 'rojo');
          sesionId = null;
          setEstado('Ejecución detenida', 'error');
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        detenerSesion();
        linea('', '');
        linea('Ejecución detenida por el usuario.', 'amarillo');
        setEstado('Ejecución detenida', '');
      }
    });
  }

  function erroresEnConsola(c, modo) {
    const fuente = E.codigo.value.split('\n');
    const nombre = NOMBRE_FASE[c.fase_fallida] || '';
    linea(modo === 'ejecutar' ? '> No se pudo ejecutar el programa.' : '> La compilación falló.', 'rojo');
    const uno = c.errores.length === 1;
    linea(`Hay ${plural(c.errores.length, 'error', 'errores')} en el análisis ${nombre}. ` +
      segunModo(uno ? 'Corríjalo y vuelva a intentar.' : 'Corríjalos y vuelva a intentar.',
        uno ? 'Arréglalo, compa, y vuelve a intentar.' : 'Arréglalos, compa, y vuelve a intentar.'), 'gris');
    linea('', '');
    c.errores.slice(0, 6).forEach((d) => {
      linea(modoCosteno && d.mensaje_costeno ? d.mensaje_costeno : `Línea ${d.linea}, col. ${d.columna}: ${d.mensaje}`, 'rojo');
      const texto = (fuente[d.linea - 1] || '').replace(/\t/g, ' ');
      if (texto.length <= 70) {
        linea(`  ${texto}`, 'gris');
        linea(`  ${' '.repeat(Math.max(d.columna - 1, 0))}^`, 'caret');
      }
      linea('', '');
    });
    if (c.errores.length > 6) linea(`… y ${c.errores.length - 6} más: vea la pestaña Errores.`, 'gris');
    if (c.tokens.length) linea(`Los ${c.tokens.length} tokens encontrados están en la pestaña Reporte.`, 'gris');
  }

  /* ===================================================================== */
  /*  Paneles de resultados                                                 */
  /* ===================================================================== */
  function textoDiag(d) {
    return modoCosteno && d.mensaje_costeno ? d.mensaje_costeno : d.mensaje;
  }

  function filaDiag(d, icono) {
    const cuerpo = modoCosteno && d.mensaje_costeno
      ? `${esc(d.mensaje_costeno)} <span class="pos">(columna ${d.columna})</span>`
      : `<strong class="pos">Línea ${d.linea}, col. ${d.columna}</strong> &mdash; ${esc(d.mensaje)}`;
    const detalle = modoCosteno && d.mensaje_costeno ? `Detalle técnico: ${d.mensaje}` : `Ir a la línea ${d.linea}`;
    return `<li class="clic" data-l="${d.linea}" data-c="${d.columna}" title="${esc(detalle)}">` +
      `<svg><use href="#${icono}"/></svg><span>${cuerpo}</span>` +
      `<span class="cod">${esc(d.codigo)}</span></li>`;
  }

  function pintarCompilacion(c) {
    resultadoVigente = true;
    const nErr = c.errores.length;
    const nAvi = c.advertencias.length;
    actualizarInsignia(nErr, nAvi);

    marcasError = new Set(c.errores.map((d) => d.linea));
    marcasAviso = new Set(c.advertencias.map((d) => d.linea));
    pintarMarcasLineas();

    /* -- Mensajes -- */
    const m = ['<li><svg><use href="#i-ok"/></svg>[INFO] Compilación iniciada…</li>'];
    c.fases.forEach((f) => {
      if (f.estado === 'ok') {
        const txt = f.id === 'lexico'
          ? `Análisis léxico completado. (${plural(c.tokens.length, 'token', 'tokens')})`
          : f.id === 'sintactico' ? 'Análisis sintáctico completado.' : 'Análisis semántico sin errores.';
        m.push(`<li><svg><use href="#i-ok"/></svg>[INFO] ${txt}</li>`);
      } else if (f.estado === 'error') {
        m.push(`<li><svg><use href="#i-error-x"/></svg>[ERROR] ${f.nombre}: ${plural(f.errores, 'error', 'errores')}.</li>`);
      } else {
        m.push(`<li><svg><use href="#i-pendiente"/></svg>[INFO] ${f.nombre} omitido: corrija primero los errores de la fase anterior.</li>`);
      }
    });
    if (c.tokens.length) {
      const donde = ['<a href="#" data-ir="reporte">Reporte</a> (los tokens)'];
      if (c.arbol) donde.push('<a href="#" data-ir="arbol">Árbol Sintáctico</a> (la estructura del programa)');
      if (c.simbolos && c.simbolos.length) donde.push('<a href="#" data-ir="simbolos">Tabla de Símbolos</a> (las variables)');
      m.push(`<li><svg style="color:#1b72e8"><use href="#i-info"/></svg><span>Resultados del análisis en las pestañas: ${donde.join(', ')}.</span></li>`);
    }
    if (nAvi) m.push(`<li><svg><use href="#i-aviso"/></svg>[ADVERTENCIA] ${plural(nAvi, 'advertencia', 'advertencias')}: revise la pestaña Advertencias.</li>`);
    const resumen = `${plural(nErr, 'error', 'errores')}, ${plural(nAvi, 'advertencia', 'advertencias')}.`;
    const banner = c.exitoso
      ? `<div class="banner ok"><svg><use href="#i-ok-oscuro"/></svg>Compilación exitosa. ${resumen}</div>`
      : `<div class="banner mal"><svg><use href="#i-error-x"/></svg>La compilación falló en el análisis ${NOMBRE_FASE[c.fase_fallida] || ''}. ${resumen}</div>`;
    $('#pane-mensajes').innerHTML = `<ul class="lista">${m.join('')}</ul>${banner}`;

    /* -- Errores / Advertencias -- */
    $('#pane-errores').innerHTML = nErr
      ? `<ul class="lista">${c.errores.map((d) => filaDiag(d, 'i-error-x')).join('')}</ul>`
      : '<div class="sin-datos">Sin errores.</div>';
    $('#pane-advertencias').innerHTML = nAvi
      ? `<ul class="lista">${c.advertencias.map((d) => filaDiag(d, 'i-aviso')).join('')}</ul>`
      : '<div class="sin-datos">Sin advertencias.</div>';
    const cE = $('#cnt-errores'); cE.textContent = nErr; cE.hidden = nErr === 0;
    const cA = $('#cnt-advertencias'); cA.textContent = nAvi; cA.hidden = nAvi === 0;

    pintarReporte(c);
    pintarArbol(c);
    pintarSimbolos(c);

    activarPestana('inferior', nErr ? 'errores' : 'mensajes');
  }

  function pintarReporte(c) {
    const LIMITE = 5000;
    const filas = c.tokens.slice(0, LIMITE).map((t, i) =>
      `<tr><td class="num">${i + 1}</td><td class="num">${t[0]}</td><td class="num">${t[1]}</td>` +
      `<td class="mono">${esc(t[2])}</td><td class="mono">${esc(t[3])}</td></tr>`).join('');
    const chips = Object.entries(c.conteo)
      .sort((a, b) => b[1] - a[1])
      .map(([tipo, n]) => `<span class="chip">${esc(tipo)}<b>${n}</b></span>`).join('');
    const total = c.tokens_total || c.tokens.length;
    const nota = total > LIMITE
      ? `<div class="sin-datos">Se muestran los primeros ${LIMITE} de ${total} tokens.</div>` : '';
    $('#pane-reporte').innerHTML = c.tokens.length
      ? `<div class="resumen">Tokens: ${c.tokens_total || c.tokens.length} &middot; Errores: ${c.errores.length} &middot; Advertencias: ${c.advertencias.length} &middot; Líneas: ${c.lineas}</div>` +
        `<table class="tabla"><thead><tr><th>N.º</th><th>Línea</th><th>Columna</th><th>Tipo de token</th><th>Valor</th></tr></thead><tbody>${filas}</tbody></table>${nota}` +
        `<div class="resumen">Cantidad por tipo de token</div><div class="chips">${chips}</div>`
      : '<div class="sin-datos">No se encontraron tokens.</div>';
  }

  const AYUDA_PANEL = {
    arbol: ['Árbol Sintáctico', 'Muestra la estructura del programa: declaraciones, asignaciones, mensajes y condicionales. Aparece cuando el programa no tiene errores léxicos ni de sintaxis.'],
    simbolos: ['Tabla de Símbolos', 'Lista las variables del programa con su tipo, la línea donde se declararon y si se leen o se les asigna un valor. Aparece cuando el programa no tiene errores léxicos ni de sintaxis.'],
  };

  function vacio(clave, extra) {
    const [t, p] = AYUDA_PANEL[clave];
    return `<div class="vacio"><svg><use href="#i-pendiente"/></svg><h3>${t}</h3><p>${p}</p>${extra ? `<p>${extra}</p>` : ''}</div>`;
  }

  function nodoArbol(n, ctx) {
    if (ctx.n++ > 4000) { ctx.cortado = true; return ''; }
    const hoja = (txt, cls = '') => `<li><div class="hoja"><span class="ico hoja-ico"></span><span class="${cls}">${txt}</span></div></li>`;
    const rama = (txt, hijos) => `<li><details open><summary><span class="ico"></span><span>${txt}</span></summary><ul>${hijos}</ul></details></li>`;
    const lista = (arr) => (arr && arr.length ? arr.map((i) => nodoArbol(i, ctx)).join('') : hoja('(vacío)', 'tenue'));
    const nombre = (s) => `<b>${esc(s)}</b>`;
    switch (n.nodo) {
      case 'Programa': return rama('Programa', lista(n.instrucciones));
      case 'Declaracion': return hoja(`Declaración: ${nombre(n.nombre)} : ${esc(n.tipo_dato)}`);
      case 'Asignacion': return rama(`Asignación: ${nombre(n.nombre)} =`, nodoArbol(n.valor, ctx));
      case 'Lectura': return hoja(`Lectura: ${nombre(n.nombre)} ← Captura.${esc(n.tipo_dato)}()`);
      case 'Mensaje': return rama('Mensaje.Texto', nodoArbol(n.valor, ctx));
      case 'Condicional':
        return rama('Si',
          (n.condicion ? rama('Condición', nodoArbol(n.condicion, ctx)) : '') +
          rama('Entonces', lista(n.entonces)) +
          (n.sino !== null && n.sino !== undefined ? rama('Sino', lista(n.sino)) : ''));
      case 'Binario': {
        const rel = ['==', '!=', '<', '>', '<=', '>='].includes(n.op);
        return rama(`${rel ? 'Comparación' : 'Operación'} ( ${esc(n.op)} )`, nodoArbol(n.izq, ctx) + nodoArbol(n.der, ctx));
      }
      case 'Unario': return rama(`Signo ( ${esc(n.op)} )`, nodoArbol(n.operando, ctx));
      case 'Numero': return hoja(`Número ${esc(n.valor)} <span class="tenue">(${esc(n.tipo_dato)})</span>`);
      case 'Cadena': return hoja(`Texto “${esc(n.valor)}”`, 'rojo');
      case 'Logico': return hoja(`Valor ${n.valor ? 'Verdadero' : 'Falso'}`);
      case 'Variable': return hoja(`Variable ${nombre(n.nombre)}`);
      default: return hoja(esc(n.nodo || '?'));
    }
  }

  function pintarArbol(c) {
    if (!c.arbol) {
      $('#pane-arbol').innerHTML = vacio('arbol', c.arbol_omitido ? 'El programa es tan grande que su árbol no se muestra (el programa sí se compila y se ejecuta).'
        : c.exitoso ? '' : 'Corrija los errores de las fases anteriores para ver el árbol.');
      return;
    }
    const ctx = { n: 0, cortado: false };
    const html = nodoArbol(c.arbol, ctx);
    $('#pane-arbol').innerHTML = `<ul class="arbol">${html}</ul>` +
      (ctx.cortado ? '<div class="sin-datos">El árbol es muy grande: se muestra solo una parte.</div>' : '');
  }

  function pintarSimbolos(c) {
    if (!c.simbolos || !c.simbolos.length) {
      $('#pane-simbolos').innerHTML = vacio('simbolos',
        c.fase_fallida === 'lexico' || c.fase_fallida === 'sintactico'
          ? 'Corrija los errores de las fases anteriores para ver las variables.'
          : (c.exitoso ? 'Este programa no declara variables.' : ''));
      return;
    }
    const filas = c.simbolos.map((s) =>
      `<tr><td class="mono">${esc(s.nombre)}</td><td>${esc(s.tipo)}</td><td class="num">${s.linea}</td>` +
      `<td>${s.asignada ? '<span class="si">Sí</span>' : '<span class="no">No</span>'}</td>` +
      `<td>${s.usada ? '<span class="si">Sí</span>' : '<span class="no">No</span>'}</td></tr>`).join('');
    $('#pane-simbolos').innerHTML =
      `<div class="resumen">Variables del programa: ${c.simbolos_total || c.simbolos.length}${(c.simbolos_total || 0) > c.simbolos.length ? ` (se muestran ${c.simbolos.length})` : ''}</div>` +
      `<table class="tabla"><thead><tr><th>Nombre</th><th>Tipo</th><th>Declarada en la línea</th><th>Recibe un valor</th><th>Se usa (se lee)</th></tr></thead><tbody>${filas}</tbody></table>`;
  }

  $('#pane-mensajes').addEventListener('click', (e) => {
    const a = e.target.closest('a[data-ir]');
    if (!a) return;
    e.preventDefault();
    activarPestana('inferior', a.dataset.ir);
  });

  ['pane-errores', 'pane-advertencias'].forEach((id) => {
    $('#' + id).addEventListener('click', (e) => {
      const li = e.target.closest('li[data-l]');
      if (li) irA(Number(li.dataset.l), Number(li.dataset.c));
    });
  });

  function limpiarResultados() {
    actualizarInsignia(0, 0);
    detenerSesion();
    ultima = null;
    resultadoVigente = false;
    quitarMarcas();
    $('#pane-mensajes').innerHTML = '<ul class="lista"><li><svg><use href="#i-ok"/></svg>[INFO] ' +
      segunModo('Listo. Presione Compilar (F7) para revisar el programa o Ejecutar (F5) para correrlo.',
        'Listo, compa. Presiona Compilar (F7) para revisar el programa o Ejecutar (F5) para correrlo.') + '</li></ul>';
    ['errores', 'advertencias', 'reporte'].forEach((p) => {
      $('#pane-' + p).innerHTML = '<div class="sin-datos">Aún no hay resultados. Presione Compilar o Ejecutar.</div>';
    });
    $('#pane-arbol').innerHTML = vacio('arbol');
    $('#pane-simbolos').innerHTML = vacio('simbolos');
    ['cnt-errores', 'cnt-advertencias'].forEach((id) => { $('#' + id).hidden = true; });
    consolaInicial();
    activarPestana('inferior', 'mensajes');
    setEstado('Listo', '');
  }

  /* ===================================================================== */
  /*  Archivos                                                              */
  /* ===================================================================== */
  function descargarArchivo(nombre, texto, tipo = 'text/plain;charset=utf-8') {
    const url = URL.createObjectURL(new Blob([texto], { type: tipo }));
    const a = document.createElement('a');
    a.href = url; a.download = nombre;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  function descargarReporte(c) {
    const nombre = (docActual() || {}).nombre || 'programa.cst';
    const L = ['REPORTE DEL COMPILADOR COSTEÑOL', `Archivo: ${nombre}`, `Fecha: ${new Date().toLocaleString('es-CO')}`, '',
      `Resultado: ${c.exitoso ? 'compilación exitosa' : 'la compilación falló en el análisis ' + (NOMBRE_FASE[c.fase_fallida] || '')}`,
      `Líneas: ${c.lineas}   Tokens: ${c.tokens.length}   Errores: ${c.errores.length}   Advertencias: ${c.advertencias.length}`, ''];
    if (c.errores.length) { L.push('ERRORES'); c.errores.forEach((d) => L.push(`  [${d.codigo}] Línea ${d.linea}, columna ${d.columna}: ${d.mensaje}`)); L.push(''); }
    if (c.advertencias.length) { L.push('ADVERTENCIAS'); c.advertencias.forEach((d) => L.push(`  [${d.codigo}] Línea ${d.linea}, columna ${d.columna}: ${d.mensaje}`)); L.push(''); }
    if (c.simbolos && c.simbolos.length) {
      L.push('TABLA DE SÍMBOLOS'); c.simbolos.forEach((s) => L.push(`  ${s.nombre.padEnd(20)} ${s.tipo.padEnd(8)} línea ${s.linea}`)); L.push('');
    }
    L.push('TOKENS', '  Línea:Col   Tipo                   Valor');
    c.tokens.forEach((t) => L.push(`  ${String(t[0]).padStart(4)}:${String(t[1]).padEnd(5)} ${t[2].padEnd(22)} ${t[3]}`));
    descargarArchivo('reporte.txt', L.join('\r\n') + '\r\n');
  }

  function guardar() {
    const d = docActual();
    let nombre = d ? d.nombre : 'programa.cst';
    if (!/\.[A-Za-z0-9]+$/.test(nombre)) nombre += '.cst';
    descargarArchivo(nombre, E.codigo.value.replace(/\n/g, '\r\n'));
  }

  $('#btn-nuevo').addEventListener('click', () => nuevoDoc());
  $('#btn-guardar').addEventListener('click', guardar);
  $('#btn-compilar').addEventListener('click', compilar);
  $('#btn-ejecutar').addEventListener('click', ejecutar);
  $('#btn-limpiar').addEventListener('click', () => {
    detenerSesion();
    consolaLimpiar();
    setEstado('Listo', '');
  });
  $('#btn-abrir').addEventListener('click', () => $('#archivo-entrada').click());
  $('#archivo-entrada').addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    if (f.size > 2_000_000) { alert('El archivo es demasiado grande (máximo 2 MB).'); e.target.value = ''; return; }
    const lector = new FileReader();
    lector.onload = () => nuevoDoc(f.name, String(lector.result).replace(/^\ufeff/, '').replace(/\r\n?/g, '\n'));
    lector.onerror = () => alert('No se pudo leer el archivo.');
    lector.readAsText(f, 'utf-8');
    e.target.value = '';
  });

  /* ===================================================================== */
  /*  Barra lateral y diálogos                                              */
  /* ===================================================================== */
  const dialogos = {
    manual: $('#dlg-manual'), ejemplos: $('#dlg-ejemplos'),
    analizador: $('#dlg-analizador'), acerca: $('#dlg-acerca'),
  };

  /* ===================================================================== */
  /*  Modo celular: una vista a la vez, menú desplegable y barra inferior   */
  /* ===================================================================== */
  const esMovil = () => document.documentElement.classList.contains('movil');
  const esTactil = () => window.matchMedia('(pointer: coarse)').matches;
  const PRINCIPAL = $('#principal');

  function marcarBarra(v) {
    $$('#barra-movil button').forEach((b) => b.classList.toggle('activo', b.dataset.vista === v));
  }
  function setVista(v) {
    if (!esMovil()) return;
    if (v === 'asistente') { abrirAsistente(); return; }
    if (A.panel && !A.panel.hidden) cerrarAsistente();
    PRINCIPAL.dataset.vista = v;
    marcarBarra(v);
    if (v === 'editor') actualizarCursor();
  }
  function abrirMenu(abrir) {
    $('#lateral').classList.toggle('abierto', abrir);
    $('#cortina').hidden = !abrir;
    $('#btn-menu').setAttribute('aria-expanded', String(abrir));
  }
  function actualizarInsignia(nErr, nAvi) {
    const b = $('#badge-resultados');
    const n = nErr || nAvi;
    b.hidden = !n;
    b.textContent = n > 99 ? '99+' : String(n || 0);
    b.classList.toggle('aviso', !nErr);
  }
  $('#btn-menu').addEventListener('click', () => abrirMenu(!$('#lateral').classList.contains('abierto')));
  $('#cortina').addEventListener('click', () => abrirMenu(false));
  $('#barra-movil').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-vista]');
    if (b) setVista(b.dataset.vista);
  });
  document.addEventListener('movilcambio', () => {
    abrirMenu(false);
    if (esMovil()) setVista('editor');
    if (document.documentElement.style.getPropertyValue('--tam-codigo')) aplicarTamano($('#rng-tam').value);
  });

  function marcarNav(nombre) {
    $$('.nav-item').forEach((b) => b.classList.toggle('activo', b.dataset.nav === nombre));
  }
  function navReposo() {
    const abierto = $('#asistente') && !$('#asistente').hidden;
    marcarNav(abierto ? 'asistente' : 'inicio');
  }

  $$('.nav-item').forEach((b) => {
    b.addEventListener('click', () => {
      const n = b.dataset.nav;
      if (esMovil()) abrirMenu(false);
      if (n === 'inicio') { marcarNav('inicio'); if (esMovil()) setVista('editor'); else E.codigo.focus(); return; }
      if (n === 'asistente') { if (esMovil()) setVista('asistente'); else alternarAsistente(); return; }
      marcarNav(n);
      if (n === 'ejemplos') cargarEjemplos();
      if (n === 'manual') cargarManual();
      dialogos[n].showModal();
    });
  });
  $$('dialog').forEach((d) => {
    d.addEventListener('close', navReposo);
    d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
    $$('[data-cerrar]', d).forEach((b) => b.addEventListener('click', () => d.close()));
  });

  /* ---- Ejemplos ---- */
  let ejemplos = null;
  async function cargarEjemplos() {
    const ul = $('#lista-ejemplos');
    if (!ejemplos) {
      try { ejemplos = await (await fetch('/api/ejemplos')).json(); }
      catch (_) { ul.innerHTML = '<li class="dlg-nota">No se pudieron cargar los ejemplos.</li>'; return; }
    }
    ul.innerHTML = ejemplos.map((ej, i) =>
      `<li class="${/rror/.test(ej.titulo) ? 'err' : 'ok'}"><button type="button" data-i="${i}"><svg><use href="#i-documento"/></svg>` +
      `<span>${esc(ej.titulo)}<small>${esc(ej.archivo)}</small></span></button></li>`).join('')
      || '<li class="dlg-nota">No hay ejemplos en la carpeta ejemplos/.</li>';
  }
  $('#lista-ejemplos').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-i]');
    if (!b) return;
    const ej = ejemplos[Number(b.dataset.i)];
    $('#dlg-ejemplos').close();
    nuevoDoc(ej.archivo, ej.codigo.replace(/\r\n?/g, '\n'));
  });

  /* ---- Manual de uso ---- */
  let manualCargado = false;
  async function cargarManual() {
    if (manualCargado) return;
    const cont = $('#manual-contenido');
    try {
      const [html, cat] = await Promise.all([
        fetch('manual.html').then((r) => { if (!r.ok) throw new Error(); return r.text(); }),
        fetch('/api/catalogo').then((r) => r.json()).catch(() => []),
      ]);
      cont.innerHTML = html;
      construirCatalogo(cat);
      prepararEjemplosManual();
      construirIndiceManual();
      manualCargado = true;
    } catch (_) {
      cont.innerHTML = '<p class="dlg-nota">No se pudo cargar el manual (archivo web/manual.html).</p>';
    }
  }

  function construirCatalogo(cat) {
    const dest = $('#catalogo-mensajes');
    if (!dest) return;
    if (!cat.length) { dest.innerHTML = '<p class="dlg-nota">No se pudo cargar la lista de mensajes.</p>'; return; }
    let fase = '';
    let filas = '';
    cat.forEach((c) => {
      if (c.fase !== fase) {
        fase = c.fase;
        filas += `<tr class="fase"><th colspan="4">${esc(fase)}</th></tr>`;
      }
      filas += `<tr data-buscar="${esc((c.codigo + ' ' + c.titulo + ' ' + c.significa + ' ' + c.corregir).toLowerCase())}">` +
        `<td><code>${esc(c.codigo)}</code></td><td><span class="etq ${c.tipo === 'Error' ? 'e' : 'a'}">${c.tipo}</span></td>` +
        `<td><strong>${esc(c.titulo)}</strong><br>${esc(c.significa)}</td><td>${esc(c.corregir)}</td></tr>`;
    });
    dest.innerHTML = '<input type="search" class="filtro" id="filtro-catalogo" placeholder="Buscar un código o una palabra (por ejemplo E-SIN-01 o punto y coma)…" aria-label="Buscar en la lista de mensajes">' +
      `<table><thead><tr><th>Código</th><th>Tipo</th><th>Qué significa</th><th>Cómo corregirlo</th></tr></thead><tbody>${filas}</tbody></table>`;
    $('#filtro-catalogo').addEventListener('input', (e) => {
      const q = e.target.value.trim().toLowerCase();
      $$('tbody tr[data-buscar]', dest).forEach((tr) => { tr.hidden = q && !tr.dataset.buscar.includes(q); });
    });
  }

  function prepararEjemplosManual() {
    $$('#manual-contenido pre.codigo').forEach((pre) => {
      const src = pre.textContent.replace(/^\n/, '').replace(/\s+$/, '') + '\n';
      pre.innerHTML = resaltar(src.replace(/\n$/, ''));
      if (pre.hasAttribute('data-sin-probar')) return;
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'probar'; b.textContent = 'Probar en el editor';
      b.addEventListener('click', () => {
        dialogos.manual.close();
        nuevoDoc(`ejemplo_manual_${contadorDocs}.cst`, src);
      });
      pre.appendChild(b);
    });
  }

  function construirIndiceManual() {
    const indice = $('#manual-indice');
    const cont = $('#manual-contenido');
    const secciones = $$('h2', cont);
    indice.innerHTML = secciones.map((h, i) => {
      if (!h.id) h.id = 'm' + i;
      return `<a href="#${h.id}" data-id="${h.id}">${esc(h.textContent)}</a>`;
    }).join('');
    const irA = (id) => {
      const dest = document.getElementById(id);
      if (dest) cont.scrollTo({ top: dest.offsetTop - cont.offsetTop - 8, behavior: 'smooth' });
    };
    cont.addEventListener('click', (e) => {
      const a = e.target.closest('a[href^="#"]');
      if (!a) return;
      e.preventDefault();
      irA(a.getAttribute('href').slice(1));
    });
    indice.addEventListener('click', (e) => {
      const a = e.target.closest('a[data-id]');
      if (!a) return;
      e.preventDefault();
      irA(a.dataset.id);
    });
    // marca en el índice la sección que se está leyendo
    const marcar = () => {
      let actual = secciones[0];
      secciones.forEach((h) => { if (h.offsetTop - cont.offsetTop <= cont.scrollTop + 24) actual = h; });
      $$('a', indice).forEach((a) => a.classList.toggle('activo', actual && a.dataset.id === actual.id));
    };
    cont.addEventListener('scroll', marcar);
    marcar();
  }

  /* ===================================================================== */
  /*  Asistente de IA                                                       */
  /* ===================================================================== */
  const A = {
    panel: $('#asistente'), cuerpo: $('#cuerpo'), msgs: $('#asi-mensajes'), texto: $('#asi-texto'),
    enviar: $('#asi-enviar'), config: $('#asi-config'), sugerencias: $('#asi-sugerencias'), contexto: $('#asi-contexto'),
  };
  const CLAVE_CHAT = 'costenol.chat';
  const SUGERENCIAS = [
    'Quiero calcular la edad de una persona con su año de nacimiento',
    '¿Cómo se declaran los enteros?',
    '¿Cómo le pido un dato al usuario?',
    'Revisa mi código y dime qué falla',
  ];
  const BIENVENIDA = 'Hola, soy el asistente de Costeñol. Pídame un programa (por ejemplo «calcular el promedio de tres notas») ' +
    'o pregúnteme cómo se hace algo en el lenguaje o en el compilador. Todo el código que le entrego se revisa con el compilador antes de mostrárselo.';
  let chat = [];                 // { rol, contenido, bloques?, reintentos? }
  let iaEstado = null;
  let asiOcupado = false;
  let contadorAsistente = 1;

  function inlineMd(s) {
    return esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  }

  function mdLite(texto) {
    let html = '';
    let lista = null;
    let parrafo = [];
    const cerrarP = () => { if (parrafo.length) { html += `<p>${inlineMd(parrafo.join(' '))}</p>`; parrafo = []; } };
    const cerrarL = () => { if (lista) { html += `</${lista}>`; lista = null; } };
    for (const l of texto.split('\n')) {
      const s = l.trim();
      let m;
      if (!s) { cerrarP(); cerrarL(); continue; }
      if ((m = s.match(/^[-*•]\s+(.*)$/))) {
        cerrarP(); if (lista !== 'ul') { cerrarL(); html += '<ul>'; lista = 'ul'; }
        html += `<li>${inlineMd(m[1])}</li>`; continue;
      }
      if ((m = s.match(/^\d+[.)]\s+(.*)$/))) {
        cerrarP(); if (lista !== 'ol') { cerrarL(); html += '<ol>'; lista = 'ol'; }
        html += `<li>${inlineMd(m[1])}</li>`; continue;
      }
      if ((m = s.match(/^#{1,4}\s+(.*)$/))) { cerrarP(); cerrarL(); html += `<p><strong>${inlineMd(m[1])}</strong></p>`; continue; }
      cerrarL();
      parrafo.push(s);
    }
    cerrarP(); cerrarL();
    return html;
  }

  function bloqueHTML(codigo, v) {
    const ok = v ? v.exitoso : null;
    const estado = ok === null ? '' : ok
      ? '<span class="ok">✔ Compila sin errores</span>'
      : `<span class="mal">⚠ Tiene ${plural(v.errores.length, 'error', 'errores')}</span>`;
    const errores = v && !v.exitoso
      ? `<ul class="bloque-errores">${v.errores.slice(0, 5).map((e) => `<li>Línea ${e.linea}: ${esc(e.mensaje)}</li>`).join('')}</ul>` : '';
    return `<div class="bloque-codigo"><div class="bloque-cab">${estado}<span class="espacio"></span>` +
      '<button type="button" data-accion="copiar">Copiar</button>' +
      '<button type="button" data-accion="abrir">Abrir en el editor</button>' +
      (ok ? '<button type="button" class="verde" data-accion="ejecutar">Abrir y ejecutar</button>' : '') +
      `</div><pre>${resaltar(codigo)}</pre>${errores}</div>`;
  }

  function renderAsistente(texto, bloques, reintentos) {
    const re = /```[ \t]*[A-Za-z0-9_+\-]*[ \t]*\r?\n([\s\S]*?)```/g;
    let html = '';
    let ultimo = 0;
    let i = 0;
    let m;
    while ((m = re.exec(texto)) !== null) {
      html += mdLite(texto.slice(ultimo, m.index));
      html += bloqueHTML(m[1].replace(/\r?\n$/, ''), (bloques || [])[i]);
      ultimo = m.index + m[0].length;
      i++;
    }
    html += mdLite(texto.slice(ultimo));
    if (reintentos > 0) {
      html += `<div class="nota-revision">El compilador encontró errores en la primera versión del código y el asistente lo corrigió automáticamente (${plural(reintentos, 'intento', 'intentos')}).</div>`;
    }
    return html;
  }

  function burbuja(clase, html) {
    const d = document.createElement('div');
    d.className = 'burbuja ' + clase;
    d.innerHTML = html;
    A.msgs.appendChild(d);
    A.msgs.scrollTop = A.msgs.scrollHeight;
    return d;
  }

  function guardarChat() {
    try { localStorage.setItem(CLAVE_CHAT, JSON.stringify(chat.slice(-30))); } catch (_) { /* se ignora */ }
  }

  function pintarChat() {
    A.msgs.innerHTML = '';
    burbuja('sistema', esc(BIENVENIDA));
    chat.forEach((m) => {
      if (m.rol === 'user') burbuja('usuario', esc(m.contenido));
      else burbuja('asistente', renderAsistente(m.contenido, m.bloques, m.reintentos));
    });
    A.sugerencias.innerHTML = chat.length ? '' : SUGERENCIAS.map((s, i) => `<button type="button" data-s="${i}">${esc(s)}</button>`).join('');
  }

  function mostrarConfigIA(mostrar) {
    A.config.hidden = !mostrar;
    if (mostrar) $('#asi-clave').focus();
  }

  function textoEstadoIA() {
    const e = $('#asi-estado-clave');
    if (iaEstado && iaEstado.configurada) {
      e.className = 'asi-estado ok';
      e.textContent = `Clave guardada (${iaEstado.sufijo || '••••'}), tomada ${iaEstado.origen === 'variable' ? 'de la variable de entorno ANTHROPIC_API_KEY' : 'del archivo ia_config.json'}. Modelo: ${iaEstado.modelo}.`;
    } else {
      e.className = 'asi-estado';
      e.textContent = 'Todavía no hay una clave guardada.';
    }
  }

  async function cargarEstadoIA() {
    try {
      iaEstado = await (await fetch('/api/ia/estado')).json();
      $('#asi-modelo').value = iaEstado.modelo || '';
      textoEstadoIA();
      $('#asi-ajustes').hidden = iaEstado.configurable === false;       // en la nube la clave va en el servidor
      if (iaEstado.configurable === false) {
        mostrarConfigIA(false);
        if (!iaEstado.configurada && !A.msgs.querySelector('.fallo.sin-ia')) {
          burbuja('fallo sin-ia', 'El asistente no está activado en este servidor: falta la clave de API (variable ANTHROPIC_API_KEY).');
        }
      } else if (!iaEstado.configurada) mostrarConfigIA(true);
    } catch (_) { /* sin conexión: se verá al enviar */ }
  }

  function abrirAsistente() {
    A.panel.hidden = false;
    A.cuerpo.classList.add('con-asistente');
    marcarNav('asistente');
    pintarChat();
    cargarEstadoIA();
    if (esMovil()) marcarBarra('asistente');
    else A.texto.focus();                                       // en el celular no se abre el teclado solo
  }
  function cerrarAsistente() {
    A.panel.hidden = true;
    A.cuerpo.classList.remove('con-asistente');
    marcarNav('inicio');
    if (esMovil()) marcarBarra(PRINCIPAL.dataset.vista);
  }
  function alternarAsistente() { if (A.panel.hidden) abrirAsistente(); else cerrarAsistente(); }

  async function enviarAsistente(textoDirecto) {
    const texto = (typeof textoDirecto === 'string' ? textoDirecto : A.texto.value).trim();
    if (!texto || asiOcupado) return;
    if (!iaEstado || !iaEstado.configurada) {
      if (iaEstado && iaEstado.configurable === false) return;
      mostrarConfigIA(true);
      return;
    }
    asiOcupado = true;
    A.enviar.disabled = true;
    A.texto.value = '';
    A.sugerencias.innerHTML = '';
    chat.push({ rol: 'user', contenido: texto });
    burbuja('usuario', esc(texto));
    const espera = burbuja('asistente pensando', '<span></span><span></span><span></span>');
    const conContexto = A.contexto.checked;
    const errores = conContexto && ultima && resultadoVigente
      ? ultima.errores.slice(0, 20).map((e) => `Línea ${e.linea}, columna ${e.columna} [${e.codigo}]: ${e.mensaje}`) : [];
    try {
      const r = await llamar('/api/asistente', {
        mensajes: chat.map((m) => ({ rol: m.rol, contenido: m.contenido })),
        codigo: conContexto ? E.codigo.value : '',
        errores,
      });
      espera.remove();
      chat.push({ rol: 'assistant', contenido: r.respuesta, bloques: r.bloques, reintentos: r.reintentos });
      burbuja('asistente', renderAsistente(r.respuesta, r.bloques, r.reintentos));
      guardarChat();
    } catch (err) {
      espera.remove();
      chat.pop();
      A.texto.value = texto;
      A.msgs.lastElementChild && A.msgs.lastElementChild.classList.contains('usuario') && A.msgs.lastElementChild.remove();
      burbuja('fallo', esc(err.message));
      if (/clave|modelo/i.test(err.message)) { await cargarEstadoIA(); mostrarConfigIA(true); }
    } finally {
      asiOcupado = false;
      A.enviar.disabled = false;
      A.texto.focus();
    }
  }

  async function copiarTexto(t) {
    try { await navigator.clipboard.writeText(t); return true; } catch (_) { /* alternativa */ }
    const ta = document.createElement('textarea');
    ta.value = t; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (_) { /* se ignora */ }
    ta.remove();
    return ok;
  }

  A.msgs.addEventListener('click', async (e) => {
    const b = e.target.closest('button[data-accion]');
    if (!b) return;
    const codigo = b.closest('.bloque-codigo').querySelector('pre').textContent;
    if (b.dataset.accion === 'copiar') {
      const ok = await copiarTexto(codigo);
      b.textContent = ok ? '¡Copiado!' : 'No se pudo copiar';
      setTimeout(() => { b.textContent = 'Copiar'; }, 1500);
    } else {
      nuevoDoc(`asistente_${contadorAsistente++}.cst`, codigo + '\n');
      if (b.dataset.accion === 'ejecutar') ejecutar();
    }
  });
  A.sugerencias.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-s]');
    if (b) enviarAsistente(SUGERENCIAS[Number(b.dataset.s)]);
  });
  A.enviar.addEventListener('click', () => enviarAsistente());
  A.texto.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviarAsistente(); }
  });
  $('#asi-cerrar').addEventListener('click', cerrarAsistente);
  $('#asi-ajustes').addEventListener('click', () => mostrarConfigIA(A.config.hidden));
  $('#asi-nuevo').addEventListener('click', () => {
    if (chat.length && !confirm('¿Empezar una conversación nueva? Se borrará la actual.')) return;
    chat = [];
    guardarChat();
    pintarChat();
  });
  $('#asi-guardar').addEventListener('click', async () => {
    const estado = $('#asi-estado-clave');
    try {
      iaEstado = await llamar('/api/ia/config', { clave: $('#asi-clave').value, modelo: $('#asi-modelo').value });
      $('#asi-clave').value = '';
      textoEstadoIA();
      if (iaEstado.configurada) mostrarConfigIA(false);
    } catch (err) {
      estado.className = 'asi-estado mal';
      estado.textContent = err.message;
    }
  });
  $('#asi-quitar').addEventListener('click', async () => {
    try { iaEstado = await llamar('/api/ia/borrar', {}); textoEstadoIA(); } catch (err) { $('#asi-estado-clave').textContent = err.message; }
  });

  /* ===================================================================== */
  /*  Exportar                                                              */
  /* ===================================================================== */
  const CLAVE_FORMATO = 'costenol.formato';
  let formatos = null;
  let formatoElegido = 'python';

  function nombreBase() {
    const d = docActual();
    return ((d && d.nombre) || 'programa').replace(/\.[^.]*$/, '');
  }

  function pintarFormatos() {
    $('#lista-formatos').innerHTML = formatos.map((f) =>
      `<label class="formato${f.disponible ? '' : ' inactivo'}${f.id === formatoElegido ? ' elegido' : ''}">` +
      `<input type="radio" name="formato" value="${f.id}" ${f.id === formatoElegido ? 'checked' : ''} ${f.disponible ? '' : 'disabled'}>` +
      `<span><strong>${esc(f.nombre)}</strong><span class="ext">${esc(f.extension)}</span></span>` +
      `<small>${esc(f.descripcion)}<br><code>${esc(f.como.replace('{archivo}', 'archivo' + f.extension))}</code></small></label>`).join('');
  }

  async function abrirExportar() {
    const est = $('#exp-estado');
    est.className = 'exp-estado';
    est.textContent = '';
    $('#exp-nombre').value = nombreBase();
    try {
      formatos = await (await fetch('/api/exportar/formatos')).json();
    } catch (_) {
      formatos = null;
    }
    if (!formatos) { $('#lista-formatos').innerHTML = '<p class="dlg-nota">No se pudo contactar el compilador.</p>'; }
    else {
      try { formatoElegido = localStorage.getItem(CLAVE_FORMATO) || 'python'; } catch (_) { formatoElegido = 'python'; }
      if (!formatos.some((f) => f.id === formatoElegido && f.disponible)) formatoElegido = 'python';
      pintarFormatos();
    }
    $('#dlg-exportar').showModal();
  }

  $('#lista-formatos').addEventListener('change', (e) => {
    if (e.target.name !== 'formato') return;
    formatoElegido = e.target.value;
    try { localStorage.setItem(CLAVE_FORMATO, formatoElegido); } catch (_) { /* se ignora */ }
    pintarFormatos();
  });

  function base64ABlob(b64, mime) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime });
  }

  // Pregunta al usuario dónde guardar (Chrome/Edge); si el navegador no puede, usa la descarga normal.
  async function guardarComo(blob, archivo, formato) {
    if (window.showSaveFilePicker) {
      try {
        const ext = (archivo.match(/\.[^.]+$/) || [''])[0];
        const tipoMime = (blob.type || 'application/octet-stream').split(';')[0];
        const manejador = await window.showSaveFilePicker({
          suggestedName: archivo,
          types: [{ description: formato.nombre, accept: { [tipoMime]: [ext] } }],
        });
        const w = await manejador.createWritable();
        await w.write(blob);
        await w.close();
        return { guardado: true, nombre: manejador.name, donde: 'en la carpeta que eligió' };
      } catch (err) {
        if (err && err.name === 'AbortError') return { guardado: false, cancelado: true };
        /* otro problema: se intenta la descarga normal */
      }
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = archivo;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
    return { guardado: true, nombre: archivo, donde: 'en la carpeta de descargas del navegador' };
  }

  $('#exp-guardar').addEventListener('click', async () => {
    const est = $('#exp-estado');
    const boton = $('#exp-guardar');
    const formato = (formatos || []).find((f) => f.id === formatoElegido);
    if (!formato) return;
    boton.disabled = true;
    est.className = 'exp-estado';
    est.textContent = 'Preparando el archivo…';
    try {
      const r = await llamar('/api/exportar', { codigo: E.codigo.value, formato: formatoElegido, nombre: $('#exp-nombre').value });
      const res = await guardarComo(base64ABlob(r.base64, r.mime), r.archivo, formato);
      if (res.cancelado) { est.textContent = 'Se canceló: no se guardó nada.'; return; }
      est.className = 'exp-estado ok';
      est.innerHTML = `Guardado <code>${esc(res.nombre)}</code> ${esc(res.donde)}.<br>${esc(r.como.replace(r.archivo, res.nombre))}`;
    } catch (err) {
      est.className = 'exp-estado mal';
      est.innerHTML = esc(err.message) + (/errores/.test(err.message) ? ' <a id="ver-errores">Ver los errores</a>' : '');
      const ver = $('#ver-errores');
      if (ver) ver.addEventListener('click', () => { $('#dlg-exportar').close(); compilar(); });
    } finally {
      boton.disabled = false;
    }
  });
  $('#btn-exportar').addEventListener('click', abrirExportar);

  /* ---- Configuración ---- */
  function aplicarTamano(valor) {
    const p = Number(valor) / 100;
    const base = esMovil() ? [1.0, 1.5] : [1.15, 1.55];
    document.documentElement.style.setProperty('--tam-codigo', `${(base[0] * p).toFixed(3)}rem`);
    document.documentElement.style.setProperty('--alto-linea', `${(base[1] * p).toFixed(3)}rem`);
    $('#val-tam').textContent = `${valor} %`;
    $('#rng-tam').value = valor;
  }
  function guardarConfig() {
    try {
      localStorage.setItem(CLAVE_CONFIG, JSON.stringify({
        tam: $('#rng-tam').value, auto: E.chkAuto.checked, reporte: E.chkReporte.checked,
        autocompletar: $('#chk-autocompletar').checked,
        costeno: $('#chk-costeno').checked,
      }));
    } catch (_) { /* se ignora */ }
  }
  $('#btn-config').addEventListener('click', () => $('#dlg-config').showModal());
  $('#rng-tam').addEventListener('input', (e) => { aplicarTamano(e.target.value); guardarConfig(); });
  E.chkAuto.addEventListener('change', guardarConfig);
  $('#chk-costeno').addEventListener('change', (e) => {
    modoCosteno = e.target.checked;
    guardarConfig();
    if (ultima) pintarCompilacion(ultima);
  });
  $('#chk-autocompletar').addEventListener('change', (e) => {
    autocompletar = e.target.checked;
    if (!autocompletar) ocultarSugerencias();
    guardarConfig();
  });
  E.chkReporte.addEventListener('change', guardarConfig);

  /* ---- Controles de ventana ---- */
  $('#btn-max').addEventListener('click', () => {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
    else document.exitFullscreen?.();
  });
  $('#btn-min').addEventListener('click', () => { if (document.fullscreenElement) document.exitFullscreen?.(); });
  $('#btn-cerrar').addEventListener('click', async () => {
    cerrando = true;
    await detenerSesion();
    if (!modoNube) { try { await fetch('/api/cerrar', { method: 'POST' }); } catch (_) { /* ya cerrado */ } }
    window.close();
    setTimeout(() => { $('#cierre').hidden = false; }, 250);
  });

  /* ---- Latido: permite que Python se cierre cuando se cierra la ventana ---- */
  // En la versión en línea NO hay latido: cualquier respuesta del servidor cuenta como actividad y
  // le impediría "dormir" (Railway Serverless).
  function latido() { if (!cerrando && !modoNube) fetch('/api/latido', { method: 'POST' }).catch(() => {}); }
  function iniciarLatido() {
    if (modoNube) return;
    setInterval(latido, 2000);
    latido();
  }
  window.addEventListener('pagehide', () => {
    if (modoNube) return;
    try { navigator.sendBeacon('/api/cerrar'); } catch (_) { /* se ignora */ }
  });
  async function cargarModo() {
    try { modoNube = !!(await (await fetch('/api/modo')).json()).nube; } catch (_) { modoNube = false; }
    iniciarLatido();
  }

  /* ===================================================================== */
  /*  Arranque                                                              */
  /* ===================================================================== */
  function iniciar() {
    cargarModo();
    try {
      const cfg = JSON.parse(localStorage.getItem(CLAVE_CONFIG) || 'null');
      if (cfg) {
        aplicarTamano(cfg.tam || 100);
        E.chkAuto.checked = !!cfg.auto;
        E.chkReporte.checked = !!cfg.reporte;
        autocompletar = cfg.autocompletar !== false;
        $('#chk-autocompletar').checked = autocompletar;
        modoCosteno = cfg.costeno !== false;
        $('#chk-costeno').checked = modoCosteno;
      }
    } catch (_) { /* sin configuración */ }

    try {
      const d = JSON.parse(localStorage.getItem(CLAVE_DOCS) || 'null');
      if (d && Array.isArray(d.docs) && d.docs.length && d.docs.every((x) => x && typeof x.codigo === 'string')) {
        docs = d.docs;
        activoId = docs.some((x) => x.id === d.activo) ? d.activo : docs[0].id;
        contadorDocs = d.contador || docs.length + 1;
      }
    } catch (_) { /* sin documentos guardados */ }
    if (!docs.length) {
      docs = [{ id: 'd1', nombre: 'principal.cst', codigo: MUESTRA }];
      activoId = 'd1';
    }
    mostrarDoc();
    limpiarResultados();
    try {
      const c = JSON.parse(localStorage.getItem(CLAVE_CHAT) || 'null');
      if (Array.isArray(c)) chat = c.filter((m) => m && (m.rol === 'user' || m.rol === 'assistant') && typeof m.contenido === 'string');
    } catch (_) { /* sin conversación guardada */ }

    let visto = false;
    try { visto = localStorage.getItem(CLAVE_MANUAL) === '1'; } catch (_) { /* sin almacenamiento */ }
    if (!visto) {
      try { localStorage.setItem(CLAVE_MANUAL, '1'); } catch (_) { /* se ignora */ }
      marcarNav('manual');
      cargarManual();
      dialogos.manual.showModal();
    }
  }
  iniciar();
})();
