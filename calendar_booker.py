# calendar_booker.py
import os
import datetime
import zoneinfo
from pathlib import Path
from typing import Dict, Any, List, Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import json

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
# Use environment variable or relative path for better portability
CLIENT_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", 
                       r"C:\Users\gatsi\Box\MY BREATHTAKING PROJECT\Voice Calendar AI\credentials.json")
TOKEN_PATH = Path.home() / ".voice-calendar-ai" / "token.json"
TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
CALENDAR_ID = "primary"
DEFAULT_TZ = "America/New_York"

def _ensure_rfc3339_with_tz(dt_str: str) -> str:
    """Convert datetime string to RFC3339 format with timezone"""
    if not dt_str:
        return dt_str
    
    # If it's already in proper RFC3339 format with timezone
    if ("T" in dt_str and 
        (dt_str.endswith("Z") or 
         "+" in dt_str.split("T")[1] or 
         "-" in dt_str.split("T")[1])):
        return dt_str
    
    try:
        # Handle date-only format (all-day events)
        if "T" not in dt_str:
            # This is a date-only string (YYYY-MM-DD)
            return dt_str  # Return as-is for all-day events
        
        # Handle datetime without timezone
        if "T" in dt_str and not any(x in dt_str for x in ["Z", "+", "-"]):
            # Parse as naive datetime and add timezone
            naive_dt = datetime.datetime.fromisoformat(dt_str)
            aware_dt = naive_dt.replace(tzinfo=zoneinfo.ZoneInfo(DEFAULT_TZ))
            return aware_dt.isoformat()
        
        # Handle other cases
        dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=zoneinfo.ZoneInfo(DEFAULT_TZ))
        return dt.isoformat()
        
    except (ValueError, AttributeError) as e:
        print(f"Warning: Could not parse date '{dt_str}': {e}")
        return dt_str  # Return as-is and let Google API handle validation

def get_service():
    """Get authenticated Google Calendar service"""
    creds = None
    
    # Load token if exists
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception as e:
            print(f"Error loading credentials: {e}")
            creds = None
    
    # Refresh or get new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing token: {e}")
                creds = None
        
        if not creds:
            try:
                if not os.path.exists(CLIENT_PATH):
                    raise FileNotFoundError(f"Credentials file not found: {CLIENT_PATH}")
                
                flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_PATH), SCOPES)
                creds = flow.run_local_server(port=8080, prompt="consent")
                
                # Save the credentials for next run
                TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            except Exception as e:
                print(f"Error during OAuth flow: {e}")
                raise
    
    return build("calendar", "v3", credentials=creds)

def create_event(event_body: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new calendar event"""
    try:
        service = get_service()
        
        # Validate and format datetime strings
        if "start" in event_body and "dateTime" in event_body["start"]:
            event_body["start"]["dateTime"] = _ensure_rfc3339_with_tz(event_body["start"]["dateTime"])
        
        if "end" in event_body and "dateTime" in event_body["end"]:
            event_body["end"]["dateTime"] = _ensure_rfc3339_with_tz(event_body["end"]["dateTime"])
        
        print(f"Creating event with body: {json.dumps(event_body, indent=2)}")
        
        event = service.events().insert(
            calendarId=CALENDAR_ID, 
            body=event_body, 
            sendUpdates="all"
        ).execute()
        
        print(f"Event created: {event.get('htmlLink')}")
        return event
        
    except Exception as e:
        print(f"Error creating event: {e}")
        raise

def query_conflicts(start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
    """Query for conflicting events in the given time range"""
    try:
        service = get_service()
        start_iso = _ensure_rfc3339_with_tz(start_iso)
        end_iso = _ensure_rfc3339_with_tz(end_iso)
        
        resp = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_iso,
            timeMax=end_iso,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        
        return resp.get("items", [])
        
    except Exception as e:
        print(f"Error querying conflicts: {e}")
        return []

def _find_event_by_title(service, title: str) -> Optional[Dict[str, Any]]:
    """Find event by title (case-insensitive partial match)"""
    try:
        resp = service.events().list(calendarId=CALENDAR_ID, q=title).execute()
        for ev in resp.get("items", []):
            if ev.get("summary", "").lower() == title.lower():
                return ev
        return None
    except Exception as e:
        print(f"Error finding event by title: {e}")
        return None

def move_event(criteria: Dict[str, Any], new_start: str, new_end: str) -> Dict[str, Any]:
    """Move an existing event to new time"""
    try:
        service = get_service()
        ev = _find_event_by_title(service, criteria["title"])
        if not ev:
            raise ValueError(f"Event '{criteria['title']}' not found")
        
        patch = {
            "start": {"dateTime": _ensure_rfc3339_with_tz(new_start), "timeZone": DEFAULT_TZ},
            "end": {"dateTime": _ensure_rfc3339_with_tz(new_end), "timeZone": DEFAULT_TZ}
        }
        
        return service.events().patch(
            calendarId=CALENDAR_ID,
            eventId=ev["id"],
            body=patch,
            sendUpdates="all"
        ).execute()
        
    except Exception as e:
        print(f"Error moving event: {e}")
        raise

def cancel_event(criteria: Dict[str, Any]) -> Dict[str, Any]:
    """Cancel an existing event"""
    try:
        service = get_service()
        ev = _find_event_by_title(service, criteria["title"])
        if not ev:
            raise ValueError(f"Event '{criteria['title']}' not found")
        
        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=ev["id"],
            sendUpdates="all"
        ).execute()
        
        return {"id": ev["id"], "status": "cancelled"}
        
    except Exception as e:
        print(f"Error canceling event: {e}")
        raise