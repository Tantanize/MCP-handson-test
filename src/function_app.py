import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any

# azure.functions is only available in the Functions runtime; provide a minimal stub for local tests
try:
    import azure.functions as func
except ImportError:
    class _FuncStub:
        class AuthLevel:
            FUNCTION = None
        class FunctionApp:
            def __init__(self, *args, **kwargs):
                pass
            def mcp_tool(self, *args, **kwargs):
                def deco(fn):
                    return fn
                return deco
            def mcp_tool_property(self, *args, **kwargs):
                def deco(fn):
                    return fn
                return deco
            def blob_input(self, *args, **kwargs):
                def deco(fn):
                    return fn
                return deco
            def blob_output(self, *args, **kwargs):
                def deco(fn):
                    return fn
                return deco
            def mcp_resource_trigger(self, *args, **kwargs):
                def deco(fn):
                    return fn
                return deco
        class Out:
            def __getitem__(self, key):
                return _FuncStub.Out
        def __getattr__(self, name):
            # return simple decorator for unknown methods
            def deco(*args, **kwargs):
                def inner(fn):
                    return fn
                return inner
            return deco
    func = _FuncStub()

# weather_service is used by other tools; make import optional during testing
try:
    from weather_service import WeatherService
except ImportError:
    class WeatherService:
        def get_current_weather(self, location: str):
            return {"Location": location or "", "Error": "stub", "Source": "local"}

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Weather service instance
weather_service = WeatherService()

# Constants for the Weather Widget resource
WEATHER_WIDGET_URI = "ui://weather/index.html"
WEATHER_WIDGET_NAME = "Weather Widget"
WEATHER_WIDGET_DESCRIPTION = "Interactive weather display for MCP Apps"
WEATHER_WIDGET_MIME_TYPE = "text/html;profile=mcp-app"

# Metadata for the tool (as valid JSON string)
TOOL_METADATA = '{"ui": {"resourceUri": "ui://weather/index.html"}}'

# Metadata for the resource (as valid JSON string)
RESOURCE_METADATA = '{"ui": {"prefersBorder": true}}'

# Constants for the Azure Blob Storage container, file, and blob path
_SNIPPET_NAME_PROPERTY_NAME = "snippetname"
_BLOB_PATH = "snippets/{mcptoolargs." + _SNIPPET_NAME_PROPERTY_NAME + "}.json"


@app.mcp_tool()
def hello_mcp() -> str:
    """Hello world."""
    return "Hello I am MCPTool!"


@app.mcp_tool()
@app.mcp_tool_property(arg_name="snippetname", description="The name of the snippet.")
@app.blob_input(arg_name="file", connection="AzureWebJobsStorage", path=_BLOB_PATH)
def get_snippet(file: func.InputStream, snippetname: str) -> str:
    """Retrieve a snippet by name from Azure Blob Storage."""
    snippet_content = file.read().decode("utf-8")
    logging.info(f"Retrieved snippet: {snippet_content}")
    return snippet_content


@app.mcp_tool()
@app.mcp_tool_property(arg_name="snippetname", description="The name of the snippet.")
@app.mcp_tool_property(arg_name="snippet", description="The content of the snippet.")
@app.blob_output(arg_name="file", connection="AzureWebJobsStorage", path=_BLOB_PATH)
def save_snippet(file: func.Out[str], snippetname: str, snippet: str) -> str:
    """Save a snippet with a name to Azure Blob Storage."""
    if not snippetname:
        return "No snippet name provided"

    if not snippet:
        return "No snippet content provided"

    file.set(snippet)
    logging.info(f"Saved snippet: {snippet}")
    return f"Snippet '{snippet}' saved successfully"


