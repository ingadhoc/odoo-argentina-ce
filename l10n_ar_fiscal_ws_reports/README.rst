========================================
Reportes fiscales Argentina (CE)
========================================

Libro de IVA de ventas y compras, sus archivos de intercambio para ARCA y el
análisis de IVA.

Características
===============

- Libro de IVA de ventas y de compras por período y diarios, en planilla de cálculo,
  con su ciclo de borrador, presentado y cancelado, historial y espacio para adjuntar
  el libro tal como se presentó.
- Archivos de intercambio del régimen de información de compras y ventas: uno de
  comprobantes, uno de alícuotas y, en compras, uno de importaciones de bienes.
  Salen en texto de ancho fijo, con la codificación que espera el organismo.
- Prorrateo del crédito fiscal, global o por comprobante.
- Análisis de IVA: un cubo con una línea por apunte alcanzado por IVA, con las bases
  y los impuestos abiertos por alícuota (2,5 %, 5 %, 10,5 %, 21 % y 27 %),
  percepciones de IVA, no gravado y exento.

Detalles Técnicos
=================

Modelos nuevos
--------------

- ``account.vat.ledger``: el libro de un período, con los diarios, el estado, los
  textos de los tres archivos y su versión descargable.
- ``account.ar.vat.line``: vista SQL de solo lectura que convierte los apuntes
  contables en columnas por alícuota.
- ``report.account_vat_ledger_xlsx``: la planilla del libro.

Vistas incluidas
----------------

- Formulario y lista del libro, con menús de ventas y de compras bajo los informes
  argentinos.
- Lista, tabla dinámica y buscador del análisis de IVA.
- Regla de registro por compañía sobre el libro.

Uso
===

#. Entrar a Contabilidad, Informes, y elegir el libro de ventas o el de compras.
#. Crear uno indicando el período y los diarios; el libro junta los comprobantes
   publicados de ese rango.
#. Imprimir la planilla con el botón correspondiente.
#. Para el régimen de información, generar los textos y descargar los archivos desde
   la pestaña de archivos.
#. Presentar el libro deja el registro cerrado; se puede volver a borrador.

Arquitectura
============

Los reportes no leen las facturas directamente: leen ``account.ar.vat.line``, una
vista SQL que traduce los apuntes contables a columnas por alícuota. Así, un cambio
en cómo Odoo guarda los impuestos se absorbe en la vista y no en cada reporte.

Los archivos de intercambio se arman con anchos fijos por campo y se guardan como
texto en el libro antes de ofrecerse como archivo, de modo que se puede revisar lo
que se va a presentar.

Dependencias
============

- ``l10n_ar_fiscal_ws``
- ``report_xlsx``

Autor
=====

ADHOC SA, Moldeo Interactive, Odoo Community Association (OCA)

Licencia
========

AGPL-3
