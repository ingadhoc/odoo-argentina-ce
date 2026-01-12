# WSFEv1 zeep Migration - Test Plan

## Migration Status: ✅ READY FOR TESTING

### Date: 2026-01-12
### Branch: `19.0_tmp_iniciozeep`

---

## Overview

This document outlines the testing plan for the migration from `pyafipws` to `zeep` for the WSFEv1 (Web Service de Facturación Electrónica) integration with AFIP.

### What Changed

- **Old**: `pyafipws.wsfev1.WSFEv1` (unmaintained library)
- **New**: `zeep` (modern, maintained SOAP client)
- **Strategy**: Adapter pattern for backward compatibility

### Files Modified/Created

1. **`l10n_ar_afipws_fe/lib/wsfev1_client.py`** - New zeep-based client
2. **`l10n_ar_afipws_fe/lib/wsfev1_adapter.py`** - Compatibility adapter
3. **`l10n_ar_afipws_fe/models/afipws_connection.py`** - Updated connect() method
4. **`AGENTS.md`** - Added critical inheritance documentation

---

## Pre-Testing Checklist

### ✅ Code Quality Checks

- [x] Python syntax validation passed
- [x] All nested SOAP arrays use zeep factory
- [x] Field references use correct base module names
- [x] Error enrichment dictionary added
- [x] All pyafipws methods implemented in adapter

### ✅ Dependencies

- [x] `zeep` added to `external_dependencies` in `__manifest__.py`
- [x] `lxml` added to `external_dependencies` in `__manifest__.py`

### Installation Commands

```bash
# Install zeep and dependencies
pip3 install zeep lxml requests

# Verify installation
python3 -c "import zeep; print(f'zeep version: {zeep.__version__}')"
```

---

## Testing Environments

### AFIP Homologation Environment

**IMPORTANT**: Always test in homologation first!

- WSDL: `https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL`
- WSAA (Auth): `https://wsaahomo.afip.gov.ar/ws/services/LoginCms`
- Test CUIT: 20111111112 (or your registered test CUIT)

### AFIP Production Environment

**WARNING**: Only use after successful homologation testing!

- WSDL: `https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL`
- WSAA (Auth): `https://wsaa.afip.gov.ar/ws/services/LoginCms`

---

## Test Cases

### Test 1: Module Installation/Upgrade

**Objective**: Verify module loads without errors

```bash
# From Odoo CLI
./odoo-bin -u l10n_ar_afipws_fe -d your_database --stop-after-init

# Or from UI
# Apps > l10n_ar_afipws_fe > Upgrade
```

**Expected Result**:
- No import errors
- Module status: "Installed"
- No error in logs

**Verify**:
```bash
grep -i "wsfev1\|zeep\|error" /var/log/odoo/odoo.log | tail -50
```

---

### Test 2: Connection Test (Dummy)

**Objective**: Verify basic connectivity to AFIP

**Steps**:
1. Go to: Accounting > Configuration > AFIP > Connections
2. Find or create a connection with:
   - Type: Homologation
   - AFIP WS: WSFEv1
   - Valid token/sign (from WSAA)
3. Click "Test Connection" (or equivalent button)

**Expected Result**:
- No errors
- Log shows: "WSFEv1 conectado con CUIT..."
- AppServer, DbServer, AuthServer status: "OK"

**Check Logs**:
```bash
tail -f /var/log/odoo/odoo.log | grep -i "wsfe\|dummy"
```

---

### Test 3: Get Last Invoice Number

**Objective**: Query último comprobante autorizado

**Steps**:
1. Navigate to journal configuration
2. Select a journal with WSFEv1 configured
3. Click "Get Last Invoice Number" or equivalent

**Expected Result**:
- Returns a number (0 if no previous invoices)
- No exceptions

**Debug Command** (in Odoo shell):
```python
journal = env['account.journal'].search([('afip_ws', '=', 'wsfe')], limit=1)
doc_type = env['l10n_latam.document.type'].search([('code', '=', '1')], limit=1)
last_number = journal.get_pyafipws_last_invoice(doc_type)
print(f"Last invoice number: {last_number}")
```

---

### Test 4: Get AFIP Parameters

**Objective**: Verify parameter query methods

**Test in Odoo shell**:
```python
connection = env['afipws.connection'].search([('afip_ws', '=', 'wsfe')], limit=1)
ws = connection.connect()

# Test parameter methods
print("Testing Dummy...")
result = ws.Dummy()
print(f"Dummy OK: {result}")

print("\nTesting ParamGetPtosVenta...")
puntos = ws.ParamGetPtosVenta(sep=" ")
print(f"Puntos de venta: {puntos}")

print("\nTesting ParamGetTiposCbte...")
tipos = ws.ParamGetTiposCbte(sep=",")
print(f"Tipos cbte: {tipos[:100]}...")  # First 100 chars

print("\nTesting CompUltimoAutorizado...")
ultimo = ws.CompUltimoAutorizado(1, 1)  # Tipo 1, PtoVta 1
print(f"Último autorizado: {ultimo}")
```

