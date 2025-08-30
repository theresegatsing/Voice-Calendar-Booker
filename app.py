# app.py (complete working version with proper date parsing)
import os
import json
import logging
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Dict, Any
from datetime import datetime, timedelta
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Ollama settings
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

class EventRequest(BaseModel):
    utterance: str

class EventResponse(BaseModel):
    intent: str
    title: str = None
    start: str = None
    end: str = None
    duration_minutes: int = None
    attendees: list = None
    timezone: str = None

def validate_and_correct_dates(event_data: Dict[str, Any], utterance: str = "") -> Dict[str, Any]:
    """Validate and correct date formats with proper specific date handling"""
    utterance_lower = utterance.lower()
    
    # Check if we mentioned a specific month that should override any existing date
    month_patterns = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    for month_name, month_num in month_patterns.items():
        if month_name in utterance_lower:
            day_match = re.search(rf"{month_name}\s+(\d{{1,2}})(?:st|nd|rd|th)?", utterance_lower)
            if day_match:
                day_num = int(day_match.group(1))
                current_year = datetime.now().year
                
                try:
                    corrected_date = datetime(current_year, month_num, day_num)
                    
                    # If we have a time in the existing start date, preserve it
                    if "start" in event_data and event_data["start"]:
                        start_str = event_data["start"]
                        time_match = re.search(r"T(\d{2}:\d{2}:\d{2})", start_str)
                        if time_match:
                            time_part = time_match.group(1)
                            event_data["start"] = f"{corrected_date.strftime('%Y-%m-%d')}T{time_part}"
                            
                            # Also update end date if it exists
                            if "end" in event_data and event_data["end"]:
                                end_str = event_data["end"]
                                end_time_match = re.search(r"T(\d{2}:\d{2}:\d{2})", end_str)
                                if end_time_match:
                                    event_data["end"] = f"{corrected_date.strftime('%Y-%m-%d')}T{end_time_match.group(1)}"
                    
                    logger.info(f"Corrected to specific date: {corrected_date.strftime('%Y-%m-%d')}")
                    break
                    
                except ValueError:
                    continue
    
    # Original date correction logic for next day, tomorrow, etc.
    if "start" not in event_data:
        return event_data
    
    try:
        start_str = event_data.get("start", "")
        current_year = datetime.now().year
        
        # Check if date is wrong (not current year)
        if start_str and str(current_year) not in start_str:
            time_match = re.search(r"T(\d{2}:\d{2}:\d{2})", start_str)
            if time_match:
                time_part = time_match.group(1)
                
                today = datetime.now()
                corrected_date = today
                
                # Handle "next [day]" patterns
                day_mapping = {
                    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                    'friday': 4, 'saturday': 5, 'sunday': 6
                }
                
                next_day_match = re.search(r"next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", utterance_lower)
                if next_day_match:
                    day_name = next_day_match.group(1)
                    target_weekday = day_mapping[day_name]
                    current_weekday = today.weekday()
                    
                    days_until_next = (target_weekday - current_weekday) % 7
                    if days_until_next <= 0:
                        days_until_next += 7
                    
                    corrected_date = today + timedelta(days=days_until_next)
                    logger.info(f"Corrected 'next {day_name}': {corrected_date.strftime('%Y-%m-%d')}")
                
                # Handle "tomorrow"
                elif "tomorrow" in utterance_lower:
                    corrected_date = today + timedelta(days=1)
                    logger.info(f"Corrected 'tomorrow': {corrected_date.strftime('%Y-%m-%d')}")
                
                # Handle specific dates (September 6th)
                else:
                    date_found = False
                    for month_name, month_num in month_patterns.items():
                        if month_name in utterance_lower:
                            day_match = re.search(rf"{month_name}\s+(\d{{1,2}})(?:st|nd|rd|th)?", utterance_lower)
                            if day_match:
                                day_num = int(day_match.group(1))
                                corrected_date = datetime(current_year, month_num, day_num)
                                logger.info(f"Corrected specific date: {corrected_date.strftime('%Y-%m-%d')}")
                                date_found = True
                                break
                    
                    if not date_found:
                        corrected_date = today + timedelta(days=1)
                        logger.info(f"Default correction to tomorrow: {corrected_date.strftime('%Y-%m-%d')}")
                
                # Apply corrected date
                corrected_start = f"{corrected_date.strftime('%Y-%m-%d')}T{time_part}"
                event_data["start"] = corrected_start
                
                # Correct end time too
                if "end" in event_data:
                    end_str = event_data["end"]
                    end_time_match = re.search(r"T(\d{2}:\d{2}:\d{2})", end_str)
                    if end_time_match:
                        end_time_part = end_time_match.group(1)
                        event_data["end"] = f"{corrected_date.strftime('%Y-%m-%d')}T{end_time_part}"
    
    except Exception as e:
        logger.error(f"Date correction failed: {e}")
    
    return event_data