# Weather Widget Resource - returns HTML content for the weather widget
@app.mcp_resource_trigger(
    arg_name="context",
    uri=WEATHER_WIDGET_URI,
    resource_name=WEATHER_WIDGET_NAME,
    description=WEATHER_WIDGET_DESCRIPTION,
    mime_type=WEATHER_WIDGET_MIME_TYPE,
    metadata=RESOURCE_METADATA
)
def get_weather_widget(context) -> str:
    """Get the weather widget HTML content."""
    logging.info("Getting weather widget")
    
    try:
        # Get the path to the widget HTML file
        # Current file is src/function_app.py, look for src/app/index.html
        current_dir = Path(__file__).parent
        file_path = current_dir / "app" / "dist" / "index.html"
        
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        else:
            logging.warning(f"Weather widget file not found at: {file_path}")
            # Return a fallback HTML if file not found
            return """<!DOCTYPE html>
<html>
<head><title>Weather Widget</title></head>
<body>
  <h1>Weather Widget</h1>
  <p>Widget content not found. Please ensure the app/index.html file exists.</p>
</body>
</html>"""
    except Exception as e:
        logging.error(f"Error reading weather widget file: {e}")
        return """<!DOCTYPE html>
<html>
<head><title>Weather Widget Error</title></head>
<body>
  <h1>Weather Widget</h1>
  <p>Error loading widget content.</p>
</body>
</html>"""


# Get Weather Tool - returns current weather for a location
@app.mcp_tool(metadata=TOOL_METADATA)
@app.mcp_tool_property(arg_name="location", description="City name to check weather for (e.g., Seattle, New York, Miami)")
def get_weather(location: str) -> Dict[str, Any]:
    """Returns current weather for a location via Open-Meteo."""
    logging.info(f"Getting weather for location: {location}")
    
    try:
        result = weather_service.get_current_weather(location)
        
        if "TemperatureC" in result:
            logging.info(f"Weather fetched for {result['Location']}: {result['TemperatureC']}°C")
        else:
            logging.warning(f"Weather error for {result['Location']}: {result.get('Error', 'Unknown error')}")
        
        return json.dumps(result)
    except Exception as e:
        logging.error(f"Failed to get weather for {location}: {e}")
        return json.dumps({
            "Location": location or "Unknown",
            "Error": f"Unable to fetch weather: {str(e)}",
            "Source": "api.open-meteo.com"
        })


# ---------------------------------------------------------------------------
# Movie list tool implementation
# ---------------------------------------------------------------------------

@app.mcp_tool()
@app.mcp_tool_property(arg_name="date", description="Filter movies by this date (YYYY-MM-DD)")
@app.mcp_tool_property(arg_name="query", description="Search text to filter movie titles")
@app.mcp_tool_property(arg_name="limit", description="Maximum number of movies to return")
def get_movie_list(date: str = None, query: str = None, limit: int = None) -> str:
    """Return a JSON string listing movies, optionally filtered by date and/or query.

    Implements the logic described in documents/detailed-design.md.
    """
    # helper for error response
    def err(code: int, msg: str):
        return json.dumps({"error": {"code": code, "message": msg}})

    # validation
    try:
        if date:
            # simple YYYY-MM-DD check
            import re
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                return err(-32602, "Invalid date format")
        if query is not None and not isinstance(query, str):
            return err(-32602, "Query must be a string")
        if limit is not None:
            if not isinstance(limit, int) or limit <= 0:
                return err(-32602, "Limit must be a positive integer")
    except Exception as ex:
        return err(-32602, str(ex))

    # Load movies
    data_dir = Path(__file__).parent / "data"
    movies_path = data_dir / "movies.json"
    try:
        movies = json.loads(movies_path.read_text(encoding="utf-8"))
    except Exception:
        movies = []

    # filter by date if requested
    if date:
        schedules_path = data_dir / "schedules.json"
        try:
            schedules = json.loads(schedules_path.read_text(encoding="utf-8"))
        except Exception:
            schedules = []
        ids = {sch["movie_id"] for sch in schedules if sch.get("date") == date}
        movies = [m for m in movies if m.get("movie_id") in ids]

    # filter by query
    if query:
        norm = lambda s: s.lower()
        movies = [m for m in movies if query.lower() in norm(m.get("title", "")) or query.lower() in norm(m.get("description", ""))]

    # sort by recommendation and rating
    movies.sort(key=lambda m: (0 if m.get("recommended") else 1, -m.get("rating", 0)))

    # apply limit
    if limit is not None:
        movies = movies[:limit]

    return json.dumps({"movies": movies})


# ---------------------------------------------------------------------------
# Show schedule tool implementation
# ---------------------------------------------------------------------------

