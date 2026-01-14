#!/usr/bin/env python3
# pylint: skip-file
# flake8: noqa
"""
Script para verificar que un certificado y una clave privada correspondan.
Uso: python3 verify_certificate_pair.py <certificado.crt> <clave.key>
"""

import hashlib
import sys


def verify_certificate_key_pair(cert_path, key_path):
    """Verifica que el certificado y la clave privada sean un par válido."""

    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_private_key
    except ImportError:
        print("❌ Error: Falta instalar cryptography")
        print("Ejecute: pip install cryptography")
        return False

    print("=" * 70)
    print("VERIFICACIÓN DE PAR CERTIFICADO-CLAVE PRIVADA")
    print("=" * 70)

    # 1. Cargar certificado
    try:
        print(f"\n1️⃣  Cargando certificado: {cert_path}")
        with open(cert_path, "rb") as f:
            cert_data = f.read()

        cert = x509.load_pem_x509_certificate(cert_data, default_backend())

        # Mostrar información del certificado
        subject = cert.subject
        issuer = cert.issuer

        print("   ✓ Certificado cargado correctamente")
        print(
            f"   Subject CN: {subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value if subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME) else 'N/A'}"
        )
        print(
            f"   Issuer CN: {issuer.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value if issuer.get_attributes_for_oid(x509.NameOID.COMMON_NAME) else 'N/A'}"
        )
        print(f"   Válido desde: {cert.not_valid_before_utc}")
        print(f"   Válido hasta: {cert.not_valid_after_utc}")

    except FileNotFoundError:
        print(f"   ❌ Error: Archivo no encontrado: {cert_path}")
        return False
    except Exception as e:
        print(f"   ❌ Error al cargar certificado: {e}")
        return False

    # 2. Cargar clave privada
    try:
        print(f"\n2️⃣  Cargando clave privada: {key_path}")
        with open(key_path, "rb") as f:
            key_data = f.read()

        # Intentar cargar con y sin contraseña
        try:
            pkey = load_pem_private_key(key_data, password=None, backend=default_backend())
            print("   ✓ Clave privada cargada correctamente (sin contraseña)")
        except ValueError as e:
            if "password" in str(e).lower():
                print("   ⚠️  La clave privada está protegida con contraseña")
                password = input("   Ingrese la contraseña de la clave privada: ").encode()
                try:
                    pkey = load_pem_private_key(key_data, password=password, backend=default_backend())
                    print("   ✓ Clave privada cargada correctamente (con contraseña)")
                    print("\n   ⚠️  ADVERTENCIA: AFIP requiere clave SIN contraseña")
                    print("   Para eliminar la contraseña ejecute:")
                    print(f"   openssl rsa -in {key_path} -out clave_sin_pass.key")
                except Exception as e2:
                    print(f"   ❌ Error: Contraseña incorrecta o clave inválida: {e2}")
                    return False
            else:
                raise

        key_size = pkey.key_size
        print(f"   Tamaño de clave: {key_size} bits")

    except FileNotFoundError:
        print(f"   ❌ Error: Archivo no encontrado: {key_path}")
        return False
    except Exception as e:
        print(f"   ❌ Error al cargar clave privada: {e}")
        return False

    # 3. Comparar claves públicas
    try:
        print("\n3️⃣  Comparando claves públicas...")

        # Obtener clave pública del certificado
        cert_public_key = cert.public_key()
        cert_pub_bytes = cert_public_key.public_bytes(encoding=Encoding.DER, format=PublicFormat.SubjectPublicKeyInfo)
        cert_hash = hashlib.sha256(cert_pub_bytes).hexdigest()

        # Obtener clave pública de la clave privada
        pkey_public_key = pkey.public_key()
        pkey_pub_bytes = pkey_public_key.public_bytes(encoding=Encoding.DER, format=PublicFormat.SubjectPublicKeyInfo)
        pkey_hash = hashlib.sha256(pkey_pub_bytes).hexdigest()

        print(f"   Hash certificado: {cert_hash}")
        print(f"   Hash clave privada: {pkey_hash}")

        # Comparar
        if cert_pub_bytes == pkey_pub_bytes:
            print("\n   ✅ LOS ARCHIVOS SON UN PAR VÁLIDO")
            print("   La clave privada corresponde al certificado")
            return True
        else:
            print("\n   ❌ LOS ARCHIVOS NO CORRESPONDEN")
            print("   La clave privada NO corresponde al certificado")
            print("\n   Esto significa que:")
            print("   - Está usando una clave diferente a la del CSR")
            print("   - No podrá autenticarse con AFIP usando estos archivos")
            print("\n   SOLUCIÓN:")
            print("   1. Busque la clave original que usó para el CSR")
            print("   2. O genere un nuevo certificado completo en AFIP")
            return False

    except Exception as e:
        print(f"   ❌ Error al comparar claves: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python3 verify_certificate_pair.py <certificado.crt> <clave.key>")
        print("\nEjemplo:")
        print("  python3 verify_certificate_pair.py certificado.crt clave.key")
        sys.exit(1)

    cert_file = sys.argv[1]
    key_file = sys.argv[2]

    result = verify_certificate_key_pair(cert_file, key_file)

    print("\n" + "=" * 70)
    if result:
        print("RESULTADO: ✅ PAR VÁLIDO - Puede usar estos archivos en Odoo")
    else:
        print("RESULTADO: ❌ PAR INVÁLIDO - NO puede usar estos archivos")
    print("=" * 70)

    sys.exit(0 if result else 1)
