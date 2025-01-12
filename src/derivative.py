import os
from data.data_manager import DataManager
from optimizer.optimizer import Optimizer
from lineups.lineups import Lineups
from lineups.lineup_metrics import calculate_exposure
from optimizer.late_swaptimizer import LateSwaptimizer
import pandas as pd

### Entry point of the application

def main():
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)
    # Initialize DataManager for the desired site (e.g., 'dk')
    site = "dk"  # Or "fd" depending on the use case
    process = 'main'


    data_manager = DataManager(site)

    # Load player data
    try:
        data_manager.load_player_data()
        print("Player data loaded successfully.")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    # Filter out invalid players and capture removed players
    removed_players = [
        player for player in data_manager.players
        if player.id in [0, None]
    ]
    print("Players removed before optimizer initialization:")
    for player in removed_players:
        print(f"Name: {player.name}, Ownership: {player.ownership}, ID: {player.id}")

    players = [
        player for player in data_manager.players
        if player.fpts > data_manager.config.get("projection_minimum")
    ]

    num_lineups = 1
    num_uniques = 1

    optimizer = Optimizer(site, players, num_lineups, num_uniques, data_manager.config)

    optimizer.explore_fpts_ownership_tradeoff(min_ratio=0.95, max_ratio=1, steps=250)


if __name__ == "__main__":
    main()

