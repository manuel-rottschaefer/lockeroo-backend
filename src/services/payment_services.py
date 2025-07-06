"""
Lockeroo.payment_services
-------------------------
This module provides utilities for payment handling

Key Features:
    - Imports pricing models from static configuration files
    
Dependencies:
    - yaml
"""
# Basics
import yaml
from pathlib import Path
from typing import Dict
# Models
from lockeroo_models.locker_models import PricingModel
# Services
from src.services.logging_services import logger_service as logger

# Singleton for pricing models
PRICING_MODELS: Dict[str, PricingModel] = None


def load_pricing_models(path: str) -> Dict[str, PricingModel]:
    # TODO: Why is this not referenced anywhere?
    """Loads pricing models from a YAML configuration file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        A dictionary mapping model names to PricingModel instances, or an empty
        dictionary if an error occurs or the file is not found.
    """
    path_obj = Path(path)  # Use Path for better file handling

    if not path_obj.exists():
        logger.warning(f"Configuration file not found: {path}.")
        return {}

    try:
        with open(path_obj, 'r', encoding='utf-8') as cfg:
            type_dicts = yaml.safe_load(cfg)
            if type_dicts is None:  # Handle empty YAML file
                return {}
            return {name: PricingModel(name=name, **details)
                    for name, details in type_dicts.items()}
    except yaml.YAMLError as e:
        logger.warning(f"Error parsing YAML configuration: {e}")
        return {}
    except TypeError as e:
        logger.warning(f"Data structure mismatch: {e}")
        return {}


# if PRICING_MODELS is None:
#    PRICING_MODELS = load_pricing_models('src/config/pricing_models.yml')
