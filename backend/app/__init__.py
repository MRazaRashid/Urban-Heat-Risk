"""Flask application factory. Uses MongoDB normally, allows mongomock in tests."""
import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from pymongo import MongoClient, ASCENDING, DESCENDING, GEOSPHERE
from .routes import api


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY", "development-only-change-this-secret"),
        MONGO_URI=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        MONGO_DB=os.getenv("MONGO_DB", "urban_heat_risk"),
    )
    if config:
        app.config.update(config)
    CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])
    JWTManager(app)
    mongo_client = app.config.get("MONGO_CLIENT") or MongoClient(app.config["MONGO_URI"], serverSelectionTimeoutMS=3000)
    app.extensions["heat_mongo_client"] = mongo_client
    app.extensions["heat_db"] = mongo_client[app.config["MONGO_DB"]]
    app.register_blueprint(api)

    @app.get("/health")
    def health():
        try:
            app.extensions["heat_db"].command("ping")
            return jsonify({"status": "ok", "database": "connected"})
        except Exception:
            return jsonify({"status": "unavailable", "database": "offline"}), 503

    @app.errorhandler(404)
    def missing(_):
        return jsonify({"error": "Endpoint not found"}), 404

    return app


def ensure_indexes(database):
    database.readings.create_index([("reading_id", ASCENDING)], unique=True)
    database.readings.create_index([("zone_id", ASCENDING), ("timestamp", DESCENDING)])
    database.zones.create_index("zone_id", unique=True)
    database.cooling_spots.create_index("spot_id", unique=True)
    database.cooling_spots.create_index([("geometry", GEOSPHERE)])
    database.users.create_index("email", unique=True)
    database.favourites.create_index([("user_id", ASCENDING), ("zone_id", ASCENDING)], unique=True)
    database.alerts.create_index([("user_id", ASCENDING), ("zone_id", ASCENDING)])
