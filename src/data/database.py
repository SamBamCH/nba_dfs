import sqlite3
from datetime import datetime

DB_PATH = "C:/Users/samba/nba_dfs/data/dfs_data.db"

def initialize_database():
    """Initialize the database (creates it if it doesn't exist)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create the players table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT,
            name TEXT,
            team TEXT,
            position TEXT,
            salary REAL,
            fpts REAL,
            minutes REAL,
            ceiling REAL,
            stddev REAL,
            ownership REAL,
            boom REAL,
            bust REAL,
            last_update TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

import json  # For serializing the position field

def write_players_to_database(players):
    """Write player objects to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    timestamp = datetime.now().isoformat()
    
    for player in players:
        # Serialize the position field as JSON
        position_json = json.dumps(player.position)
        
        cursor.execute("""
            INSERT INTO players (
                player_id, name, team, position, salary, fpts, minutes, ceiling, stddev, ownership, boom, bust, last_update
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            player.id,
            player.name,
            player.team,
            position_json,  # Store serialized JSON
            player.salary,
            player.fpts,
            player.minutes,
            player.ceiling,
            player.stddev,
            player.ownership,
            player.boom_pct,
            player.bust_pct,
            timestamp
        ))
    
    conn.commit()
    conn.close()