_MOVIES_BLOB_PATH = "movies/movies.json"
_SCHEDULES_BLOB_PATH = "movies/schedules.json"


@app.mcp_tool()
@app.mcp_tool_property(arg_name="movie_id", description="ID of the target movie")
@app.mcp_tool_property(arg_name="date", description="Date to search (YYYY-MM-DD). Defaults to next 7 days if omitted.")
@app.blob_input(arg_name="movies_blob", connection="AzureWebJobsStorage", path=_MOVIES_BLOB_PATH)
@app.blob_input(arg_name="schedules_blob", connection="AzureWebJobsStorage", path=_SCHEDULES_BLOB_PATH)
def get_show_schedule(movies_blob: func.InputStream, schedules_blob: func.InputStream, movie_id: str, date: str = None) -> str:
    """指定した映画の上映スケジュール一覧を取得します。"""
    def err(code: int, msg: str):
        return json.dumps({"error": {"code": code, "message": msg}})

    # 1. Input validation
    if not movie_id or not isinstance(movie_id, str):
        return err(-32602, "movie_id is required and must be a non-empty string")

    if date is not None:
        if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return err(-32602, "Invalid date format. Expected YYYY-MM-DD")

    # 2. Movie existence check (from Blob)
    try:
        movies = json.loads(movies_blob.read().decode("utf-8")) if movies_blob else []
    except Exception:
        movies = []

    if not any(m.get("movie_id") == movie_id for m in movies):
        return err(-32602, f"Movie not found: {movie_id}")

    # 3. Schedule extraction (from Blob)
    try:
        schedules = json.loads(schedules_blob.read().decode("utf-8")) if schedules_blob else []
    except Exception:
        schedules = []

    matched = [s for s in schedules if s.get("movie_id") == movie_id]

    if not matched:
        return json.dumps({"schedules": []})

    # 4. Date filter
    if date:
        matched = [s for s in matched if s.get("date") == date]
    else:
        today = datetime.now().date()
        end_date = today + timedelta(days=7)
        filtered = []
        for s in matched:
            try:
                s_date = datetime.strptime(s.get("date", ""), "%Y-%m-%d").date()
                if today <= s_date <= end_date:
                    filtered.append(s)
            except ValueError:
                continue
        matched = filtered

    # 5. Build response
    result = []
    for s in matched:
        result.append({
            "schedule_id": s.get("schedule_id"),
            "date": s.get("date"),
            "start_time": s.get("start_time"),
            "end_time": s.get("end_time"),
            "theater_id": s.get("theater_id"),
            "theater_name": s.get("theater_name"),
            "available_seats_count": s.get("available_seats_count"),
            "total_seats_count": s.get("total_seats_count"),
        })

    return json.dumps({"schedules": result})


# ---------------------------------------------------------------------------
# Seat availability tool implementation
# ---------------------------------------------------------------------------

_SEAT_AVAILABILITY_BLOB_PATH = "movies/seat_availability.json"


@app.mcp_tool()
@app.mcp_tool_property(arg_name="schedule_id", description="Target schedule ID")
@app.blob_input(arg_name="seats_blob", connection="AzureWebJobsStorage", path=_SEAT_AVAILABILITY_BLOB_PATH)
def get_seat_availability(seats_blob: func.InputStream, schedule_id: str) -> str:
    """指定上映回の座席一覧と各座席の状態を取得します。"""
    def err(code: int, msg: str):
        return json.dumps({"error": {"code": code, "message": msg}})

    # 1. Input validation
    if not schedule_id or not isinstance(schedule_id, str):
        return err(-32602, "schedule_id is required and must be a non-empty string")

    # 2. Data lookup (from Blob)
    try:
        seat_data = json.loads(seats_blob.read().decode("utf-8")) if seats_blob else []
    except Exception:
        seat_data = []

    entry = None
    for item in seat_data:
        if item.get("schedule_id") == schedule_id:
            entry = item
            break

    if entry is None:
        return err(-32602, f"Schedule not found: {schedule_id}")

    # 3. Count available / reserved from actual seat statuses
    seats = entry.get("seats", [])
    available_count = sum(1 for s in seats if s.get("status") == "available")
    reserved_count = sum(1 for s in seats if s.get("status") == "reserved")

    # 4. Build response
    return json.dumps({
        "schedule_id": schedule_id,
        "seats": seats,
        "available_count": available_count,
        "reserved_count": reserved_count,
    })


