from src.optimizer import Optimizer

def main():
    site = "dk"

    # First run: use small randomness to get baseline ownership
    initial_randomness = 0.1  # Example value
    num_lineups_step1 = 500   # Example: run 100 lineups to gauge ownership
    num_uniques = 1           # Example unique constraint

    optimizer_step1 = Optimizer(site, num_lineups_step1, num_uniques, initial_randomness)
    initial_lineups = optimizer_step1.optimize(num_lineups_step1)

    # Calculate ownership-based constraints from the first run
    ownership_percentile = 90  # Example percentile
    ownership_limits = optimizer_step1.calculate_ownership_limits(initial_lineups, ownership_percentile)

    # Second run: use final constraints and parameters
    final_randomness = 0.0    # Example: no randomness now
    num_lineups_final = 150   # The final number of lineups you actually want

    optimizer_step2 = Optimizer(site, num_lineups_final, num_uniques, final_randomness)
    optimizer_step2.set_ownership_limits(ownership_limits)

    final_lineups = optimizer_step2.run()

    # Process or output final_lineups as needed
    print("Final lineups generated:", final_lineups)

if __name__ == "__main__":
    main()

