/* Detecta si la pantalla es de teléfono y ajusta el alto cuando aparece el teclado.
   Se carga en la cabecera (antes de dibujar la página) para que no haya "saltos". */
(function () {
  'use strict';
  var raiz = document.documentElement;

  // Modo móvil: pantallas angostas, o un teléfono girado (poca altura con pantalla táctil).
  var consulta = window.matchMedia('(max-width: 820px), (max-height: 520px) and (pointer: coarse)');
  function aplicarModo() {
    raiz.classList.toggle('movil', consulta.matches);
    document.dispatchEvent(new Event('movilcambio'));
  }
  aplicarModo();
  if (consulta.addEventListener) consulta.addEventListener('change', aplicarModo);
  else if (consulta.addListener) consulta.addListener(aplicarModo);

  // Alto realmente visible (descontando el teclado en pantalla) y detección del teclado.
  var vv = window.visualViewport;
  var ancho = window.innerWidth;
  var maximo = 0;
  function medir() {
    if (window.innerWidth !== ancho) { ancho = window.innerWidth; maximo = 0; }   // giró el aparato
    if (vv && vv.scale > 1.02) return;                                             // con zoom no se mide
    var alto = vv ? vv.height : window.innerHeight;
    raiz.style.setProperty('--alto-visible', alto + 'px');
    maximo = Math.max(maximo, alto);
    raiz.classList.toggle('teclado', raiz.classList.contains('movil') && alto < maximo * 0.75);
  }
  medir();
  window.addEventListener('resize', medir);
  if (vv) { vv.addEventListener('resize', medir); vv.addEventListener('scroll', medir); }
})();
