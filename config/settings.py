import yaml
import os

def get_config():
    """
    Membaca konfigurasi dari settings.yml.
    """
    config_path = os.path.join(os.path.dirname(__file__), 'settings.yml')
    if not os.path.exists(config_path):
        print("Warning: settings.yml tidak ditemukan.")
        return {}
    
    with open(config_path, 'r') as file:
        try:
            return yaml.safe_load(file)
        except yaml.YAMLError as exc:
            print(f"Error parsing YAML file: {exc}")
            return {}
