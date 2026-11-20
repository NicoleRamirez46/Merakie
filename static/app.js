/* app.js · el ÚNICO JavaScript de la plataforma (muy poco, a propósito).
   Todo lo demás (guardar, validar, calcular) lo hace Python en el servidor. */

// 1) Pide confirmación antes de enviar un formulario que tenga data-confirmar="...".
//    Ejemplo en HTML:  <form data-confirmar="¿Seguro que quieres cancelar?">
document.addEventListener("submit", function (e) {
  var mensaje = e.target.dataset.confirmar;
  if (mensaje && !confirm(mensaje)) e.preventDefault();
});

// 2) Horas disponibles: cuando la persona cambia el servicio o la fecha, le preguntamos
//    al servidor qué horas están libres y llenamos la lista desplegable "hora".
function cargarHoras(form) {
  var servicio = form.querySelector("[name=servicio_id]").value;
  var fecha = form.querySelector("[name=fecha]").value;
  var lista = form.querySelector("[name=hora]");
  lista.innerHTML = "";
  if (!servicio || !fecha) return;
  fetch(form.dataset.urlHoras + "?servicio_id=" + encodeURIComponent(servicio) + "&fecha=" + encodeURIComponent(fecha))
    .then(function (r) { return r.json(); })
    .then(function (datos) {
      if (datos.horas.length === 0) {
        lista.innerHTML = '<option value="">No hay horas libres ese día</option>';
        return;
      }
      datos.horas.forEach(function (h) {
        var op = document.createElement("option");
        op.value = h;
        op.textContent = h;   // textContent (no innerHTML): así nada se interpreta como código
        lista.appendChild(op);
      });
    });
}
document.querySelectorAll("form[data-url-horas]").forEach(function (form) {
  form.querySelector("[name=servicio_id]").addEventListener("change", function () { cargarHoras(form); });
  form.querySelector("[name=fecha]").addEventListener("change", function () { cargarHoras(form); });
  cargarHoras(form);
});
