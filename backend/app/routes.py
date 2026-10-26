from datetime import datetime, timedelta
import re
from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash, generate_password_hash
from pymongo.errors import DuplicateKeyError

from .utils import heat_index_c, risk_category
from .utils import admin_only, db, error, haversine_km, json_ready, number, parse_date, read_paginated, uid, utcnow

api = Blueprint("api", __name__)


def load_json():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ValueError("A JSON object is required")
    return value


def required(d, *fields):
    missing = [f for f in fields if d.get(f) in (None, "")]
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))


def make_reading(data, existing=None):
    required(data, "zone_id", "sensor_id", "timestamp", "air_temperature_c", "humidity_pct")
    if not db().zones.find_one({"zone_id": data["zone_id"]}):
        raise ValueError("zone_id does not exist")
    temperature = number(data["air_temperature_c"], "air_temperature_c", -70, 70)
    humidity = number(data["humidity_pct"], "humidity_pct", 0, 100)
    zone = db().zones.find_one({"zone_id": data["zone_id"]})
    index = heat_index_c(temperature, humidity)
    result = {
        "reading_id": (existing or {}).get("reading_id", uid()),
        "zone_id": data["zone_id"], "sensor_id": str(data["sensor_id"]),
        "timestamp": parse_date(data["timestamp"]),
        "latitude": number(data.get("latitude", zone["latitude"]), "latitude", -90, 90),
        "longitude": number(data.get("longitude", zone["longitude"]), "longitude", -180, 180),
        "air_temperature_c": temperature, "humidity_pct": humidity,
        "heat_index_c": index,
        "surface_temperature_c": number(data.get("surface_temperature_c", temperature + 3), "surface_temperature_c", -70, 100),
        "risk_category": risk_category(index), "source": data.get("source", "manual"),
    }
    result["quality_flag"] = "review" if abs(result["surface_temperature_c"] - temperature) > 20 else "ok"
    return result


def make_spot(data, existing=None):
    required(data, "spot_name", "spot_type", "address", "latitude", "longitude")
    name = str(data["spot_name"]).strip()
    spot_type = str(data["spot_type"]).strip()
    address = str(data["address"]).strip()
    if not name or not spot_type or not address:
        raise ValueError("spot_name, spot_type and address cannot be blank")
    accessibility = data.get("accessibility", False)
    if not isinstance(accessibility, bool):
        raise ValueError("accessibility must be true or false")
    status = str(data.get("availability_status", "open")).strip().lower()
    if status not in {"open", "closed", "unknown"}:
        raise ValueError("availability_status must be open, closed or unknown")
    lat = number(data["latitude"], "latitude", -90, 90)
    lng = number(data["longitude"], "longitude", -180, 180)
    return {
        "spot_id": (existing or {}).get("spot_id", uid()),
        "spot_name": name, "spot_type": spot_type,
        "address": address,
        "latitude": lat, "longitude": lng,
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "opening_hours": str(data.get("opening_hours", "See facility")),
        "accessibility": accessibility,
        "availability_status": status,
    }


@api.get("/readings")
def list_readings():
    query = {}
    if request.args.get("zone"):
        query["zone_id"] = request.args["zone"]
    if request.args.get("date"):
        try:
            d = datetime.fromisoformat(request.args["date"]).date()
            start = parse_date(d.isoformat())
            query["timestamp"] = {"$gte": start, "$lt": start + timedelta(days=1)}
        except ValueError:
            return error("date must be YYYY-MM-DD")
    try:
        return jsonify(read_paginated(db().readings, query))
    except ValueError as exc:
        return error(str(exc))


@api.get("/readings/<reading_id>")
def get_reading(reading_id):
    item = db().readings.find_one({"reading_id": reading_id})
    return jsonify(json_ready(item)) if item else error("Reading not found", 404)


@api.post("/readings")
@admin_only
def create_reading():
    try:
        item = make_reading(load_json())
    except ValueError as exc:
        return error(str(exc))
    db().readings.insert_one(item)
    return jsonify(json_ready(item)), 201


@api.put("/readings/<reading_id>")
@admin_only
def update_reading(reading_id):
    previous = db().readings.find_one({"reading_id": reading_id})
    if not previous:
        return error("Reading not found", 404)
    try:
        merged = {**previous, **load_json()}
        item = make_reading(merged, previous)
    except ValueError as exc:
        return error(str(exc))
    db().readings.replace_one({"reading_id": reading_id}, item)
    return jsonify(json_ready(item))


@api.delete("/readings/<reading_id>")
@admin_only
def delete_reading(reading_id):
    if not db().readings.delete_one({"reading_id": reading_id}).deleted_count:
        return error("Reading not found", 404)
    return "", 204


