import yaml
import json
from typing import List, Dict, Any
from datetime import datetime


def load_yaml(file_path: str) -> Dict:
    """Load YAML configuration file."""
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)


def load_json(file_path: str) -> List[Dict]:
    """Load JSON configuration file."""
    with open(file_path, 'r') as file:
        return json.load(file)


def get_station_type_by_code(code: str, station_types: Dict) -> Dict:
    """Find station type configuration by its code."""
    for station_type in station_types.values():
        if station_type['code'] == code:
            return station_type
    raise ValueError(f"No station type found for code: {code}")


def generate_locker_configs(stations: List[Dict], station_types: Dict) -> List[Dict]:
    """Generate locker configurations based on station types."""
    lockers = []

    for station in stations:
        station_type = get_station_type_by_code(
            station['station_type'], station_types)
        layout = station_type['locker_layout']

        # Generate lockers based on layout
        locker_index = 1
        for row_idx, row in enumerate(layout['layout'], 1):
            for col_idx, locker_type in enumerate(row, 1):
                locker = {
                    "station": {
                        "$ref": "stations",
                        "$callsign": station['callsign'],
                        "$db": "lockeroo"
                    },
                    "callsign": f"{station['callsign']}#{locker_index:03d}",
                    "station_index": locker_index,
                    "position": [row_idx, col_idx],
                    "locker_type": locker_type,
                    "pricing_model": f"storage-{locker_type}",
                    "availability": "operational",
                    "locker_state": "locked",
                    "charger_installed": True,
                    "charger_available": True,
                    "last_service_at": station['last_service_date'],
                    "total_session_count": 0,
                    "total_session_duration": 0
                }
                lockers.append(locker)
                locker_index += 1

    return lockers


def save_json(data: List[Dict], file_path: str):
    """Save data as JSON file."""
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=2)


def main():
    # Load configuration files
    station_types = load_yaml('src/config/station_types.yml')
    stations = load_json('static/database/base_data/stations.json')

    # Generate locker configurations
    lockers = generate_locker_configs(stations, station_types)

    # Save generated configurations
    save_json(lockers, 'static/database/base_data/lockers_gen.json')


if __name__ == "__main__":
    main()
