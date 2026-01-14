# 🚨 URGENT: AFIP Error 10002 - Next Steps

## Current Status

**Problem Confirmed**: The `FeDetReq` array is arriving EMPTY at AFIP despite having 1 element in Python.

### Evidence from Logs

```
✅ Python Side: "Cantidad items en FeDetReq: 1"
❌ AFIP Side:   "Informado: 1, Enviado: 0"
```

## What We Just Fixed

### 1. XML Logging Fixed ✅

**Files Changed**:
- `l10n_ar_afipws_fe/lib/wsfev1_client.py`
- `l10n_ar_afipws_fe/lib/wsfev1_adapter.py`

**Change**:
```python
# OLD (broken):
xml = self.history.last_sent['envelope'].decode()  # ❌ _Element has no decode()

# NEW (fixed):
from lxml import etree
xml = etree.tostring(self.history.last_sent['envelope'], encoding='unicode', pretty_print=True)  # ✅
```

**Now Changed to INFO level** so you'll see the XML in normal logs (not just DEBUG)

---

## 🔥 IMMEDIATE NEXT STEP

### 1. Restart Odoo

```bash
# However you restart Odoo, for example:
sudo systemctl restart odoo
# or
docker restart odoo_container
# or kill the process and restart
```

### 2. Upgrade Module

```bash
# From Odoo web interface:
Apps > l10n_ar_afipws_fe > Upgrade

# OR from command line:
./odoo-bin -u l10n_ar_afipws_fe -d l10n_ar --stop-after-init
```

### 3. Try Invoice Validation AGAIN

Create the same invoice and click "Validate"

### 4. Check Logs for THIS

Look for this new log line:

```
INFO ... XML Request enviado a AFIP:
<soap-env:Envelope ...>
  ...
  <ns0:FeDetReq>
    <!-- ⚠️ CRITICAL: CHECK IF THIS IS EMPTY! -->
  </ns0:FeDetReq>
  ...
</soap-env:Envelope>
```

**Share the ENTIRE XML envelope** with me.

---

## 🔍 What to Look For in the XML

### Scenario A: `<ns0:FeDetReq>` is EMPTY

```xml
<ns0:FeDetReq/>  <!-- ❌ EMPTY! -->
```

**This means**: zeep is not serializing the array properly

**Fix**: We need to use explicit array wrapper or zeep settings

### Scenario B: `<ns0:FeDetReq>` has content

```xml
<ns0:FeDetReq>
  <ns0:FECAEDetRequest>  <!-- ✅ Has content! -->
    <ns0:CbteDesde>1</ns0:CbteDesde>
    ...
  </ns0:FECAEDetRequest>
</ns0:FeDetReq>
```

**This means**: The XML is correct, problem is elsewhere (maybe namespace issue)

**Fix**: Check XML namespaces and AFIP WSDL version

---

## 📋 Information to Collect

When you run the test, copy/paste these from the logs:

1. **Line starting with**: `XML Request enviado a AFIP:`
   Copy the **ENTIRE XML** (all lines until the closing `</soap-env:Envelope>`)

2. **Line**: `FECAERequest completo - Cantidad items en FeDetReq:`
   Verify it still says `1`

3. **AFIP Error**: The full error from AFIP

---

## 🎯 Hypothesis & Likely Fix

Based on zeep/SOAP experience, I suspect **one of these**:

### Most Likely: zeep Array Serialization Issue

zeep might be serializing the array incorrectly because:
- It treats empty/None fields specially
- AFIP expects a specific XML structure

**Potential Fix** (we'll apply after seeing XML):

```python
# In wsfev1_client.py, line ~199

# Current:
fe_cae_req = factory.FECAERequest(
    FeCabReq=fe_cab_req,
    FeDetReq=[fe_det_req],  # ❌ Might be the issue
)

# Try Option 1: Explicit type
array_wrapper = factory.ArrayOfFECAEDetRequest([fe_det_req])
fe_cae_req = factory.FECAERequest(
    FeCabReq=fe_cab_req,
    FeDetReq=array_wrapper,
)

# OR Try Option 2: Direct assignment
fe_cae_req = factory.FECAERequest()
fe_cae_req.FeCabReq = fe_cab_req
fe_cae_req.FeDetReq = [fe_det_req]  # Assign after creation
```

### Less Likely: AFIP WSDL Changed

AFIP sometimes updates WSDLs. We're using:
```python
WSDL_HOMO = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"
```

**Check**: Download the WSDL and verify structure hasn't changed

---

## 🛠️ Quick Test (Alternative)

If you can't wait for full Odoo restart, try this standalone test:

```bash
cd /path/to/odoo-argentina-ce/l10n_ar_afipws_fe

python3 << 'EOF'
import logging
logging.basicConfig(level=logging.INFO)

from lib.wsfev1_client import WSFEv1Client

# Your actual credentials
client = WSFEv1Client(
    cuit='20168259485',  # From your log
    token='YOUR_TOKEN',
    sign='YOUR_SIGN',
    environment='homologation'
)

# Exact data from your log
factura_data = {
    'PtoVta': 1,
    'CbteTipo': 6,
    'Concepto': 2,
    'DocTipo': 99,
    'DocNro': 0,
    'CbteDesde': 1,
    'CbteHasta': 1,
    'CbteFch': '20260112',
    'ImpTotal': 242.0,
    'ImpTotConc': 0.0,
    'ImpNeto': 200.0,
    'ImpOpEx': 0.0,
    'ImpTrib': 0.0,
    'ImpIVA': 42.0,
    'MonId': 'PES',
    'MonCotiz': 1.0,
    'FchVtoPago': '20260228',
    'Iva': [{'Id': 5, 'BaseImp': 200.0, 'Importe': 42.0}]
}

result = client.solicitar_cae(factura_data)
print(f"\nResultado: {result}")

# The XML will be printed automatically in the logs
EOF
```

---

## 📞 What to Report Back

After running the test with updated code, share:

1. ✅ **The complete XML request** (from logs)
2. ✅ Confirmation that "Cantidad items en FeDetReq" = 1
3. ✅ AFIP's error message (if still 10002)
4. ✅ Any NEW log lines or warnings

---

## 💡 Why This Will Work

Once we see the actual SOAP XML:
- If `<ns0:FeDetReq>` is empty → Fix array serialization
- If `<ns0:FeDetReq>` has data → Check namespace/structure
- Either way, we'll have the smoking gun

The fix will take **5 minutes** once we see the XML.

---

**Status**: XML logging fixed, ready for retest
**Next Action**: Restart Odoo, upgrade module, validate invoice, share XML
**ETA to Fix**: ~5 minutes after seeing XML envelope

🚀 **Let's get that XML!**
