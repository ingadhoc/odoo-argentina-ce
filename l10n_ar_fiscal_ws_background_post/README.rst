=================================================
Validación en background por lotes (CE)
=================================================

Puente entre la cola de validación en background y los web services fiscales: la
cola pide la autorización de a lotes, un pedido por lote, en vez de un pedido por
comprobante.

Se instala solo cuando están instalados ``l10n_ar_fiscal_ws`` y
``account_background_post``. No agrega campos, vistas ni parámetros.

Características
===============

- El cron de validación en background arma los lotes con el mismo criterio que el
  posteo manual —compañía, diario y tipo de comprobante, del más viejo al más
  nuevo, partidos por ``l10n_ar_fiscal_ws.batch_size``— y postea un lote por vez.
- Un rechazo del servicio le carga el intento al comprobante que el servicio
  rechazó. Los que venían detrás no llegaron a enviarse, así que no pagan el
  intento y vuelven a la cola en la misma corrida.
- Un error que no es una respuesta del servicio (la conexión, la base, una
  validación) no dice qué comprobante rompió: ahí el lote se reintenta de a uno,
  con el circuito de siempre, que le carga el intento al que corresponde.
- Si otro proceso está facturando el mismo diario, el lote queda para la próxima
  corrida sin cargarle el intento a nadie.
- El botón de validar con varios comprobantes seleccionados también manda un
  pedido por lote, en vez de uno por comprobante. El tope del asistente no
  cambia: arriba de ``account_background_post.batch_size`` sigue pidiendo que se
  validen en background.
- Los comprobantes de la cola que no facturan por web service siguen validándose
  de a uno.
- Marcar un comprobante para la cola gana sobre pedir la autorización: un diferido
  no queda posteado, así que el lote no lo manda al servicio.

Detalles Técnicos
=================

Métodos nuevos
--------------

- ``account.move._l10n_ar_background_post_batch()``: postea un lote de la cola y
  devuelve cuántos comprobantes quedaron resueltos y cuáles conviene reintentar en
  la misma corrida.
- ``account.move._l10n_ar_background_post_failed(error)``: reprograma el
  comprobante o agota los reintentos y deja el motivo en el chatter, igual que el
  cron original.

Métodos heredados
-----------------

- ``account.move._cron_background_post_invoices()``: arma los lotes y los postea,
  y delega en el circuito original lo que no va por web service.
- ``account.move._post()``: resuelve primero el diferido a background, para que el
  orden en que se encadenan los dos ``_post`` deje de importar.
- ``validate.account.move.validate_move()``: valida de una sola vez los
  comprobantes que van por web service, y deja el resto en el bucle original.

Limitaciones conocidas
======================

- El tamaño del lote sale de ``l10n_ar_fiscal_ws.batch_size``, no de
  ``account_background_post.batch_size``: el que manda es el del pedido al
  servicio.
- Adentro de un lote los comprobantes van del más viejo al más nuevo, porque es el
  orden en que el servicio los acepta. Eso pisa la prioridad de la cola, donde los
  comprobantes sin fecha programada van antes que los reprogramados.

Bug Tracker
===========

Los errores se reportan en `GitHub Issues
<https://github.com/ingadhoc/odoo-argentina-ce/issues>`_.

Credits
=======

* ADHOC SA
