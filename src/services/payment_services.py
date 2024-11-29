"""This module provides services for payments."""

# Types
from typing import Dict

# Configuration
import yaml

# Services
from src.services.logging_services import logger

# Models
from src.models.payment_models import PricingModel

# Singleton for pricing models
PRICING_MODELS: Dict[str, PricingModel] = None

CONFIG_PATH = 'src/config/pricing_models.yml'

if PRICING_MODELS is None:
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as cfg:
            type_dicts = yaml.safe_load(cfg)
            PRICING_MODELS = {name: PricingModel(name=name, **details)
                              for name, details in type_dicts.items()}
    except FileNotFoundError:
        logger.warning(f"Configuration file not found: {CONFIG_PATH}.")
        PRICING_MODELS = {}
    except yaml.YAMLError as e:
        logger.warning(f"Error parsing YAML configuration: {e}")
        PRICING_MODELS = {}
    except TypeError as e:
        logger.warning(f"Data structure mismatch: {e}")
        PRICING_MODELS = {}
