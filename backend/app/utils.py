"""Shared conversion, validation, access-control and geographic helpers."""
from datetime import datetime, timezone
from functools import wraps
from math import asin, cos, radians, sin, sqrt
from uuid import uuid4

from flask import current_app, jsonify
from flask_jwt_extended import get_jwt, jwt_required


def db():
    return current_app.extensions["heat_db"]


def uid():
    return str(uuid4())


def utcnow():
    return datetime.now(timezone.utc)


def json_ready(obj):
    """Convert MongoDB records into JSON-friendly dictionaries."""
    if isinstance(obj, list):
        return [json_ready(item) for item in obj]
    if isinstance(obj, dict):
        return {key: json_ready(value) for key, value in obj.items() if key not in {"_id", "password_hash"}}
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def error(message, status=400):
    return jsonify({"error": message}), status


def number(value, name, minimum=None, maximum=None):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name} must be a number")
    if minimum is not None and result < minimum or maximum is not None and result > maximum:
        raise ValueError(f"{name} is out of range")
    return result


def parse_date(value, name="timestamp"):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise ValueError(f"{name} must be an ISO-8601 date/time")


def admin_only(fn):
    @wraps(fn)
    @jwt_required()
    def wrapped(*args, **kwargs):
        if get_jwt().get("role") != "admin":
            return error("Administrator access required", 403)
        return fn(*args, **kwargs)
    return wrapped


def haversine_km(lat1, lng1, lat2, lng2):
    a1, a2 = radians(lat1), radians(lat2)
    da, dl = radians(lat2 - lat1), radians(lng2 - lng1)
    h = sin(da / 2) ** 2 + cos(a1) * cos(a2) * sin(dl / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(h))


def read_paginated(collection, query=None, order="timestamp", max_page_size=100):
    from flask import request
    try:
        page = max(1, int(request.args.get("page", 1)))
        limit = max(1, min(max_page_size, int(request.args.get("limit", 30))))
    except ValueError:
        raise ValueError("page and limit must be integers")
    query = query or {}
    total = collection.count_documents(query)
    items = list(collection.find(query).sort(order, -1).skip((page - 1) * limit).limit(limit))
    return {"items": json_ready(items), "page": page, "limit": limit, "total": total}


# Heat-risk calculations


def heat_index_c(temperature_c, humidity_pct):

    if temperature_c < 27 or humidity_pct < 40:
        return round(temperature_c, 1)
    t = temperature_c * 9 / 5 + 32
    h = humidity_pct
    hi = (-42.379 + 2.04901523*t + 10.14333127*h - 0.22475541*t*h
          - 0.00683783*t*t - 0.05481717*h*h + 0.00122874*t*t*h
          + 0.00085282*t*h*h - 0.00000199*t*t*h*h)
    return round((hi - 32) * 5 / 9, 1)


def risk_category(heat_index):
    if heat_index >= 32:
        return "high"
    if heat_index >= 27:
        return "moderate"
    return "low"
