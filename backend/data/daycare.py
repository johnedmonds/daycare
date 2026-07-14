import json
import logging
import requests
import re
from backend.config import CACHE_DIR, DAYCARE_PROGRAMS_URL

DAYCARES_CACHE_PATH = CACHE_DIR / "daycares.json"

logger = logging.getLogger(__name__)

def fetch_daycares(force_refresh=False):
    """
    Fetch all active NYC child care programs and cache them.
    Socrata API handles pagination using $limit and $offset.
    """
    if not force_refresh and DAYCARES_CACHE_PATH.exists():
        try:
            with open(DAYCARES_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading daycares cache: {e}. Re-fetching...")

    logger.info("Fetching daycare facilities from NYC Open Data...")
    all_daycares = []
    limit = 1000
    offset = 0
    
    try:
        while True:
            logger.info(f"Fetching daycares offset={offset}...")
            # SODA API pagination
            response = requests.get(
                DAYCARE_PROGRAMS_URL, 
                params={"$limit": limit, "$offset": offset},
                timeout=20
            )
            response.raise_for_status()
            batch = response.json()
            
            if not batch:
                break
                
            for item in batch:
                # Clean coordinates
                if "latitude" in item:
                    try:
                        item["latitude"] = float(item["latitude"])
                    except (ValueError, TypeError):
                        item["latitude"] = None
                if "longitude" in item:
                    try:
                        item["longitude"] = float(item["longitude"])
                    except (ValueError, TypeError):
                        item["longitude"] = None
                
                # Check for capacity
                if "capacity" in item:
                    try:
                        item["capacity"] = int(item["capacity"])
                    except (ValueError, TypeError):
                        item["capacity"] = 0
                        
            all_daycares.extend(batch)
            offset += limit
            
            # If we got fewer than limit, we've hit the end
            if len(batch) < limit:
                break
                
        # Save to cache
        with open(DAYCARES_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(all_daycares, f, indent=2)
            
        logger.info(f"Successfully cached {len(all_daycares)} daycare programs.")
        return all_daycares
    except Exception as e:
        logger.error(f"Failed to fetch daycare programs: {e}")
        # Fallback to cached file if it exists
        if DAYCARES_CACHE_PATH.exists():
            with open(DAYCARES_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

def accepts_infants(age_range_str: str) -> bool:
    """
    Check if the daycare accepts infants/toddlers under 2 years old.
    Examples:
    - '0 YEARS - 2 YEARS' -> True
    - '3 MONTHS - 5 YEARS' -> True
    - '2 YEARS - 5 YEARS' -> False
    - '3 YEARS - 5 YEARS' -> False
    - 'NO DATA' -> False
    """
    if not age_range_str:
        return False
        
    age_range_str = age_range_str.upper().strip()
    if "NO DATA" in age_range_str:
        return False
        
    # Standard format contains: '0 YEARS', '1 YEAR', 'MONTH', 'WEEK'
    if "0 YEARS" in age_range_str or "1 YEAR" in age_range_str or "MONTH" in age_range_str or "WEEK" in age_range_str:
        # Check starting number to prevent false positives (like '2 YEARS')
        match = re.search(r'(\d+)\s*(YEAR|MONTH|WEEK)', age_range_str)
        if match:
            val = int(match.group(1))
            unit = match.group(2)
            if unit == "YEAR" and val <= 1:
                return True
            if unit in ("MONTH", "WEEK"):
                return True
        else:
            # Fallback if no match but '0' exists
            if "0" in age_range_str:
                return True
                
    return False

def filter_daycares(daycares, accepts_infants_only=False):
    """
    Filter daycares by location (must have coordinates) and optional age filter.
    """
    filtered = []
    for d in daycares:
        if d.get("latitude") is None or d.get("longitude") is None:
            continue
            
        if accepts_infants_only:
            age_range = d.get("age_range", "")
            if not accepts_infants(age_range):
                continue
                
        filtered.append(d)
    return filtered
