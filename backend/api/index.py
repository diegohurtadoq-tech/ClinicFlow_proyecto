"""
Punto de entrada para el runtime de Python de Vercel (@vercel/python).

Vercel empaqueta este archivo junto con el resto del proyecto (`backend/`
es la raiz del build, segun vercel.json) y espera encontrar una variable
`app` con la aplicacion ASGI/WSGI. Toda la app real vive en `app/main.py`;
este archivo solo la reexporta.
"""

from app.main import app  # noqa: F401