def extract_event_fallback(utterance: str) -> Dict[str, Any]:
    """Improved fallback function with proper date parsing for specific dates"""
    utterance_lower = utterance.lower()
    result = {"intent": "CreateEvent", "title": "Meeting", "timezone": "America/New_York"}
    
    today = datetime.now()
    current_year = today.year
    
    # Handle specific dates like "September 18th"
    month_patterns = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    event_date = None
    date_found = False
    
    # Parse specific month-day patterns
    for month_name, month_num in month_patterns.items():
        if month_name in utterance_lower:
            # Match patterns like "September 18th", "September 18", "september 18th at"
            day_match = re.search(rf"{month_name}\s+(\d{{1,2}})(?:st|nd|rd|th)?", utterance_lower)
            if day_match:
                day_num = int(day_match.group(1))
                try:
                    event_date = datetime(current_year, month_num, day_num)
                    result["title"] = f"Meeting on {month_name.title()} {day_num}"
                    date_found = True
                    logger.info(f"Parsed specific date: {event_date.strftime('%Y-%m-%d')}")
                    break
                except ValueError:
                    # Invalid date (e.g., February 30)
                    continue
    
    # Handle "next [day]" patterns if no specific date found
    if not date_found:
        day_mapping = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        next_day_match = re.search(r"next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", utterance_lower)
        
        if next_day_match:
            day_name = next_day_match.group(1)
            target_weekday = day_mapping[day_name]
            current_weekday = today.weekday()
            
            days_until_next = (target_weekday - current_weekday) % 7
            if days_until_next <= 0:
                days_until_next += 7
            
            event_date = today + timedelta(days=days_until_next)
            result["title"] = f"{day_name.title()} Meeting"
            
        elif "tomorrow" in utterance_lower:
            event_date = today + timedelta(days=1)
            
        else:
            # Default to today if no date specified
            event_date = today
    
    # Parse time with better pattern matching
    time_match = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(a\.m\.|p\.m\.|am|pm|a\.m|p\.m)?", utterance_lower, re.IGNORECASE)
    if time_match and event_date:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or "0")
        period = (time_match.group(3) or "").lower().replace('.', '')
        
        # Convert to 24-hour format
        if any(p in period for p in ['pm', 'p.m']):
            if hour < 12:
                hour += 12
        elif any(p in period for p in ['am', 'a.m']) and hour == 12:
            hour = 0
        
        # Handle 12-hour format without AM/PM (assume PM if ambiguous)
        if not period and hour < 8:
            hour += 12  # Assume evening for hours 1-7 without AM/PM
        
        try:
            start_time = event_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            result["start"] = start_time.isoformat()
            
            # Set default duration of 1 hour if not specified
            default_duration = 60
            result["end"] = (start_time + timedelta(minutes=default_duration)).isoformat()
            result["duration_minutes"] = default_duration
        except ValueError as e:
            logger.error(f"Invalid time: {e}")
    
    # Parse duration more accurately
    duration_match = re.search(r"for\s+(\d+)\s*(hour|hr|minute|min|minutes|hrs|hours)", utterance_lower)
    if duration_match and "start" in result:
        duration = int(duration_match.group(1))
        unit = duration_match.group(2).lower()
        
        try:
            start_time = datetime.fromisoformat(result["start"].replace('Z', '+00:00'))
            
            if any(u in unit for u in ['hour', 'hr']):
                result["end"] = (start_time + timedelta(hours=duration)).isoformat()
                result["duration_minutes"] = duration * 60
            else:
                result["end"] = (start_time + timedelta(minutes=duration)).isoformat()
                result["duration_minutes"] = duration
        except Exception as e:
            logger.error(f"Error calculating end time: {e}")
    
    # Parse title from utterance (first few meaningful words)
    words = [word for word in utterance.split() if word.lower() not in ['schedule', 'a', 'meeting', 'with', 'on', 'at', 'for']]
    if len(words) > 0:
        result["title"] = " ".join(words[:4])  # Use first 4 meaningful words as title
    
    # Parse attendees
    email_matches = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', utterance)
    if email_matches:
        result["attendees"] = email_matches
    
    return result

def extract_event(utterance: str) -> Dict[str, Any]:
    """
    Main extraction function with AI and fallback
    """
    try:
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        system_prompt = f"""You are a calendar assistant. Today is {current_date}. 
        Return JSON with: intent, title, start, end, duration_minutes, attendees.
        Use CURRENT REAL DATES, not old dates!"""
        
        response = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": f"Extract calendar event from: {utterance}. Today is {current_date}. Return JSON:",
                "system": system_prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1}
            },
            timeout=10
        )
        
        result = response.json()
        event_data = json.loads(result["response"])
        
        # Validate and correct dates with utterance context
        return validate_and_correct_dates(event_data, utterance)
        
    except Exception as e:
        logger.error(f"Ollama extraction failed: {e}")
        return extract_event_fallback(utterance)

@app.get("/")
async def root():
    return {"message": "Calendar NLU API is running!"}

@app.get("/health")
async def health_check():
    """Check if Ollama is available"""
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        return {
            "status": "healthy" if response.status_code == 200 else "degraded",
            "ollama_available": response.status_code == 200,
            "model_loaded": OLLAMA_MODEL in response.text if response.status_code == 200 else False
        }
    except:
        return {"status": "unhealthy", "ollama_available": False}

@app.post("/extract", response_model=EventResponse)
async def extract_event_endpoint(request: EventRequest):
    result = extract_event(request.utterance)
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)