def zone_heat_data():
    results = []
    for zone in db().zones.find().sort("neighbourhood", 1):
        reading = db().readings.find_one({"zone_id": zone["zone_id"]}, sort=[("timestamp", -1)])
        item = json_ready(zone)
        item["latest_reading"] = json_ready(reading) if reading else None
        item["risk_category"] = reading["risk_category"] if reading else "unknown"
        item["heat_index_c"] = reading["heat_index_c"] if reading else None
        results.append(item)
    return results


@api.get("/zones/heat-risk")
@api.get("/guest/heat-map")
def zone_heat():
    return jsonify({"zones": zone_heat_data(), "notice": "Demo heat-risk categories, not official public health advice"})


@api.get("/guest/search")
def guest_search():
    zones = zone_heat_data()
    term = request.args.get("q", "").casefold()
    category = request.args.get("risk", "").lower()
    return jsonify({"zones": [z for z in zones if term in z["neighbourhood"].casefold() and (not category or z["risk_category"] == category)]})


@api.get("/cooling-spots")
@api.get("/guest/cooling-spots")
def list_cooling():
    query = {}
    if request.args.get("accessible") == "true":
        query["accessibility"] = True
    if request.args.get("status"):
        query["availability_status"] = request.args["status"]
    results = list(db().cooling_spots.find(query).sort("spot_name", 1))
    return jsonify({"items": json_ready(results), "total": len(results)})


@api.get("/cooling-spots/nearby")
def nearby_cooling():
    try:
        lat = number(request.args.get("lat"), "lat", -90, 90)
        lng = number(request.args.get("lng"), "lng", -180, 180)
        max_km = number(request.args.get("radius_km", 10), "radius_km", 0.1, 100)
    except ValueError as exc:
        return error(str(exc))
    accessible = request.args.get("accessible") == "true"
    query = {"accessibility": True} if accessible else {}
    # Mongo 2dsphere nearby query; mongomock currently lacks $near support.
    try:
        found = list(db().cooling_spots.find({**query, "geometry": {"$near": {
            "$geometry": {"type": "Point", "coordinates": [lng, lat]},
            "$maxDistance": max_km * 1000
        }}}).limit(30))
    except Exception as exc:
        # The fallback also makes the demo usable with lightweight test databases.
        if type(exc).__name__ not in {"NotImplementedError", "OperationFailure", "TypeError"}:
            raise
        found = list(db().cooling_spots.find(query))
    items = []
    for spot in found:
        distance = haversine_km(lat, lng, spot["latitude"], spot["longitude"])
        if distance <= max_km:
            clean = json_ready(spot)
            clean["distance_km"] = round(distance, 2)
            items.append(clean)
    items.sort(key=lambda x: x["distance_km"])
    return jsonify({"items": items[:30], "total": len(items[:30])})


@api.get("/cooling-spots/<spot_id>")
def get_cooling(spot_id):
    item = db().cooling_spots.find_one({"spot_id": spot_id})
    return jsonify(json_ready(item)) if item else error("Cooling spot not found", 404)


@api.post("/admin/cooling-spots")
@admin_only
def create_cooling():
    try:
        item = make_spot(load_json())
    except ValueError as exc:
        return error(str(exc))
    db().cooling_spots.insert_one(item)
    return jsonify(json_ready(item)), 201


@api.put("/admin/cooling-spots/<spot_id>")
@admin_only
def update_cooling(spot_id):
    previous = db().cooling_spots.find_one({"spot_id": spot_id})
    if not previous:
        return error("Cooling spot not found", 404)
    try:
        item = make_spot({**previous, **load_json()}, previous)
    except ValueError as exc:
        return error(str(exc))
    db().cooling_spots.replace_one({"spot_id": spot_id}, item)
    return jsonify(json_ready(item))


@api.delete("/admin/cooling-spots/<spot_id>")
@admin_only
def delete_cooling(spot_id):
    if not db().cooling_spots.delete_one({"spot_id": spot_id}).deleted_count:
        return error("Cooling spot not found", 404)
    return "", 204