**Expected Result**:
- All methods execute without errors
- Returns valid data (not empty strings unless no data exists)

---

### Test 5: Create and Validate Invoice (CRITICAL)

**Objective**: Full invoice validation flow with CAE request

**Steps**:
1. Go to: Accounting > Customers > Invoices
2. Create new invoice:
   - Customer: Valid customer with CUIT
   - Journal: Configured with WSFEv1
   - Document Type: Factura A or B (code 1 or 6)
   - Invoice lines: At least one line with VAT
   - Amount: Small amount for testing (e.g., 1000 ARS)
3. Click "Validate"

**Expected Behavior**:

**Success Case**:
- Invoice state changes to "Posted"
- `l10n_ar_afip_auth_code` field populated with CAE
- `l10n_ar_afip_auth_code_due` field populated with CAE expiration
- No error messages

**Rejection Case** (if data invalid):
- Error message shows AFIP rejection reason
- Error message includes enriched description (from AFIP_ERROR_MESSAGES)
- Invoice remains in draft state

**Check Logs**:
```bash
tail -f /var/log/odoo/odoo.log | grep -iE "cae|afip|wsfe|error"
```

**Look for**:
```
INFO ... WSFEv1 conectado con CUIT "..."
INFO ... Solicitando CAE - PtoVta: X, CbteTipo: Y, Nro: Z
INFO ... CAE obtenido exitosamente: XXXXX..., vencimiento: YYYYMMDD
```

---

### Test 6: Invoice with VAT Items

**Objective**: Test IVA aliquots serialization

**Create invoice with**:
- Multiple lines with different VAT rates (0%, 10.5%, 21%)
- Ensure `_get_vat()` returns multiple IVA items

**Expected**:
- All IVA aliquots properly sent to AFIP
- CAE obtained
- No "ArrayOfAlicIva" errors

---

### Test 7: Credit/Debit Note with Associated Invoice

**Objective**: Test comprobantes asociados

**Steps**:
1. Create and validate a regular invoice
2. Create a credit note for that invoice
3. Validate credit note

**Expected**:
- Credit note has `CbteAsoc` field populated
- CAE obtained for credit note
- AFIP links credit note to original invoice

---

### Test 8: Invoice with Tributes

**Objective**: Test perceptions/retentions

**Create invoice with**:
- Taxes with `l10n_ar_tribute_afip_code` set (e.g., IIBB, perception)

**Expected**:
- Tributes properly serialized in `Tributos` array
- CAE obtained
- No "ArrayOfTributo" errors

---

### Test 9: FCE (Factura de Crédito Electrónica)

**Objective**: Test MiPyME FCE functionality

**Create invoice with**:
- Document type: FCE (codes 201-213)
- Partner bank account (CBU) configured
- `afip_fce_es_anulacion` = False

**Expected**:
- Optional field 2101 (CBU) added
- Optional field 27 (transmission type) added if configured
- CAE obtained

---

### Test 10: Error Handling

**Objective**: Verify error messages are user-friendly

**Test Cases**:

**A) Expired Token**:
1. Use connection with expired token
2. Try to validate invoice

**Expected**: Error message includes "Token expirado - Debe solicitar un nuevo token"

**B) Invalid CUIT**:
1. Set invalid customer CUIT
2. Try to validate

**Expected**: Error message includes "CUIT del cliente inválido"

**C) Wrong Invoice Number Sequence**:
1. Manually change invoice number to skip sequence
2. Try to validate

**Expected**: Error message includes "debe ser consecutivo al último autorizado"

---

## Performance Testing

### Response Time Benchmarks

**Baseline** (measure these times):

```python
import time

connection = env['afipws.connection'].search([('afip_ws', '=', 'wsfe')], limit=1)

# Test 1: Connection time
start = time.time()
ws = connection.connect()
print(f"Connection time: {time.time() - start:.2f}s")

# Test 2: Dummy call
start = time.time()
ws.Dummy()
print(f"Dummy time: {time.time() - start:.2f}s")

# Test 3: CAE request (on a draft invoice)
invoice = env['account.move'].search([('state', '=', 'draft')], limit=1)
start = time.time()
invoice.action_post()  # This calls AFIP
print(f"CAE request time: {time.time() - start:.2f}s")
```

**Expected Times** (approximate):
- Connection: < 2 seconds
- Dummy: < 3 seconds
- CAE request: 3-10 seconds (depends on AFIP)

---

## Rollback Plan

If critical issues found:

### Option 1: Quick Fix
If zeep-specific issue, fix in `wsfev1_client.py` or `wsfev1_adapter.py`

### Option 2: Temporary Pyafipws Fallback

1. Edit `l10n_ar_afipws_fe/models/afipws_connection.py`:

