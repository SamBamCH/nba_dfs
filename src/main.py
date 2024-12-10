import os
from data.data_manager import DataManager
from optimizer.optimizer import Optimizer
from lineups.lineups import Lineups
from lineups.lineup_metrics import calculate_exposure


def main():
    # Initialize DataManager for the desired site (e.g., 'dk')
    site = "dk"  # Or "fd" depending on the use case
    data_manager = DataManager(site)

    # Load player data
    try:
        data_manager.load_player_data()
        print("Player data loaded successfully.")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return
    
    # Retrieve the players and config
    players = data_manager.players

    data_manager.players = [player for player in players if not (player.ownership in [0, None] and player.id in [0, None])]

    # Initialize the optimizer
    num_lineups = 150  # Example number of lineups
    num_uniques = 3   # Example minimum number of unique players between lineups
    optimizer = Optimizer(site, data_manager.players, num_lineups, num_uniques, data_manager.config)

    lineups = optimizer.run()

    exposure_df = calculate_exposure(lineups.lineups, players)

# Display the sorted DataFrame
    print(exposure_df)
    lineups.export_to_csv("data/output/optimal_lineups.csv", site=optimizer.site)




if __name__ == "__main__":
    main()
