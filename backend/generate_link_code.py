"""
Script de utilidad para generar codigos de vinculacion desde la terminal.
Util para testing sin necesitar autenticacion web.

Uso:
    python generate_link_code.py <patient_id>

Ejemplo:
    python generate_link_code.py 1
"""

import sys
from pathlib import Path

# Agregar el directorio backend al path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal
from app.telegram.authenticator import PatientAuthenticator


def main():
    if len(sys.argv) != 2:
        print("Uso: python generate_link_code.py <patient_id>")
        print("Ejemplo: python generate_link_code.py 1")
        sys.exit(1)

    try:
        patient_id = int(sys.argv[1])
    except ValueError:
        print(f"Error: '{sys.argv[1]}' no es un ID valido")
        sys.exit(1)

    db = SessionLocal()
    try:
        authenticator = PatientAuthenticator()
        code = authenticator.generate_link_code(db, patient_id)

        print()
        print("=" * 60)
        print("  Codigo de Vinculacion Generado")
        print("=" * 60)
        print()
        print(f"  Patient ID: {patient_id}")
        print(f"  Codigo:     {code}")
        print(f"  Expira en:  10 minutos")
        print()
        print("Instrucciones:")
        print(f"  1. Abre Telegram y busca tu bot")
        print(f"  2. Envia: /start {code}")
        print()
        print("=" * 60)
        print()

    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