```python
def _get_ws(self, afip_ws):
    ws = super(AfipwsConnection, self)._get_ws(afip_ws)
    if afip_ws == "wsfe":
        # FALLBACK: Use old pyafipws temporarily
        try:
            from pyafipws.wsfev1 import WSFEv1
            ws = WSFEv1()
            _logger.warning("Using pyafipws fallback for WSFEv1")
        except ImportError:
            raise UserError(_("pyafipws not installed"))
    return ws
```

2. Restart Odoo
3. Upgrade module

---

## Known Issues / Limitations

### 1. XML Capture Not Implemented

**Issue**: `XmlRequest` and `XmlResponse` attributes show placeholder text

**Impact**: Debugging SOAP requests/responses requires checking zeep logs

**Workaround**: Enable zeep debugging:
```python
import logging
logging.getLogger('zeep').setLevel(logging.DEBUG)
```

**Future**: Implement zeep plugin to capture raw XML

### 2. Type-Checking Warnings

**Issue**: Editor shows warnings about dict key types

**Impact**: None - Python is dynamically typed, warnings are from type checker

**Action**: Ignore these warnings

### 3. WSFEX, WSMTXCA, WSCDC, WSBFE Not Migrated

**Issue**: Only WSFEv1 migrated to zeep so far

**Impact**: These services still require pyafipws

**Future**: Migrate other services in subsequent phases

---

## Success Criteria

Migration considered successful if:

- [ ] All 10 test cases pass
- [ ] No regression in existing functionality
- [ ] CAE obtained successfully in homologation
- [ ] Error messages are clear and helpful
- [ ] Performance is equal or better than pyafipws
- [ ] No critical bugs found

---

## Post-Testing Actions

### If All Tests Pass:

1. **Tag the commit**:
   ```bash
   git tag -a v19.0.1.0.0-zeep-migration -m "WSFEv1 migrated to zeep"
   git push origin v19.0.1.0.0-zeep-migration
   ```

2. **Merge to main branch**:
   ```bash
   git checkout 19.0
   git merge 19.0_tmp_iniciozeep
   git push origin 19.0
   ```

3. **Production deployment**:
   - Schedule during low-traffic window
   - Have rollback plan ready
   - Monitor logs for first 100 invoices

4. **Documentation**:
   - Update CHANGELOG.md
   - Update README.md with zeep installation instructions
   - Document any configuration changes

### If Tests Fail:

1. Document all failures in GitHub issue
2. Fix critical issues
3. Re-run full test plan
4. Consider rollback if unfixable

---

## Contact / Support

**Issues**: Report on GitHub repository issue tracker

**Migration Lead**: See git commit history

**AFIP Documentation**:
- [AFIP Web Services Manual](https://www.afip.gob.ar/ws/documentacion/)
- [WSFEv1 Specification](https://www.afip.gob.ar/fe/documentos/)

---

## Appendix: Debugging Commands

### Enable Detailed zeep Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('zeep.wsdl').setLevel(logging.DEBUG)
logging.getLogger('zeep.xsd').setLevel(logging.DEBUG)
logging.getLogger('zeep.transport').setLevel(logging.DEBUG)
```

### Inspect WSDL Types

```python
from zeep import Client
client = Client('https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL')

# List all types
for type_name in client.wsdl.types.get_type_names():
    print(type_name)

# Inspect specific type
fecae_type = client.wsdl.types.get_type('{http://ar.gov.afip.dif.FEV1/}FECAERequest')
print(fecae_type.signature())
```

### Manual CAE Request (Outside Odoo)

```python
from l10n_ar_afipws_fe.lib.wsfev1_client import WSFEv1Client

# Initialize
client = WSFEv1Client(
    cuit='20111111112',
    token='YOUR_TOKEN',
    sign='YOUR_SIGN',
    environment='homologation'
)

# Test dummy
result = client.dummy()
print(f"Dummy result: {result}")

# Request CAE
factura_data = {
    'PtoVta': 1,
    'CbteTipo': 6,  # Factura B
    'Concepto': 1,  # Productos
    'DocTipo': 99,  # Consumidor final
    'DocNro': 0,
    'CbteDesde': 1,
    'CbteHasta': 1,
    'CbteFch': '20260112',
    'ImpTotal': 121.00,
    'ImpTotConc': 0,
    'ImpNeto': 100.00,
    'ImpOpEx': 0,
    'ImpTrib': 0,
    'ImpIVA': 21.00,
    'MonId': 'PES',
    'MonCotiz': 1.00,
    'Iva': [
        {'Id': 5, 'BaseImp': 100.00, 'Importe': 21.00}  # IVA 21%
    ]
}

result = client.solicitar_cae(factura_data)
print(f"CAE result: {result}")
```

---

**Last Updated**: 2026-01-12
**Version**: 1.0
**Status**: Ready for Testing
