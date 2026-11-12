"""
sro_registry_data.py - Master SRO Directory for Tamil Nadu (TNREGINET Official)
=================================================================================
Maps Registration Districts -> Sub-Registrar Offices (SROs) with official TNREGINET IDs,
Zones, and District Codes for Autonomous EC Sweeping (1975–2026).
Loads all 638 official SROs across 56 districts from tnreginet_official_sro_master.json.
"""

import os
import sys
import json
import re

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MASTER_JSON_PATH = os.path.join(CURRENT_DIR, "tnreginet_official_sro_master.json")

# Fallback basic directory if JSON is not present
DISTRICT_ZONE_MAP = {
    "Trichy (திருச்சிராப்பள்ளி)": {"zone_id": "6", "district_id": "20034"},
    "Madurai North (மதுரை வடக்கு)": {"zone_id": "4", "district_id": "20018"},
    "Madurai South (மதுரை தெற்கு)": {"zone_id": "4", "district_id": "20017"},
    "Chennai South (சென்னை தெற்கு)": {"zone_id": "1", "district_id": "20001"},
    "Chennai Central (சென்னை மத்தி)": {"zone_id": "1", "district_id": "20003"},
    "Chennai North (சென்னை வடக்கு)": {"zone_id": "1", "district_id": "20002"},
    "Coimbatore North (கோயம்புத்தூர் வடக்கு)": {"zone_id": "2", "district_id": "20006"},
    "Coimbatore South (கோயம்புத்தூர் தெற்கு)": {"zone_id": "2", "district_id": "50006"},
    "Salem East (சேலம் கிழக்கு)": {"zone_id": "5", "district_id": "20029"},
    "Salem West (சேலம் மேற்கு)": {"zone_id": "5", "district_id": "20030"},
    "Chengalpattu (செங்கல்பட்டு)": {"zone_id": "15", "district_id": "20004"},
    "Tambaram (தாம்பரம்)": {"zone_id": "15", "district_id": "50007"}
}

DISTRICT_SRO_DIRECTORY = {}

# Load all 638 official SROs from harvested TNREGINET master JSON
if os.path.exists(MASTER_JSON_PATH):
    try:
        with open(MASTER_JSON_PATH, "r", encoding="utf-8") as f:
            raw_master = json.load(f)
            for dist_label, sro_list in raw_master.items():
                DISTRICT_SRO_DIRECTORY[dist_label] = []
                for s in sro_list:
                    s_id = s.get("id", "")
                    s_name = s.get("name", "")
                    z_id = s.get("zone_id", "6")
                    d_id = s.get("district_id", "20034")
                    DISTRICT_SRO_DIRECTORY[dist_label].append({
                        "id": s_id,
                        "name": s_name,
                        "code": s_id.split(':')[0] if ':' in s_id else s_id,
                        "zone_id": z_id,
                        "district_id": d_id
                    })
                    if dist_label not in DISTRICT_ZONE_MAP:
                        DISTRICT_ZONE_MAP[dist_label] = {"zone_id": z_id, "district_id": d_id}
    except Exception as e:
        print(f"[!] Warning loading official SRO master: {e}")

# Helper Functions
def get_districts():
    return list(DISTRICT_SRO_DIRECTORY.keys())

def get_sros_for_district(district_name: str):
    if district_name in DISTRICT_SRO_DIRECTORY:
        return DISTRICT_SRO_DIRECTORY[district_name]
    # Check partial match
    clean_d = district_name.lower().split('(')[0].strip()
    for d, sros in DISTRICT_SRO_DIRECTORY.items():
        if clean_d in d.lower():
            return sros
    return []

def get_district_metadata(district_name: str):
    if district_name in DISTRICT_ZONE_MAP:
        return DISTRICT_ZONE_MAP[district_name]
    clean_d = district_name.lower().split('(')[0].strip()
    for d, meta in DISTRICT_ZONE_MAP.items():
        if clean_d in d.lower():
            return meta
    return {"zone_id": "6", "district_id": "20034"}

def find_sro_by_id(sro_id: str):
    for dist, sros in DISTRICT_SRO_DIRECTORY.items():
        for sro in sros:
            if sro["id"] == sro_id or sro["code"] == sro_id:
                return {**sro, "district": dist}
    return None

def resolve_sro_details(sro_name: str, district_name: str = "", sro_id: str = ""):
    """
    Resolves SRO record, id, zone_id, and district_id from any partial input.
    Matches against all 638 official TNREGINET SROs.
    """
    # 1. Exact match by id if provided and valid
    if sro_id:
        found = find_sro_by_id(sro_id)
        if found:
            return found

    # 2. Match by SRO name across all districts
    sro_name_clean = re.sub(r'[^a-zA-Z0-9]+', '', sro_name.lower().split('(')[0].strip())
    
    # Priority match within same district if specified
    if district_name:
        for sro in get_sros_for_district(district_name):
            base_clean = re.sub(r'[^a-zA-Z0-9]+', '', sro["name"].lower().split('(')[0].strip())
            if sro_name_clean == base_clean or sro_name_clean in base_clean or base_clean in sro_name_clean:
                return {**sro, "district": district_name}

    # Global match across all SROs
    for dist, sros in DISTRICT_SRO_DIRECTORY.items():
        for sro in sros:
            base_clean = re.sub(r'[^a-zA-Z0-9]+', '', sro["name"].lower().split('(')[0].strip())
            if sro_name_clean == base_clean or sro_name_clean in base_clean or base_clean in sro_name_clean:
                return {**sro, "district": dist}

    # 3. Default fallback if not found
    dist_meta = get_district_metadata(district_name)
    return {
        "id": sro_id or "20445:1",
        "name": sro_name or "Trichy Joint 1",
        "code": sro_id.split(':')[0] if ':' in sro_id else "20445",
        "zone_id": dist_meta.get("zone_id", "6"),
        "district_id": dist_meta.get("district_id", "20034"),
        "district": district_name or "Trichy"
    }
