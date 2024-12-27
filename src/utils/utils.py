from datetime import datetime, timedelta
import pytz

def parse_game_time(game_info, timezone="US/Eastern", lock_offset_hours=0):
    """
    Parse game time from the Game Info string and adjust it to include a lock offset.
    
    :param game_info: String containing game info (e.g., "GB@PHI 09/06/2024 08:15PM ET").
    :param timezone: Timezone of the game times (default: US/Eastern).
    :param lock_offset_hours: Number of hours to subtract for lock time.
    :return: Timezone-aware datetime object adjusted for lock time.
    """
    try:
        eastern = pytz.timezone(timezone)
        date_part, time_part, _ = game_info.split()[-3:]
        gametime = datetime.strptime(f"{date_part} {time_part}", "%m/%d/%Y %I:%M%p")
        gametime = eastern.localize(gametime)
        lock_time = gametime - timedelta(hours=lock_offset_hours)
        return lock_time
    except Exception as e:
        raise ValueError(f"Error parsing game info '{game_info}': {e}")