# ---------------------------------------------------------------------------
# Reserve seats tool implementation
# ---------------------------------------------------------------------------

_RESERVATIONS_BLOB_PATH = "movies/reservations.jsonl"


@app.mcp_tool()
@app.mcp_tool_property(arg_name="schedule_id", description="上映スケジュールID")
@app.mcp_tool_property(arg_name="reservation_seats", description='List of seat IDs to reserve (e.g., ["A1", "A2"])')
@app.mcp_tool_property(arg_name="reservation_pw", description="Reservation password (plaintext; hashed when stored)")
@app.mcp_tool_property(arg_name="customer_name", description="Customer name (optional)")
@app.blob_input(arg_name="seats_blob", connection="AzureWebJobsStorage", path=_SEAT_AVAILABILITY_BLOB_PATH)
@app.blob_output(arg_name="seats_out", connection="AzureWebJobsStorage", path=_SEAT_AVAILABILITY_BLOB_PATH)
@app.blob_output(arg_name="reservations_out", connection="AzureWebJobsStorage", path=_RESERVATIONS_BLOB_PATH)
def reserve_seats(
    seats_blob: func.InputStream,
    seats_out: func.Out[str],
    reservations_out: func.Out[str],
    schedule_id: str,
    reservation_seats: str,
    reservation_pw: str,
    customer_name: str = None,
) -> str:
    """指定した座席の予約を実行します。競合時はエラーを返却。"""
    def err(code: int, msg: str, data=None):
        body = {"error": {"code": code, "message": msg}}
        if data is not None:
            body["error"]["data"] = data
        return json.dumps(body)

    # 1. Input validation
    if not schedule_id or not isinstance(schedule_id, str):
        return err(-32602, "schedule_id is required")

    # reservation_seats arrives as JSON string from MCP; parse it
    if isinstance(reservation_seats, str):
        try:
            reservation_seats = json.loads(reservation_seats)
        except (json.JSONDecodeError, TypeError):
            return err(-32602, "reservation_seats must be a JSON array of seat IDs")

    if not isinstance(reservation_seats, list) or len(reservation_seats) == 0:
        return err(-32602, "reservation_seats must be a non-empty array of seat IDs")
    for sid in reservation_seats:
        if not isinstance(sid, str) or not sid:
            return err(-32602, "Each seat ID must be a non-empty string")

    if not reservation_pw or not isinstance(reservation_pw, str):
        return err(-32602, "reservation_pw is required")

    # 2. Load seat availability from Blob
    try:
        seat_data = json.loads(seats_blob.read().decode("utf-8")) if seats_blob else []
    except Exception:
        seat_data = []

    entry = None
    entry_idx = None
    for idx, item in enumerate(seat_data):
        if item.get("schedule_id") == schedule_id:
            entry = item
            entry_idx = idx
            break

    if entry is None:
        return err(-32602, f"Schedule not found: {schedule_id}")

    # Check seat availability and detect conflicts
    seats = entry.get("seats", [])
    seat_map = {s["seat_id"]: s for s in seats}
    conflicted = []
    for sid in reservation_seats:
        seat = seat_map.get(sid)
        if seat is None:
            conflicted.append(sid)
        elif seat.get("status") != "available":
            conflicted.append(sid)

    if conflicted:
        return err(409, "Seat conflict", {
            "conflicted_seats": conflicted,
            "message": f"Seats {', '.join(conflicted)} are not available",
        })

    # 3. Generate reservation record
    now = datetime.now(timezone.utc)
    reservation_id = "r" + now.strftime("%Y%m%d%H%M%S")
    pw_hash = hashlib.sha256(reservation_pw.encode("utf-8")).hexdigest()
    reservation_time = now.isoformat()

    record = {
        "reservation_id": reservation_id,
        "schedule_id": schedule_id,
        "reservation_seats": reservation_seats,
        "reservation_pw_hash": pw_hash,
        "customer_name": customer_name or "",
        "reservation_time": reservation_time,
        "status": "confirmed",
    }

    # 4. Update seat statuses
    for sid in reservation_seats:
        seat_map[sid]["status"] = "reserved"

    available_count = sum(1 for s in seats if s.get("status") == "available")
    reserved_count = sum(1 for s in seats if s.get("status") == "reserved")
    entry["available_count"] = available_count
    entry["reserved_count"] = reserved_count
    seat_data[entry_idx] = entry

    # Write updated seat_availability back to Blob
    seats_out.set(json.dumps(seat_data, ensure_ascii=False))

    # 5. Persist reservation to local file and Blob
    data_dir = Path(__file__).parent / "data"
    reservations_path = data_dir / "reservations.jsonl"
    record_line = json.dumps(record, ensure_ascii=False)
    with open(reservations_path, "a", encoding="utf-8") as f:
        f.write(record_line + "\n")

    # Write full reservations to Blob
    try:
        all_lines = reservations_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        all_lines = record_line + "\n"
    reservations_out.set(all_lines)

    # 6. Build response
    return json.dumps({
        "reservation_id": reservation_id,
        "reservation_pw_hash": pw_hash,
        "reservation_seats": reservation_seats,
        "reservation_time": reservation_time,
        "status": "confirmed",
    })


