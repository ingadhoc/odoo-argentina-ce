# 🐛 AFIP Error 10002: CantReg Mismatch - Debug Guide

## Error Encountered

```
[10002] Campo CantReg debe ser igual a lo informado en detalle.
Informado: 1, Enviado: 0
```

**Translation**: "CantReg field must equal what's informed in detail. Declared: 1, Sent: 0"

## Root Cause Analysis

### What This Error Means

AFIP is saying:
- **Header (FeCabReq.CantReg)**: You told us "1 invoice"
- **Detail (FeDetReq array)**: But you sent 0 invoices!

This is a **mismatch** between what we declared and what was actually sent in the SOAP envelope.

### What We Verified ✅

1. **zeep object creation is CORRECT** ✅
   - Ran test script showing `FECAERequest.FeDetReq` has 1 element
   - The Python list `[fe_det_req]` is properly populated
   - Serialization shows the data is present

2. **The bug is NOT in Python code** ✅
   - The `fe_cae_req` object has `FeDetReq` with length = 1
   - All fields are properly set

### Where the Bug Likely Is

The issue is probably in **how zeep serializes the XML** when sending to AFIP. Possible causes:

1. **XML namespace issue**: Array element might be in wrong namespace
2. **SOAP serialization**: zeep might be omitting empty/None fields incorrectly
3. **Array wrapper**: AFIP might expect a specific XML structure

---

## 🔧 Changes Made to Debug

### 1. Added HistoryPlugin for XML Capture

**File**: `l10n_ar_afipws_fe/lib/wsfev1_client.py`

**Changes**:
- Added `HistoryPlugin` import
- Added `self.history = HistoryPlugin()` in `__init__`
- Added XML logging in `solicitar_cae()`:
  ```python
  if self.history.last_sent:
      _logger.debug(f"XML Request:\n{self.history.last_sent['envelope'].decode()}")
  ```

**Purpose**: Capture the actual SOAP XML being sent to AFIP

### 2. Enhanced Debugging Logs

**File**: `l10n_ar_afipws_fe/lib/wsfev1_client.py`

**Added**:
```python
_logger.info(f"FECAEDetRequest creado - CbteDesde: {fe_det_req.CbteDesde}, ImpTotal: {fe_det_req.ImpTotal}")
_logger.info(f"FECAECabRequest creado - CantReg: {fe_cab_req.CantReg}, PtoVta: {fe_cab_req.PtoVta}")
_logger.info(f"FECAERequest completo - Cantidad items en FeDetReq: {len(fe_cae_req.FeDetReq)}")

# Critical check before sending
if not fe_cae_req.FeDetReq or len(fe_cae_req.FeDetReq) == 0:
    raise ValueError("FeDetReq está vacío!")
```

### 3. XML Capture in Adapter

**File**: `l10n_ar_afipws_fe/lib/wsfev1_adapter.py`

**Changes**:
- `XmlRequest` and `XmlResponse` now capture real XML from `HistoryPlugin`
- No longer placeholder text

---

## 🔍 Next Steps to Debug

### Step 1: Enable Debug Logging

Add this to your Odoo config or run in shell:

```python
import logging
logging.getLogger('l10n_ar_afipws_fe.lib.wsfev1_client').setLevel(logging.DEBUG)
logging.getLogger('zeep.transports').setLevel(logging.DEBUG)
```

### Step 2: Try Invoice Validation Again

1. Create a simple invoice
2. Click "Validate"
3. Check logs for:
   - "FECAEDetRequest creado" - Should show `CbteDesde: 1` and `ImpTotal: XXX`
   - "FECAERequest completo - Cantidad items" - Should show `1`
   - "XML Request enviado" - The actual SOAP XML

### Step 3: Inspect the XML Request

Look for this section in the SOAP envelope:

```xml
<ns0:FeCAEReq>
  <ns0:FeCabReq>
    <ns0:CantReg>1</ns0:CantReg>
    ...
  </ns0:FeCabReq>
  <ns0:FeDetReq>
    <!-- THIS SHOULD HAVE 1 ELEMENT! -->
    <ns0:FECAEDetRequest>
      <ns0:CbteDesde>1</ns0:CbteDesde>
      ...
    </ns0:FECAEDetRequest>
  </ns0:FeDetReq>
</ns0:FeCAEReq>
```

**If `<ns0:FeDetReq>` is EMPTY or missing the `<ns0:FECAEDetRequest>` element**, that's the smoking gun!

---

## 🛠️ Potential Fixes

### Fix Option 1: Check for None Fields

AFIP might be rejecting the request because zeep is sending too many `None` fields. Try:

