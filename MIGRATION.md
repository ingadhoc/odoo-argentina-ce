# Migración a 19

El refactor de la facturación electrónica argentina cambió los nombres de los módulos,
y eso obliga a un paso a mano antes de actualizar. El resto lo hacen los scripts que
viven en cada módulo.

| En 18 | En 19 |
|---|---|
| `l10n_ar_afipws` + `l10n_ar_afipws_fe` | `l10n_ar_fiscal_ws` |
| `l10n_ar_reports` | `l10n_ar_fiscal_ws_reports` |
| `l10n_ar_pos_afipws_fe` | se da de baja (ya venía como no instalable) |

## Por qué hay un paso a mano

Odoo corre los scripts de migración de un módulo cuando lo ve instalado con una versión
anterior a la del manifiesto. Después del renombre, la base tiene `l10n_ar_afipws`, que
ya no existe en el repositorio, y `l10n_ar_fiscal_ws`, que no está instalado: sin el
renombre previo no hay módulo que dispare ningún script. Por eso el renombre va primero
y fuera de los módulos; de ahí en adelante todo es automático.

## 1. Renombrar los módulos, antes de actualizar

Sobre la base ya en 19 y **antes** del `-u`. La forma recomendada es `odoo shell`,
porque `openupgradelib` mueve también los identificadores externos y las dependencias:

```bash
odoo shell -c /etc/odoo/odoo.conf -d LA_BASE
```

```python
from openupgradelib import openupgrade

# la factura electrónica dejó de ser un módulo aparte: se fusiona en el base
openupgrade.update_module_names(
    env.cr, [("l10n_ar_afipws_fe", "l10n_ar_afipws")], merge_modules=True
)

# y los módulos toman su nombre nuevo
openupgrade.update_module_names(
    env.cr,
    [
        ("l10n_ar_afipws", "l10n_ar_fiscal_ws"),
        ("l10n_ar_reports", "l10n_ar_fiscal_ws_reports"),
    ],
)

# el módulo de punto de venta no se migra
pos = env["ir.module.module"].search([("name", "=", "l10n_ar_pos_afipws_fe")])
if pos.state == "installed":
    pos.button_immediate_uninstall()

env.cr.commit()
```

Si no hay manera de abrir un shell, el mínimo indispensable en SQL:

```sql
-- la fusión: primero los identificadores externos, después la fila del módulo
UPDATE ir_model_data SET module = 'l10n_ar_afipws' WHERE module = 'l10n_ar_afipws_fe';
DELETE FROM ir_module_module_dependency WHERE name = 'l10n_ar_afipws_fe';
DELETE FROM ir_module_module WHERE name = 'l10n_ar_afipws_fe';

-- los renombres
UPDATE ir_module_module SET name = 'l10n_ar_fiscal_ws' WHERE name = 'l10n_ar_afipws';
UPDATE ir_model_data SET module = 'l10n_ar_fiscal_ws' WHERE module = 'l10n_ar_afipws';
UPDATE ir_module_module_dependency SET name = 'l10n_ar_fiscal_ws' WHERE name = 'l10n_ar_afipws';

UPDATE ir_module_module SET name = 'l10n_ar_fiscal_ws_reports' WHERE name = 'l10n_ar_reports';
UPDATE ir_model_data SET module = 'l10n_ar_fiscal_ws_reports' WHERE module = 'l10n_ar_reports';
UPDATE ir_module_module_dependency SET name = 'l10n_ar_fiscal_ws_reports' WHERE name = 'l10n_ar_reports';
```

No toques `latest_version`: tiene que quedar en la versión vieja para que los scripts
corran.

## 2. Actualizar

```bash
odoo -c /etc/odoo/odoo.conf -d LA_BASE -u l10n_ar_fiscal_ws,l10n_ar_fiscal_ws_reports --stop-after-init
```

En el log tiene que aparecer `Running migration [>19.0.1.0.0] pre-migration`.

## 3. Qué hacen los scripts

`l10n_ar_fiscal_ws/migrations/19.0.1.0.0/pre-migration.py`

- Renombra los modelos del certificado y su alias, con sus tablas: la clave privada y el
  certificado firmado viajan con los datos.
- Renombra los campos de la factura y de la compañía al prefijo `l10n_ar_fiscal_`, así
  las facturas conservan su CAE, su vencimiento, su resultado y el XML intercambiado.
- Borra los tickets de acceso viejos: el servicio dejó de ser una selección para pasar a
  ser un registro, y los tickets duran doce horas, así que se piden de nuevo.

`l10n_ar_fiscal_ws/migrations/19.0.1.0.0/post-migration.py`

- Pasa la cola de facturas marcadas para validarse en segundo plano al campo de
  `account_background_post`, que es quien hace eso ahora. Si ese módulo no está
  instalado y quedaban facturas encoladas, lo avisa en el log.

`l10n_ar_fiscal_ws_reports` no necesita script: el libro de IVA y el análisis de IVA
conservan sus modelos y sus campos, y la vista SQL se rehace sola al instalar.

## Correr los scripts a mano

Si preferís no depender del hook de migración —para probar en una copia, o para
reintentar un paso— los dos scripts se pueden ejecutar desde `odoo shell`:

```python
import importlib.util

def correr(path):
    spec = importlib.util.spec_from_file_location("migracion", path)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    modulo.migrate(env.cr, "18.0.1.0.0")

base = "/opt/odoo/custom/repositories/odoo-argentina-ce/l10n_ar_fiscal_ws/migrations/19.0.1.0.0"
correr(f"{base}/pre-migration.py")
correr(f"{base}/post-migration.py")
env.cr.commit()
```

Son idempotentes en lo que importa: si el campo ya tiene el nombre nuevo o la tabla ya
no está, el paso no hace nada.

## 4. Verificar

```sql
-- las facturas conservan su autorización
SELECT count(*) FROM account_move WHERE l10n_ar_fiscal_auth_code IS NOT NULL;

-- los certificados siguen ahí
SELECT count(*) FROM l10n_ar_fiscal_certificate;
SELECT count(*) FROM l10n_ar_fiscal_certificate_alias;

-- no quedó nada con el nombre viejo
SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'afipws%';
SELECT name FROM ir_module_module WHERE name LIKE '%afipws%';
```

En la interfaz: una factura vieja tiene que seguir mostrando su CAE y su vencimiento en
la pestaña ARCA, y el certificado tiene que seguir confirmado en el menú Web services.