# ---------------------------------------------------------------------------
# Movie popularity tool implementation
# ---------------------------------------------------------------------------


@app.mcp_tool()
@app.mcp_tool_property(arg_name="date", description="Date to aggregate on (YYYY-MM-DD). Defaults to today.")
@app.mcp_tool_property(arg_name="top_n", description="Return top N items (omit for all).")
@app.blob_input(arg_name="reservations_blob", connection="AzureWebJobsStorage", path=_RESERVATIONS_BLOB_PATH)
@app.blob_input(arg_name="schedules_blob", connection="AzureWebJobsStorage", path=_SCHEDULES_BLOB_PATH)
@app.blob_input(arg_name="movies_blob", connection="AzureWebJobsStorage", path=_MOVIES_BLOB_PATH)
def get_movie_popularity(
    reservations_blob: func.InputStream,
    schedules_blob: func.InputStream,
    movies_blob: func.InputStream,
    date: str = None,
    top_n: int = None,
) -> str:
    """上映中映画の人気度ランキングを集計・算出して返却します。"""
    def err(code: int, msg: str):
        return json.dumps({"error": {"code": code, "message": msg}})

    # Normalize empty string to None
    if not date:
        date = None
    if isinstance(top_n, str):
        if not top_n:
            top_n = None
        else:
            try:
                top_n = int(top_n)
            except (ValueError, TypeError):
                return err(-32602, "top_n must be a positive integer")

    # 1. Input validation
    if date is not None:
        if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return err(-32602, "Invalid date format. Expected YYYY-MM-DD")
        target_date = date
    else:
        target_date = datetime.now().date().isoformat()

    if top_n is not None:
        if not isinstance(top_n, int) or top_n <= 0:
            return err(-32602, "top_n must be a positive integer")

    # 2. Load schedules and build schedule_id -> {movie_id, date} map
    try:
        schedules = json.loads(schedules_blob.read().decode("utf-8")) if schedules_blob else []
    except Exception:
        schedules = []

    schedule_map = {}  # schedule_id -> movie_id (only for target_date)
    for sch in schedules:
        if sch.get("date") == target_date:
            schedule_map[sch["schedule_id"]] = sch["movie_id"]

    # 3. Load reservations and accumulate booked seats per movie
    try:
        raw = reservations_blob.read().decode("utf-8") if reservations_blob else ""
    except Exception:
        raw = ""

    movie_seats: dict[str, int] = {}
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("status") != "confirmed":
            continue
        sid = rec.get("schedule_id", "")
        mid = schedule_map.get(sid)
        if mid is None:
            continue
        seats = rec.get("reservation_seats", [])
        movie_seats[mid] = movie_seats.get(mid, 0) + len(seats)

    # 4. Load movies for title lookup
    try:
        movies = json.loads(movies_blob.read().decode("utf-8")) if movies_blob else []
    except Exception:
        movies = []

    title_map = {m["movie_id"]: m.get("title", "") for m in movies}

    # 5. Build ranking
    ranking = [
        {"movie_id": mid, "title": title_map.get(mid, ""), "booked_seats_count": cnt}
        for mid, cnt in movie_seats.items()
    ]
    ranking.sort(key=lambda x: -x["booked_seats_count"])

    max_count = ranking[0]["booked_seats_count"] if ranking else 0
    for i, item in enumerate(ranking):
        item["popularity_rank"] = i + 1
        item["popularity_score"] = round(item["booked_seats_count"] / max_count * 100, 1) if max_count > 0 else 0.0

    # 6. Apply top_n limit
    if top_n is not None:
        ranking = ranking[:top_n]

    return json.dumps({"popularity_ranking": ranking})


