import sys
from OrpheusDL.orpheus.core import Orpheus
from OrpheusDL.utils.models import ModuleModes

orpheus_session = Orpheus(private_mode=False)
loaded_modules = {}

def initialize_modules():
    """Loads and logs in to all available modules from settings."""
    global loaded_modules
    for service_name in ['qobuz', 'tidal', 'kkbox']:
        try:
            if service_name in orpheus_session.settings['modules']:
                print(f"Loading module: {service_name}")
                module = orpheus_session.load_module(service_name)
                
                settings = orpheus_session.settings['modules'][service_name]
                if settings.get('username') and settings.get('password'):
                    print(f"Attempting to log in to {service_name}...")
                    module.login(settings['username'], settings['password'])
                    print(f"{service_name} login successful.")
                
                loaded_modules[service_name] = module
            else:
                print(f"INFO: Configuration for '{service_name}' not found in settings.json, skipping.")
        except Exception as e:
            print(f"FATAL: Could not load or log in to '{service_name}' module. Error: {e}")

    if not loaded_modules:
        print("FATAL: No modules were loaded successfully. Please check your config. Exiting.")

def get_module(service_name):
    """Returns the loaded module for a given service."""
    module = loaded_modules.get(service_name)
    if not module:
        raise ValueError(f"Service '{service_name}' is not available or configured.")
    return module

def construct_third_party_modules(service=None):
    """Constructs third-party modules dictionary for OrpheusDL."""
    third_party_modules = {}
    default_modules = orpheus_session.settings['global']['module_defaults']
    required_modes = {
        'lyrics': ModuleModes.lyrics,
        'covers': ModuleModes.covers,
        'credits': ModuleModes.credits
    }
    
    for mode_key, mode_enum in required_modes.items():
        module_name = default_modules.get(mode_key, '')
        if module_name and module_name in loaded_modules:
            third_party_modules[mode_enum] = loaded_modules[module_name]
        else:
            third_party_modules[mode_enum] = None
    
    return third_party_modules
