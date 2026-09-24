==========================================
Pagos pro con web services fiscales
==========================================

Período asociado y comprobante de origen en las notas de crédito y débito que nacen
de un pago.

Características
===============

- Agrega al asistente de nota de crédito y débito de ``account_payment_pro`` el
  comprobante de origen y el período asociado, y los copia a la nota que crea.
- El comprobante de origen se guarda en el campo que corresponde según el tipo:
  la factura revertida en una nota de crédito, el comprobante de origen en una de
  débito.
- En la nota de débito automática del recargo financiero, que no tiene comprobante
  asociado, completa el período asociado —el mes anterior a la fecha del recibo—,
  que es lo que ARCA pide en ese caso para autorizarla.

Detalles Técnicos
=================

Modelos heredados
-----------------

- ``account.payment.invoice.wizard``: campos ``l10n_ar_fiscal_period_from``,
  ``l10n_ar_fiscal_period_to``, ``origin_invoice_id`` y ``commercial_partner_id``
  (relacionado, para acotar el dominio), y override de ``get_invoice_vals()``.

Vistas incluidas
----------------

- Herencia del formulario del asistente de ``account_payment_pro``, con el
  comprobante de origen filtrado por el cliente del pago y comprobantes publicados.

Uso
===

#. Desde un pago, crear una nota de crédito o de débito con el asistente.
#. Elegir el comprobante de origen si la nota se refiere a uno, o cargar el período
   asociado si no hay comprobante al que referirse.
#. Confirmar: la nota queda con esos datos y los informa al autorizarse.

Arquitectura
============

El módulo es solo el puente entre el asistente y la factura: no arma nada del pedido
a ARCA, que sale del mapeo de ``l10n_ar_fiscal_ws``. Se instala solo cuando están
los dos módulos.

Dependencias
============

- ``account_payment_pro``
- ``l10n_ar_fiscal_ws``

Autor
=====

ADHOC SA

Licencia
========

AGPL-3
