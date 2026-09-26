====================================
Web Services Fiscales Argentina
====================================

Conexión con los web services fiscales de ARCA y facturación electrónica: el pedido
de autorización se arma con mapeos declarativos, no con código por servicio.

Características
===============

- Autorización de facturas de venta contra ARCA al confirmarlas, con el número del
  comprobante pedido al servicio antes de numerar.
- Tres servicios de facturación declarados: factura electrónica sin detalle (WSFE),
  de exportación (WSFEX) y bono fiscal electrónico (WSBFE). El servicio de cada
  diario sale de su sistema de punto de venta.
- Mapeo declarativo del pedido y de la respuesta: qué campo de Odoo va a cada campo
  del servicio se define en datos (``l10n_ar.fiscal.ws.mapping`` y sus líneas), y lo
  que no se puede expresar en datos lo resuelve un "provider" del modelo.
- Consulta de la cotización del día a ARCA desde la factura, que la aplica y la
  registra en el historial.
- Validación local cuando se está en homologación sin certificados, para poder
  trabajar sin trámite previo.
- Certificados: alias, pedido de certificado, carga del par clave/certificado y
  tickets de acceso (WSAA) con renovación automática al vencer.
- Consulta del padrón alcance 5 de ARCA para actualizar datos de un contacto, y
  consulta del monto obligado de recepción (WSFECRED).
- Código QR, código de autorización y su vencimiento en el comprobante impreso.
- Rechazo de ARCA: la factura vuelve a borrador sin autorización, con el motivo
  del organismo en el historial y el XML enviado y recibido guardados.
- Recuperación de comprobantes: cuando el organismo autoriza y la respuesta no
  llega, un asistente en el diario recorre el rango de números con
  ``FECompConsultar``, los compara con los borradores y propone asignarlos o
  crearlos, con la opción de neutralizarlos en el acto.

Detalles Técnicos
=================

Modelos nuevos
--------------

- ``l10n_ar.fiscal.ws``: cada servicio, con su URL de producción y de homologación.
- ``l10n_ar.fiscal.ws.mapping`` y ``l10n_ar.fiscal.ws.mapping.line``: el método a
  llamar de cada servicio y cómo se arma su payload, incluidas estructuras
  anidadas, condiciones y formatos.
- ``l10n_ar.fiscal.ws.connection``: ticket de acceso vigente por servicio y compañía.
- ``l10n_ar.fiscal.certificate`` y ``l10n_ar.fiscal.certificate.alias``.

Modelos heredados
-----------------

- ``account.move``: datos de la autorización (modo, código, vencimiento, resultado,
  mensaje y XML), período asociado, datos de FCE MiPyME, código QR, numeración
  contra el servicio y los providers que alimentan el mapeo.
- ``account.journal``: servicio fiscal del diario y consultas de disponibilidad,
  puntos de venta y tipos de documento.
- ``res.company``, ``res.config.settings``: entorno, certificados y política de
  cancelación en moneda extranjera.
- ``res.partner``: consulta al padrón.
- ``product.template``: código NCM, que pide el bono fiscal electrónico.

Wizards
-------

- ``l10n_ar.fiscal.certificate.upload.wizard``: carga del certificado firmado.
- ``l10n_ar.fiscal.ws.recover`` y ``l10n_ar.fiscal.ws.recover.line``: recuperación
  de los comprobantes que el organismo autorizó y Odoo no llegó a registrar.
- ``res.partner.update.from.padron.wizard``: muestra los cambios que propone el
  padrón antes de aplicarlos.

Vistas y datos
--------------

- Formularios de servicio, certificado, alias y ticket de acceso, con su menú
  "Web services".
- Botones en el diario, en la factura y en el contacto.
- Herencia del comprobante impreso de ``l10n_ar`` para el QR y el CAE.
- Datos: servicios con sus URLs, mapeos y líneas de mapeo, y la acción de consulta
  de constancia de inscripción.

Uso
===

#. Cargar el certificado: menú Web services, crear un alias, pedir el certificado,
   subirlo a ARCA y cargar el firmado con el asistente.
#. Configurar el diario de ventas con un sistema de punto de venta por web service
   y su número de punto de venta. Probar el servicio con el botón del diario.
#. Confirmar una factura: el módulo pide el número al servicio, arma el pedido con
   el mapeo, y si ARCA la autoriza guarda el código y su vencimiento. Si la rechaza,
   la factura vuelve a borrador con el motivo.
#. En una factura en moneda extranjera, el botón "Consultar cotización" trae la del
   servicio y la aplica.
#. Para una nota de crédito o de débito sin comprobante asociado, cargar el período
   asociado en la pestaña ARCA.
#. Si el organismo autorizó comprobantes y la respuesta no llegó, el botón
   "Recuperar comprobantes" del diario abre el asistente: elegí el tipo de
   comprobante y el rango, traé lo que tiene el organismo y revisá la propuesta de
   cada uno.

Recuperación de comprobantes
============================

Pedir la autorización de a lotes trajo un riesgo nuevo: si el organismo registra el
rango y la respuesta no llega, lo que se pierde es un lote entero y no un
comprobante. El asistente del diario lo recupera.

Por cada número del rango le pregunta al servicio (``FECompConsultar``). Con lo que
contesta busca el contacto por su identificación —un consumidor final anónimo va al
contacto que crea la localización— y un borrador del mismo diario, tipo de
comprobante, contacto e importe total. Si lo encuentra propone asignarlo: le escribe
el número y la autorización y lo valida, sin volver a pedirle nada al organismo. Si
no lo encuentra propone crearlo, con una línea por alícuota de IVA informada más el
no gravado y el exento, sobre la cuenta contable que se elija. Tildando
"Neutralizar" emite además el comprobante que lo deja en cero: una nota de crédito
si lo recuperado es una factura, y una nota de débito si es una nota de crédito.
Ese sí se valida por el circuito de siempre, que le pide su propia autorización.

Un comprobante creado nunca queda con un total distinto al que informó el organismo:
si no coincide, el asistente corta y no lo registra.

Limitaciones conocidas
----------------------

- Solo WSFE. El servicio de exportación y el de bono fiscal autorizan un
  comprobante por pedido, así que ahí una respuesta perdida cuesta uno.
- Un comprobante con percepciones u otros tributos, o en moneda extranjera, se puede
  asignar a un borrador pero no crear: el asistente lo deja marcado y con el motivo.
- Los comprobantes se recuperan de a uno, en orden, y cada uno queda registrado
  aunque falle el siguiente. Volver a abrir el asistente sobre el mismo rango
  muestra los ya recuperados como "ya está en Odoo".

Arquitectura
============

El pedido de autorización no se arma en código: ``l10n_ar.fiscal.ws.mapping`` define
el método del servicio y sus líneas describen cada campo del payload —de dónde sale
el valor (un campo de Odoo, un valor fijo, un parámetro de la llamada o un provider),
cómo se formatea y bajo qué condición viaja—. Los providers son métodos
``_l10n_ar_fiscal_provider_*`` de ``account.move`` para lo que no se puede expresar
en datos: importes por tipo de impuesto, ítems de las líneas, comprobantes asociados.

La respuesta se lee con el mismo mecanismo, de modo que cada servicio declara dónde
viene el código de autorización sin tocar el código común.

Las llamadas pasan por un transporte propio que guarda el XML enviado y el recibido,
y por un ticket de acceso que se pide al WSAA y se reutiliza hasta que vence.

Dependencias
============

- ``l10n_ar``
- ``account_debit_note``

Autor
=====

ADHOC SA, Moldeo Interactive, Odoo Community Association (OCA)

Licencia
========

AGPL-3