```python
# In wsfev1_client.py, before creating FECAEDetRequest
# Remove None values from fe_det_req_data
fe_det_req_data = {k: v for k, v in fe_det_req_data.items() if v is not None}
```

### Fix Option 2: Explicit Array Creation

Some SOAP servers are picky about arrays. Try:

```python
# Instead of:
fe_cae_req = factory.FECAERequest(
    FeCabReq=fe_cab_req,
    FeDetReq=[fe_det_req],
)

# Try:
array_of_det = factory.ArrayOfFECAEDetRequest([fe_det_req])
fe_cae_req = factory.FECAERequest(
    FeCabReq=fe_cab_req,
    FeDetReq=array_of_det,
)
```

### Fix Option 3: Check WSDL Version

Verify you're using the correct WSDL:
- Homologation: `https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL`
- Production: `https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL`

Sometimes AFIP updates WSDLs and the structure changes slightly.

### Fix Option 4: zeep Settings

Try creating the client with strict mode off:

```python
from zeep import Settings

settings = Settings(strict=False, xml_huge_tree=True)
self.client = Client(self.wsdl_url, transport=transport, plugins=[self.history], settings=settings)
```

---

## 📋 Debug Checklist

When you run the next test, collect this information:

- [ ] Log line: "FECAEDetRequest creado" - what does it show?
- [ ] Log line: "FECAERequest completo - Cantidad items" - is it 1?
- [ ] Log line: "XML Request enviado" - copy the full SOAP envelope
- [ ] Does the XML have `<ns0:FeDetReq>` element?
- [ ] Does `<ns0:FeDetReq>` have a `<ns0:FECAEDetRequest>` child?
- [ ] What fields are inside the `<ns0:FECAEDetRequest>`?
- [ ] Are there any XML validation errors in zeep logs?

---

## 🎯 Quick Test Script

Run this standalone to see if the serialization works:

```bash
cd /Volumes/Disk\ 1Tb/DesarrollosODOO/odoo19Desarrollo/extra-addons/odoo-argentina-ce/l10n_ar_afipws_fe

python3 << 'PYTHON'
import logging
logging.basicConfig(level=logging.DEBUG)

from lib.wsfev1_client import WSFEv1Client

# Use your real credentials
client = WSFEv1Client(
    cuit='20111111112',  # Replace with your CUIT
    token='YOUR_TOKEN',   # Replace with your token
    sign='YOUR_SIGN',     # Replace with your sign
    environment='homologation'
)

# Test data
factura_data = {
    'PtoVta': 1,
    'CbteTipo': 6,
    'Concepto': 1,
    'DocTipo': 99,
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
    'Iva': [{'Id': 5, 'BaseImp': 100.00, 'Importe': 21.00}]
}

print("Solicitando CAE...")
result = client.solicitar_cae(factura_data)
print(f"\nResultado: {result}")

# Check history
if client.history.last_sent:
    xml_req = client.history.last_sent['envelope'].decode()
    print("\n" + "="*80)
    print("XML REQUEST SENT TO AFIP:")
    print("="*80)
    print(xml_req)
    print("="*80)

    # Check if FeDetReq is present
    if '<ns0:FeDetReq>' in xml_req:
        print("\n✅ FeDetReq found in XML")
        if '<ns0:FECAEDetRequest>' in xml_req:
            print("✅ FECAEDetRequest found inside FeDetReq")
        else:
            print("❌ FECAEDetRequest NOT FOUND inside FeDetReq!")
    else:
        print("\n❌ FeDetReq NOT FOUND in XML!")
PYTHON
```

---

## 📞 What to Report Back

After running the test, please share:

1. **All log output** (especially XML Request)
2. **AFIP's full error response** (not just the error code)
3. **Odoo version** you're using
4. **zeep version**: Run `python3 -c "import zeep; print(zeep.__version__)"`

With the XML request, I can pinpoint exactly what's wrong and provide the fix.

---

## 💡 Hypothesis

Based on common SOAP/zeep issues, I suspect:

**Most Likely**: zeep is serializing `FeDetReq` as an empty array because of how AFIP expects the XML namespace or structure. The fix will likely be one of:
- Using `ArrayOfFECAEDetRequest` explicitly
- Adjusting zeep settings
- Removing None fields before serialization

**Less Likely**: Authentication issue (the second error about CUIT might be AFIP's way of saying "request was invalid, I'm not even checking your CUIT")

---

**Status**: Debug instrumentation added, ready for testing
**Next Action**: Run invoice validation and capture XML request logs
**Files Modified**:
- `l10n_ar_afipws_fe/lib/wsfev1_client.py` (added HistoryPlugin)
- `l10n_ar_afipws_fe/lib/wsfev1_adapter.py` (added XML capture)