# ---------------------------------------------------------------------------
# Reservation details tool implementation
# ---------------------------------------------------------------------------


@app.mcp_tool()
@app.mcp_tool_property(arg_name="reservation_id", description="予約ID")
@app.mcp_tool_property(arg_name="reservation_pw", description="Reservation password (plaintext)")
@app.blob_input(arg_name="reservations_blob", connection="AzureWebJobsStorage", path=_RESERVATIONS_BLOB_PATH)
@app.blob_input(arg_name="schedules_blob", connection="AzureWebJobsStorage", path=_SCHEDULES_BLOB_PATH)
@app.blob_input(arg_name="movies_blob", connection="AzureWebJobsStorage", path=_MOVIES_BLOB_PATH)
def get_reservation_details(
    reservations_blob: func.InputStream,
    schedules_blob: func.InputStream,
    movies_blob: func.InputStream,
    reservation_id: str,
    reservation_pw: str,
) -> str:
    """予約 ID とパスワードで予約詳細を取得します。パスワード検証必須。"""
    def err(code: int, msg: str, data=None):
        body = {"error": {"code": code, "message": msg}}
        if data is not None:
            body["error"]["data"] = data
        return json.dumps(body)

    # 1. Input validation
    if not reservation_id or not isinstance(reservation_id, str):
        return err(-32602, "reservation_id is required")
    if not reservation_pw or not isinstance(reservation_pw, str):
        return err(-32602, "reservation_pw is required")

    # 2. Load reservations from Blob
    try:
        raw = reservations_blob.read().decode("utf-8") if reservations_blob else ""
    except Exception:
        raw = ""

    record = None
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("reservation_id") == reservation_id:
            record = rec
            break

    # 3. Existence check
    if record is None:
        return err(404, "Reservation not found")

    # 4. Password verification
    pw_hash = hashlib.sha256(reservation_pw.encode("utf-8")).hexdigest()
    if pw_hash != record.get("reservation_pw_hash", ""):
        return err(403, "Forbidden", "Invalid reservation password")

    # 5. Enrich with movie and schedule info
    schedule_id = record.get("schedule_id", "")

    try:
        schedules = json.loads(schedules_blob.read().decode("utf-8")) if schedules_blob else []
    except Exception:
        schedules = []

    schedule_info = {}
    movie_id = ""
    for sch in schedules:
        if sch.get("schedule_id") == schedule_id:
            schedule_info = {
                "schedule_id": sch.get("schedule_id"),
                "date": sch.get("date"),
                "start_time": sch.get("start_time"),
                "theater_id": sch.get("theater_id"),
                "theater_name": sch.get("theater_name"),
            }
            movie_id = sch.get("movie_id", "")
            break

    try:
        movies = json.loads(movies_blob.read().decode("utf-8")) if movies_blob else []
    except Exception:
        movies = []

    movie_info = {"movie_id": movie_id, "title": ""}
    for m in movies:
        if m.get("movie_id") == movie_id:
            movie_info = {"movie_id": movie_id, "title": m.get("title", "")}
            break

    # 6. Build response
    return json.dumps({
        "reservation_id": record.get("reservation_id"),
        "movie": movie_info,
        "schedule": schedule_info,
        "reservation_seats": record.get("reservation_seats", []),
        "reservation_time": record.get("reservation_time", ""),
        "status": record.get("status", ""),
    })

