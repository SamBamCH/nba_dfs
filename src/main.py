import os
from data.data_manager import DataManager
from optimizer.optimizer import Optimizer


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
    config = data_manager.config

    # Initialize the optimizer
    num_lineups = 20  # Example number of lineups
    num_uniques = 1   # Example minimum number of unique players between lineups
    optimizer = Optimizer(site, players, num_lineups, num_uniques, config)

    # Run the optimization process
    try:
        optimized_lineups = optimizer.run()
        print(f"Generated {len(optimized_lineups)} optimized lineups.")
    except Exception as e:
        print(f"Error during optimization: {e}")
        return

    # Output the optimized lineups
    for i, lineup in enumerate(optimized_lineups, start=1):
        print(f"Lineup {i}: {[player.name for player in lineup]}")


if __name__ == "__main__":
    main()
