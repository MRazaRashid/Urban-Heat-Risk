# Urban Heat Risk Monitoring & Cooling Spot Finder

A **Flask REST API backed by MongoDB** for exploring simulated urban heat conditions, classifying heat risk, finding nearby cooling spots, and managing personal favourites and heat alerts.

This is a **university coursework / demonstration project**. Its weather readings, neighbourhood data and cooling facilities are synthetic; the application is not a live weather-monitoring or public-health service.

## Contents

1. [Project overview](#project-overview)
2. [Main features](#main-features)
3. [Technology stack](#technology-stack)
4. [Project structure](#project-structure)
5. [Prerequisites](#prerequisites)
6. [Installation and configuration](#installation-and-configuration)
7. [MongoDB database and sample data](#mongodb-database-and-sample-data)
8. [Running the API](#running-the-api)
9. [API endpoints](#api-endpoints)
10. [Authentication and access control](#authentication-and-access-control)
11. [Postman testing](#postman-testing)
12. [Implementation details](#implementation-details)
13. [Troubleshooting](#troubleshooting)
14. [Data limitations and security](#data-limitations-and-security)

## Project overview

The application stores and analyses temperature and humidity readings from six fictional urban zones. It calculates an illustrative heat index and low/moderate/high heat-risk category, exposes the latest conditions through public endpoints, and finds cooling spots close to a supplied latitude and longitude.

Registered users can save **zones** as favourites and set temperature-threshold alerts. Administrators can manage readings and cooling-spot records.

The backend offers **29 HTTP route mappings**, including `/health`, and supports GET, POST, PUT and DELETE requests.

## Main features

- View, filter and paginate temperature/humidity readings.
- Retrieve the latest heat-risk status for each neighbourhood.
- Search zones by neighbourhood name and risk level.
- List cooling spots, filter by accessibility/status and search by distance.
- Generate daily analytics using a MongoDB aggregation pipeline.
- Register users and authenticate using JSON Web Tokens (JWT).
- Restrict selected create/update/delete operations to administrators.
- Save and remove a user's favourite zones.
- Create, view, update and delete user heat-threshold alerts.
- Revoke JWTs on logout using a MongoDB blacklist and automatically expire blacklist records using a TTL index.
- Validate required fields and common input ranges, and return JSON responses with appropriate HTTP status codes.

## Technology stack

| Component | Technology |
|---|---|
| API server | Python, Flask |
| Database | MongoDB, PyMongo |
| Authentication | Flask-JWT-Extended, Werkzeug password hashing |
| Cross-origin requests | Flask-CORS |
| Configuration | python-dotenv and environment variables |
| Automated API testing | Postman Collection Runner |
| Optional Python testing | pytest and mongomock (listed in `requirements.txt`) |

## Project structure

The following shows the core backend files. Other folders, such as coursework documents or test files, may be included separately.

```text
Urban-Heat-Risk/
├── README.md
└── backend/
    ├── app/
    │   ├── __init__.py       # Flask app factory, MongoDB connection, JWT and indexes
    │   ├── routes.py         # HTTP endpoints and request handling
    │   └── utils.py          # Validation, calculations, pagination and access helpers
    ├── data/                 # Sample dataset files, where included
    ├── .env                  # Local secrets; do NOT commit to Git
    ├── .gitignore
    ├── requirements.txt
    └── run.py                # Starts the local Flask API on port 5001
```

## Prerequisites

- Python 3.10 or newer recommended.
- MongoDB Community Server running locally, or another reachable MongoDB instance.
- PowerShell or another terminal.
- Postman (recommended for API testing).
- **Optional:** MongoDB Compass for viewing collections and indexes.
- **Optional:** MongoDB Database Tools for using `mongoimport`.

## Installation and configuration

The commands below use **Windows PowerShell**, from the repository's root folder.

### 1. Clone the repository

```powershell
git clone https://github.com/MRazaRashid/Urban-Heat-Risk.git
cd Urban-Heat-Risk\backend
```

If the project is already downloaded, open a terminal in its `backend` folder instead.

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Create `backend/.env`

Create a file named `.env` inside the `backend` directory:

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB=UrbanHeat
JWT_SECRET_KEY=REPLACE_WITH_YOUR_OWN_RANDOM_SECRET
```

The value `UrbanHeat` matches the database name shown in this project's MongoDB Compass setup. If your MongoDB database has a different name, set `MONGO_DB` to **that exact name**. If the variable is omitted, the code defaults to `urban_heat_risk`.

Generate a secure JWT signing key in PowerShell:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value into `JWT_SECRET_KEY`. Never commit `.env`, JWT secrets, admin passwords or exported user credentials.

If your project includes a separate administrator-provisioning script, it may use `ADMIN_EMAIL` and `ADMIN_PASSWORD` from `.env`. **Those variables alone do not create an admin account** in the uploaded Flask app; an administrator must already exist in the database for admin login to work.

## MongoDB database and sample data

The application uses these MongoDB collections:

| Collection | Purpose |
|---|---|
| `zones` | Neighbourhood metadata and geographic coordinates |
| `readings` | Timestamped simulated temperature and humidity observations |
| `cooling_spots` | Demonstration cooling locations with GeoJSON coordinates |
| `users` | Registered accounts and password hashes |
| `favourites` | Zones saved by individual users |
| `alerts` | User-configured heat thresholds |
| `blacklist` | Revoked JWT identifiers until expiry |

### Demonstration dataset

The prepared sample dataset includes:

| Dataset | Records |
|---|---:|
| Readings | 13,248 |
| Zones | 6 |
| Cooling spots | 20 |

The sample readings cover **1 June to 31 August 2025**, at hourly intervals across the six zones. The zone IDs include `central`, `riverside`, `north`, `east`, `west` and `south`.

The records are **synthetic**, and the cooling-spot addresses are **fictional**.

### Import sample JSON data (if needed)

If `backend/data/` contains the corresponding JSON files and `mongoimport` is installed, run these commands **from the `backend` folder**:

```powershell
mongoimport --uri "mongodb://localhost:27017" --db UrbanHeat --collection zones --file "data/zones.json" --jsonArray --mode upsert --upsertFields zone_id
mongoimport --uri "mongodb://localhost:27017" --db UrbanHeat --collection cooling_spots --file "data/cooling_spots.json" --jsonArray --mode upsert --upsertFields spot_id
mongoimport --uri "mongodb://localhost:27017" --db UrbanHeat --collection readings --file "data/readings.json" --jsonArray --mode upsert --upsertFields reading_id
```

Use the database name configured in `.env`. These commands are only necessary if the sample records have not already been imported. The sample JSON should preserve timestamps as MongoDB dates for date filtering and aggregation.

Do **not** overwrite your `users`, `favourites`, `alerts` or `blacklist` collections when loading the example dataset.

## Running the API

Start MongoDB first. Then, from the `backend` folder with the virtual environment active:

```powershell
python run.py
```

The API runs at:

```text
http://127.0.0.1:5001
```

Test the connection using a browser or Postman:

```text
GET http://127.0.0.1:5001/health
```

Expected response when the database is connected:

```json
{
  "status": "ok",
  "database": "connected"
}
```

## API endpoints

**Base URL:** `http://127.0.0.1:5001`

**Access key:** Public = no token; User = valid logged-in user JWT; Admin = valid administrator JWT. All protected requests use `Authorization: Bearer <token>`.

### Public, guest and analytics routes

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Check API and MongoDB connectivity |
| GET | `/readings` | List readings; supports `zone`, `date`, `page`, `limit` |
| GET | `/readings/<reading_id>` | Get a single reading |
| GET | `/zones/heat-risk` | Latest heat conditions and risk for each zone |
| GET | `/guest/heat-map` | Alternative path for zone heat-risk data |
| GET | `/guest/search` | Search zones using `q` and optional `risk` |
| GET | `/cooling-spots` | List cooling spots; optional `accessible` and `status` |
| GET | `/guest/cooling-spots` | Alternative path for cooling spots |
| GET | `/cooling-spots/nearby` | Search by `lat`, `lng`, `radius_km`, optional `accessible` |
| GET | `/cooling-spots/<spot_id>` | Get one cooling spot |
| GET | `/analytics/trends` | Daily aggregation; optional `zone` |

### Registration, login and logout

| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/auth/register` | Public | Create a normal user |
| GET | `/auth/login` | Public | Validate email/password and issue an eight-minute JWT |
| GET | `/auth/logout` | User/Admin | Revoke the supplied JWT by saving its `jti` in the blacklist |

**Important:** These are the methods in the current uploaded code. Login reads `email` and `password` as URL **query parameters**, not a JSON body. GET login and GET logout are demonstration choices; for production, authentication actions should use POST over HTTPS.

### Administrator routes

| Method | Endpoint | Description |
|---|---|---|
| POST | `/readings` | Create a reading |
| PUT | `/readings/<reading_id>` | Update a reading |
| DELETE | `/readings/<reading_id>` | Delete a reading |
| GET | `/admin/readings` | Paginated readings for admin |
| GET | `/admin/data-quality` | Find readings with `quality_flag: review` |
| POST | `/admin/cooling-spots` | Create a cooling spot |
| PUT | `/admin/cooling-spots/<spot_id>` | Update a cooling spot |
| DELETE | `/admin/cooling-spots/<spot_id>` | Delete a cooling spot |

### Registered-user routes

| Method | Endpoint | Description |
|---|---|---|
| POST | `/user/favourites` | Save an existing zone |
| GET | `/user/favourites` | List the current user's favourites |
| DELETE | `/user/favourites/<favourite_id>` | Delete a favourite |
| POST | `/user/alerts` | Create a threshold alert |
| GET | `/user/alerts` | List alerts and whether their thresholds are currently met |
| PUT | `/user/alerts/<alert_id>` | Update an alert |
| DELETE | `/user/alerts/<alert_id>` | Delete an alert |

### Example API requests

**List a zone's readings:**

```text
GET http://127.0.0.1:5001/readings?zone=central&limit=5
```

**Find accessible cooling spots nearby:**

```text
GET http://127.0.0.1:5001/cooling-spots/nearby?lat=51.5074&lng=-0.1278&radius_km=3&accessible=true
```

**Register a user (Body → raw → JSON):**

```http
POST /auth/register
Content-Type: application/json
```

```json
{
  "name": "Test User",
  "email": "test.user@example.com",
  "password": "ReplaceWithATestPassword123!"
}
```

**Log in (Params tab in Postman):**

```text
GET /auth/login?email=test.user%40example.com&password=YOUR_TEST_PASSWORD
```

**Add a zone to favourites (valid JWT required):**

```http
POST /user/favourites
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "zone_id": "central"
}
```

**Create an alert (valid JWT required):**

```http
POST /user/alerts
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "zone_id": "central",
  "threshold_c": 30
}
```

**Create a reading (admin JWT required):**

```json
{
  "zone_id": "central",
  "sensor_id": "postman-demo",
  "timestamp": "2025-08-15T12:00:00Z",
  "air_temperature_c": 34,
  "humidity_pct": 65,
  "surface_temperature_c": 38
}
```

For POST and PUT endpoints, send JSON with `Content-Type: application/json`.

## Authentication and access control

The API uses **Flask-JWT-Extended**. Passwords are stored as hashes instead of plaintext. Registration always creates a `user` role; administrator access is restricted using the `admin_only` decorator.

JWTs issued by `/auth/login` expire after **eight minutes**. For a protected request, set the HTTP header:

```text
Authorization: Bearer <access_token>
```

On logout, the JWT identifier (`jti`) is saved in MongoDB's `blacklist` collection. A JWT callback checks that collection when validating protected requests, so a revoked token is rejected. A MongoDB **TTL index** on `expires_at` removes expired blacklist records automatically; an empty blacklist after expiry is expected.

Common response codes include `200 OK`, `201 Created`, `204 No Content`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found` and `409 Conflict`.

## Postman testing

The API has been tested with an automated Postman Collection Runner workflow covering public routes, registration/login, administrator CRUD, cooling-spot searches, favourites, alerts, logout and revoked-token rejection.

The **Postman run shown in the supplied coursework screenshots** reports:

| Result | Value |
|---|---:|
| Test assertions | 43 |
| Passed | 43 |
| Failed | 0 |
| Skipped | 0 |
| Errors | 0 |
| Iterations | 1 |
| Duration | 3 s 576 ms |
| Average response time | 22 ms |

To reproduce the test run:

1. Start MongoDB and the Flask API.
2. Import your Postman collection and local environment.
3. Set `baseUrl` to `http://127.0.0.1:5001`.
4. Configure a valid pre-existing administrator account in the Postman environment.
5. Run the collection **in its defined order**; several requests save IDs or tokens for later tests.
6. Save the Runner results for your coursework evidence.

The provided results describe the recorded test run; they do not imply the test suite was rerun for this README.

## Implementation details

### Heat-risk calculation

`utils.py` calculates a demonstration heat index using a Rothfusz-style regression in its intended hot/humid range. The project then labels the calculated value:

| Heat index | Demo risk category |
|---|---|
| Below 27°C | Low |
| 27°C to below 32°C | Moderate |
| 32°C or above | High |

These thresholds are for coursework demonstration and are **not official public-health advice**.

### MongoDB functionality

The backend demonstrates:

- **CRUD** operations on readings, cooling spots, favourites and alerts.
- **Filtering and pagination** for reading listings.
- **Aggregation** with `$match`, `$group` and `$sort` for daily trends.
- **Geospatial search** using GeoJSON Points, a `2dsphere` index and `$near`, with Haversine distance calculations.
- **Indexes** for uniqueness, common lookups and the JWT blacklist.
- **TTL cleanup** of expired revoked tokens.

### Validation

Routes validate required fields, zone existence, date formats, selected numeric ranges, cooling-spot availability status and some account inputs. Validation should continue to be extended and tested as the project evolves.

## Troubleshooting

| Problem | What to check |
|---|---|
| Flask cannot connect to MongoDB | MongoDB is running; `MONGO_URI` and `MONGO_DB` match your setup |
| `JWT_SECRET_KEY is missing` | Create `backend/.env`, set a secure key, restart Flask |
| `401 Missing Authorization Header` | Set Postman Authorization to **Bearer Token**, not `x-access-token` |
| `422 Not enough segments` | The token value is malformed or the Postman environment variable is empty |
| `401` after logging out | Expected: the token has been revoked |
| `403 Administrator access required` | Log in with an existing account whose database role is `admin` |
| `404 Reading not found` | Verify the `reading_id`; create the test record first |
| `409 Zone already saved` | The user has already favourited that zone |
| Empty `blacklist` collection | Revoked tokens are removed after expiry by MongoDB TTL cleanup |
| Port `5001` unavailable | Close the process using the port, or update `run.py` and Postman `baseUrl` |


**Project repository:** https://github.com/MRazaRashid/Urban-Heat-Risk

**Project status:** Flask/MongoDB back-end API with documented endpoints and a recorded automated Postman test run.
