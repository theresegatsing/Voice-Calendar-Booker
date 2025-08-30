# voice_calendar_orchestrator.py (updated)
import os
import importlib
import json
import requests
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

CONFIG = {
    "NLU_URL": "http://localhost:8000/extract",
    "ASR_MODULE": "stt_live",
    "ASR_FUNC": "transcribe_once",
    "GCAL_CREATE_MODULE": "calendar_booker",
    "GCAL_CREATE_FUNC": "create_event",
    "GCAL_MOVE_MODULE": "calendar_booker",
    "GCAL_MOVE_FUNC": "move_event",
    "GCAL_CANCEL_MODULE": "calendar_booker",
    "GCAL_CANCEL_FUNC": "cancel_event",
    "GCAL_CONFLICTS_MODULE": "calendar_booker",
    "GCAL_CONFLICTS_FUNC": "query_conflicts",
    "USER_TZ": "America/New_York",
}

def _load_callable(module_name: str, func_name: str):
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, func_name)
    except Exception as e:
        print(f"[warn] load failed {module_name}.{func_name}: {e}")
        return None

def asr_transcribe_once() -> str:
    fn = _load_callable(CONFIG["ASR_MODULE"], CONFIG["ASR_FUNC"])
    return fn() if fn else input("🧑 Type command: ")

def nlu_extract_http(utterance: str) -> Dict[str, Any]:
    try:
        r = requests.post(CONFIG["NLU_URL"], json={"utterance": utterance}, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[error] NLU failed: {e}")
        return {"intent":"CreateEvent","title":"Meeting","duration_minutes":30,"timezone":CONFIG["USER_TZ"]}

def gcal_create(body: Dict[str, Any]) -> Dict[str, Any]:
    func = _load_callable(CONFIG["GCAL_CREATE_MODULE"], CONFIG["GCAL_CREATE_FUNC"])
    return func(body) if func else {"error": "Calendar function not available"}

def gcal_conflicts(start: str, end: str) -> List[Dict[str, Any]]:
    func = _load_callable(CONFIG["GCAL_CONFLICTS_MODULE"], CONFIG["GCAL_CONFLICTS_FUNC"])
    return func(start, end) if func else []

def compute_end(start_iso: str, dur: int) -> str:
    try:
        dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
        return (dt + timedelta(minutes=dur)).isoformat()
    except ValueError:
        # If it's a date without time, add time component
        dt = datetime.fromisoformat(start_iso.split('T')[0])
        return (dt + timedelta(minutes=dur)).isoformat()

def to_gcal_event(nlu: Dict[str, Any], start: str, end: str) -> Dict[str, Any]:
    tz = nlu.get("timezone", CONFIG["USER_TZ"])
    
    # Check if this is an all-day event (no time component)
    is_all_day = start and end and "T" not in start and "T" not in end
    
    if is_all_day:
        # All-day event - use date format
        ev = {
            "summary": nlu.get("title") or "(No title)",
            "start": {"date": start.split('T')[0] if 'T' in start else start},
            "end": {"date": end.split('T')[0] if 'T' in end else end},
        }
    else:
        # Timed event - use dateTime format
        ev = {
            "summary": nlu.get("title") or "(No title)",
            "start": {"dateTime": start, "timeZone": tz},
            "end": {"dateTime": end, "timeZone": tz},
        }
    
    # Add attendees if present
    attendees = nlu.get("attendees", [])
    if attendees and isinstance(attendees, list):
        ev["attendees"] = [{"email": email} for email in attendees if isinstance(email, str)]
    
    return ev

def handle_once():
    print("🎤 Listening for voice command...")
    utterance = asr_transcribe_once()
    print(f"🗣️  Heard: {utterance}")
    
    nlu = nlu_extract_http(utterance)
    intent = nlu.get("intent", "Unknown")
    print(f"🎯 Extracted intent: {intent}")
    print(f"📋 NLU data: {json.dumps(nlu, indent=2)}")
    
    if intent == "CreateEvent":
        start, end, dur = nlu.get("start"), nlu.get("end"), nlu.get("duration_minutes")
        print(f"⏰ Start: {start}, End: {end}, Duration: {dur}")
        
        # Calculate end time if not provided but duration is
        if not end and start and dur:
            try:
                end = compute_end(start, dur)
                print(f"📅 Computed end time: {end}")
            except Exception as e:
                print(f"❌ Error computing end time: {e}")
                return
        
        if not start or not end:
            print("❌ Missing start or end time - cannot create event")
            return
        
        payload = to_gcal_event(nlu, start, end)
        print(f"📨 Payload to Google Calendar: {json.dumps(payload, indent=2)}")
        
        # Check for conflicts
        try:
            conflicts = gcal_conflicts(start, end)
            if conflicts:
                print("⚠️  Conflict found with existing events:")
                for conflict in conflicts:
                    print(f"   - {conflict.get('summary', 'Unnamed event')} "
                          f"({conflict.get('start', {}).get('dateTime', conflict.get('start', {}).get('date', 'Unknown'))})")
        except Exception as e:
            print(f"⚠️  Could not check for conflicts: {e}")
        
        # Create the event
        try:
            created = gcal_create(payload)
            if "error" in created:
                print(f"❌ Failed to create event: {created['error']}")
            else:
                print("✅ Event created successfully!")
                if "htmlLink" in created:
                    print(f"🔗 View event: {created['htmlLink']}")
        except Exception as e:
            print(f"❌ Failed to create event: {e}")
    
    elif intent == "MoveEvent":
        print("➡️  Move event intent detected (not implemented)")
    
    elif intent == "CancelEvent":
        print("❌ Cancel event intent detected (not implemented)")
    
    else:
        print(f"🤷 Unhandled intent: {intent}")

if __name__ == "__main__":
    handle_once()