@api.get("/analytics/trends")
def analytics():
    match = {}
    if request.args.get("zone"):
        match["zone_id"] = request.args["zone"]
    pipeline = [
        {"$match": match},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "average_temperature": {"$avg": "$air_temperature_c"},
                    "average_heat_index": {"$avg": "$heat_index_c"}, "readings": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    return jsonify({"items": [{"date": r["_id"], "average_temperature": round(r["average_temperature"], 1),
                              "average_heat_index": round(r["average_heat_index"], 1), "readings": r["readings"]}
                             for r in db().readings.aggregate(pipeline)]})


@api.post("/auth/register")
def register():
    try:
        data = load_json()
        required(data, "name", "email", "password")
        email = str(data["email"]).strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("Enter a valid email address")
        if len(str(data["password"])) < 8:
            raise ValueError("Password must be at least 8 characters")
    except ValueError as exc:
        return error(str(exc))
    user = {"user_id": uid(), "name": str(data["name"]).strip(), "email": email,
            "password_hash": generate_password_hash(data["password"]), "role": "user", "created_at": utcnow()}
    try:
        db().users.insert_one(user)
    except DuplicateKeyError:
        return error("Account already exists", 409)
    return jsonify({"message": "Account created"}), 201


@api.post("/auth/login")
def login():
    try:
        data = load_json()
        required(data, "email", "password")
    except ValueError as exc:
        return error(str(exc))
    user = db().users.find_one({"email": str(data["email"]).lower().strip()})
    if not user or not check_password_hash(user["password_hash"], data["password"]):
        return error("Invalid email or password", 401)
    token = create_access_token(identity=user["user_id"], additional_claims={"role": user["role"]}, expires_delta=timedelta(hours=8))
    return jsonify({"access_token": token, "user": {"name": user["name"], "role": user["role"], "email": user["email"]}})


@api.get("/admin/readings")
@admin_only
def admin_readings():
    try:
        return jsonify(read_paginated(db().readings))
    except ValueError as exc:
        return error(str(exc))


@api.get("/admin/data-quality")
@admin_only
def flagged_readings():
    items = list(db().readings.find({"quality_flag": "review"}).sort("timestamp", -1).limit(100))
    return jsonify({"items": json_ready(items), "total": len(items)})


@api.post("/user/favourites")
@jwt_required()
def add_favourite():
    try:
        data = load_json()
        required(data, "zone_id")
    except ValueError as exc:
        return error(str(exc))
    if not db().zones.find_one({"zone_id": data["zone_id"]}):
        return error("Zone not found", 404)
    doc = {"favourite_id": uid(), "user_id": get_jwt_identity(), "zone_id": data["zone_id"], "saved_at": utcnow()}
    try:
        db().favourites.insert_one(doc)
    except DuplicateKeyError:
        return error("Zone already saved", 409)
    return jsonify(json_ready(doc)), 201


@api.get("/user/favourites")
@jwt_required()
def favourites():
    items = list(db().favourites.find({"user_id": get_jwt_identity()}))
    return jsonify({"items": json_ready(items)})


@api.delete("/user/favourites/<favourite_id>")
@jwt_required()
def delete_favourite(favourite_id):
    outcome = db().favourites.delete_one({"favourite_id": favourite_id, "user_id": get_jwt_identity()})
    return ("", 204) if outcome.deleted_count else error("Favourite not found", 404)


@api.post("/user/alerts")
@jwt_required()
def create_alert():
    try:
        data = load_json()
        required(data, "zone_id", "threshold_c")
        threshold = number(data["threshold_c"], "threshold_c", -20, 65)
    except ValueError as exc:
        return error(str(exc))
    if not db().zones.find_one({"zone_id": data["zone_id"]}):
        return error("Zone not found", 404)
    item = {"alert_id": uid(), "user_id": get_jwt_identity(), "zone_id": data["zone_id"],
            "threshold_c": threshold, "enabled": True, "created_at": utcnow()}
    db().alerts.insert_one(item)
    return jsonify(json_ready(item)), 201


@api.get("/user/alerts")
@jwt_required()
def alerts():
    items = []
    for item in db().alerts.find({"user_id": get_jwt_identity()}):
        zone_reading = db().readings.find_one({"zone_id": item["zone_id"]}, sort=[("timestamp", -1)])
        view = json_ready(item)
        view["triggered_now"] = bool(item["enabled"] and zone_reading and zone_reading["heat_index_c"] >= item["threshold_c"])
        items.append(view)
    return jsonify({"items": items})


@api.put("/user/alerts/<alert_id>")
@jwt_required()
def edit_alert(alert_id):
    current = db().alerts.find_one({"alert_id": alert_id, "user_id": get_jwt_identity()})
    if not current:
        return error("Alert not found", 404)
    try:
        data = load_json()
        changes = {}
        if "threshold_c" in data:
            changes["threshold_c"] = number(data["threshold_c"], "threshold_c", -20, 65)
        if "enabled" in data:
            if not isinstance(data["enabled"], bool):
                raise ValueError("enabled must be true or false")
            changes["enabled"] = data["enabled"]
        if not changes:
            raise ValueError("No changes supplied")
    except ValueError as exc:
        return error(str(exc))
    db().alerts.update_one({"alert_id": alert_id, "user_id": get_jwt_identity()}, {"$set": changes})
    return jsonify(json_ready(db().alerts.find_one({"alert_id": alert_id})))


@api.delete("/user/alerts/<alert_id>")
@jwt_required()
def delete_alert(alert_id):
    outcome = db().alerts.delete_one({"alert_id": alert_id, "user_id": get_jwt_identity()})
    return ("", 204) if outcome.deleted_count else error("Alert not found", 404)
