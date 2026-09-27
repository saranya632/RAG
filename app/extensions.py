"""Flask extension objects, created once and bound to the app in create_app().

Kept in their own module so models, routes and services can import them
without importing the app factory (which would create circular imports).
"""
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()   # PostgreSQL access (user accounts)
jwt = JWTManager()  # issues and verifies JWT access tokens
