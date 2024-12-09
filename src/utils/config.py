import os
import json


def get_project_root():
    """
    Returns the absolute path of the project root.
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


def load_config(site):
    """
    Load the configuration file for the specified site (e.g., 'dk', 'fd').
    :param site: The site for which to load the configuration ('dk' or 'fd').
    :return: The loaded configuration as a dictionary.
    """
    config_path = os.path.join(get_project_root(), "data", "config", f"{site}_config.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, encoding="utf-8-sig") as file:
        return json.load(file)
