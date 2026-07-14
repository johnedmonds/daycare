import json
import logging
import requests
import re
from backend.config import CACHE_DIR, DAYCARE_PROGRAMS_URL, DAYCARE_INSPECTIONS_URL

DAYCARES_CACHE_PATH = CACHE_DIR / "daycares.json"
INSPECTIONS_CACHE_PATH = CACHE_DIR / "inspections.json"


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

def fetch_inspections(force_refresh=False):
    """
    Fetch all historical NYC child care inspections and cache them.
    Socrata API handles pagination using $limit and $offset.
    """
    if not force_refresh and INSPECTIONS_CACHE_PATH.exists():
        try:
            with open(INSPECTIONS_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading inspections cache: {e}. Re-fetching...")

    logger.info("Fetching child care inspections from NYC Open Data...")
    all_inspections = []
    limit = 1000
    offset = 0
    
    try:
        while True:
            logger.info(f"Fetching inspections offset={offset}...")
            response = requests.get(
                DAYCARE_INSPECTIONS_URL, 
                params={"$limit": limit, "$offset": offset},
                timeout=20
            )
            response.raise_for_status()
            batch = response.json()
            
            if not batch:
                break
                
            all_inspections.extend(batch)
            offset += limit
            
            # If we got fewer than limit, we've hit the end
            if len(batch) < limit:
                break
                
        # Save to cache
        with open(INSPECTIONS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(all_inspections, f, indent=2)
            
        logger.info(f"Successfully cached {len(all_inspections)} inspections.")
        return all_inspections
    except Exception as e:
        logger.error(f"Failed to fetch inspections: {e}")
        # Fallback to cached file if it exists
        if INSPECTIONS_CACHE_PATH.exists():
            with open(INSPECTIONS_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

def get_inspections_by_permit(force_refresh=False):
    """
    Build an in-memory index of inspections grouped by permitnumber.
    """
    inspections = fetch_inspections(force_refresh)
    indexed = {}
    for insp in inspections:
        permit = insp.get("permitnumber")
        if permit:
            permit_key = permit.strip().upper()
            if permit_key not in indexed:
                indexed[permit_key] = []
            indexed[permit_key].append(insp)
    return indexed

def enrich_daycare_with_inspections(daycare, inspections_by_permit):
    """
    Enrich daycare object with aggregated safety and inspection statistics.
    """
    permit = daycare.get("permit_number")
    if not permit:
        return
        
    permit_key = permit.strip().upper()
    facility_insps = inspections_by_permit.get(permit_key, [])
    
    # Sort inspections by date descending (newest first)
    def get_date(x):
        d = x.get("inspectiondate")
        return d if d else ""
    facility_insps.sort(key=get_date, reverse=True)
    
    # Aggregated metrics
    total_violations = 0
    critical_violations = 0
    general_violations = 0
    hazard_violations = 0
    
    corrected_violations = 0
    open_violations = 0
    
    unique_inspections = set()
    latest_inspection_date = None
    latest_inspection_result = None
    
    # Rates and staffing from the latest available records
    violation_rate = None
    avg_violation_rate = None
    critical_violation_rate = None
    avg_critical_violation_rate = None
    hazard_violation_rate = None
    avg_hazard_violation_rate = None
    
    staff_count = None
    avg_staff_count = None
    
    violations_list = []
    
    for insp in facility_insps:
        idate = insp.get("inspectiondate")
        iresult = insp.get("inspectionsummaryresult")
        
        if idate:
            unique_inspections.add(idate)
            if not latest_inspection_date:
                latest_inspection_date = idate
                latest_inspection_result = iresult
                
        # Get rates if not already set from a newer inspection
        if violation_rate is None and insp.get("violationratepercent") is not None:
            try:
                violation_rate = float(insp["violationratepercent"])
            except (ValueError, TypeError):
                pass
        if avg_violation_rate is None and insp.get("violationavgratepercent") is not None:
            try:
                avg_violation_rate = float(insp["violationavgratepercent"])
            except (ValueError, TypeError):
                pass
        if critical_violation_rate is None and insp.get("criticalviolationrate") is not None:
            try:
                critical_violation_rate = float(insp["criticalviolationrate"])
            except (ValueError, TypeError):
                pass
        if avg_critical_violation_rate is None and insp.get("avgcriticalviolationrate") is not None:
            try:
                avg_critical_violation_rate = float(insp["avgcriticalviolationrate"])
            except (ValueError, TypeError):
                pass
        if hazard_violation_rate is None and insp.get("publichealthhazardviolationrate") is not None:
            try:
                hazard_violation_rate = float(insp["publichealthhazardviolationrate"])
            except (ValueError, TypeError):
                pass
        if avg_hazard_violation_rate is None and insp.get("averagepublichealthhazardiolationrate") is not None:
            try:
                avg_hazard_violation_rate = float(insp["averagepublichealthhazardiolationrate"])
            except (ValueError, TypeError):
                pass
                
        # Staffing
        if staff_count is None and insp.get("totaleducationalworkers") is not None:
            try:
                staff_count = int(float(insp["totaleducationalworkers"]))
            except (ValueError, TypeError):
                pass
        if avg_staff_count is None and insp.get("averagetotaleducationalworkers") is not None:
            try:
                avg_staff_count = int(float(insp["averagetotaleducationalworkers"]))
            except (ValueError, TypeError):
                pass
                
        # If there's a violation category
        vcat = insp.get("violationcategory")
        if vcat and vcat != "None" and vcat.upper() != "NONE":
            total_violations += 1
            vcat_upper = vcat.upper()
            if "CRITICAL" in vcat_upper:
                critical_violations += 1
            elif "HAZARD" in vcat_upper or "PUBLIC" in vcat_upper:
                hazard_violations += 1
            else:
                general_violations += 1
                
            vstatus = insp.get("violationstatus")
            if vstatus:
                if vstatus.upper() == "CORRECTED":
                    corrected_violations += 1
                else:
                    open_violations += 1
                    
            violations_list.append({
                "date": idate,
                "category": vcat,
                "summary": insp.get("regulationsummary", "No detail provided"),
                "status": vstatus or "Unknown"
            })
            
    daycare["safety_metrics"] = {
        "total_inspections": len(unique_inspections),
        "latest_inspection_date": latest_inspection_date,
        "latest_inspection_result": latest_inspection_result,
        "total_violations": total_violations,
        "critical_violations": critical_violations,
        "general_violations": general_violations,
        "hazard_violations": hazard_violations,
        "corrected_violations": corrected_violations,
        "open_violations": open_violations,
        "rates": {
            "violation_rate": violation_rate,
            "avg_violation_rate": avg_violation_rate,
            "critical_rate": critical_violation_rate,
            "avg_critical_rate": avg_critical_violation_rate,
            "hazard_rate": hazard_violation_rate,
            "avg_hazard_rate": avg_hazard_violation_rate,
        },
        "staffing": {
            "total_workers": staff_count,
            "avg_workers": avg_staff_count
        },
        "violations": violations_list[:10]  # Top 10 most recent violations
    }

