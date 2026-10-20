#!/usr/bin/env python3
"""
Azure AI Content Understanding Cost Estimator and Explainer

This module provides cost estimation and analysis for Azure AI Content Understanding services.
It supports two estimation modes:

1. **Usage-based estimation** (Recommended): Use actual token counts from API responses
   for the most accurate cost calculations. Run test cases first to get the `usage` object.

2. **Schema-based estimation**: Estimate costs based on schema configuration when you
   haven't run test cases yet. This provides rough estimates but is less accurate than
   usage-based calculations.

IMPORTANT: For production cost planning, always validate estimates by running representative
test files through the actual Azure Content Understanding service and using the returned
usage data for calculations.
"""

import json
import argparse
import math
import sys
from copy import deepcopy
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, asdict, field
from pathlib import Path
from enum import Enum


# Pricing Configuration - based on Azure Content Understanding pricing
# Reference: https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/pricing-explainer
PRICING_CONFIG = {
    "ce": {
        "doc_per_1000_pages": 5.0,
        "document_tiers": {
            "basic": 1.0,
            "standard": 5.0,
            "basic_sync": 1.5,
            "standard_sync": 7.5,
        },
        "audio_per_minute": 0.006,
        "video_per_minute": 1.0 / 60
    },
    "ctx": {
        "regular_per_mtok": 1.0,
        "mini_per_mtok": 1.0,
        "standard_per_mtok": 1.0,
        "advanced_per_mtok": 3.0,
        "units": {
            "doc_page": 1000,
            "text_page": 1,
            "text_chars": 1,
            "image": 1000,
            "audio_minute": 100_000 / 60,
            "video_minute": 1_000_000 / 60
        }
    },
    "models": [
        {
            "name": "gpt-4o",
            "class": "regular",
            "tokens_per_unit": {
                "doc_page": {"in": 2600, "out": 90},
                "text_page": {"in": 2600, "out": 90},
                "image": {"in": 1043, "out": 170},
                "audio_minute": {"in": 604, "out": 19},
                "video_minute": {"in": 10695, "out": 3103}
            },
            "pricing": {
                "global_regional": {"input_per_mtok": 2.50, "output_per_mtok": 10.00},
                "data_zone": {"input_per_mtok": 2.75, "output_per_mtok": 11.00}
            }
        },
        {
            "name": "gpt-4o-mini",
            "class": "mini",
            "tokens_per_unit": {
                "doc_page": {"in": 2600, "out": 90},
                "text_page": {"in": 2600, "out": 90},
                "image": {"in": 3476, "out": 170},
                "audio_minute": {"in": 604, "out": 19},
                "video_minute": {"in": 175575, "out": 3103}
            },
            "pricing": {
                "global_regional": {"input_per_mtok": 0.15, "output_per_mtok": 0.60},
                "data_zone": {"input_per_mtok": 0.165, "output_per_mtok": 0.66}
            }
        },
        {
            "name": "gpt-4.1",
            "class": "regular",
            "tokens_per_unit": {
                "doc_page": {"in": 2600, "out": 90},
                "text_page": {"in": 2600, "out": 90},
                "image": {"in": 1043, "out": 170},
                "audio_minute": {"in": 604, "out": 19},
                "video_minute": {"in": 10695, "out": 3103}
            },
            "pricing": {
                "global_regional": {"input_per_mtok": 2.00, "output_per_mtok": 8.00},
                "data_zone": {"input_per_mtok": 2.20, "output_per_mtok": 8.80}
            }
        },
        {
            "name": "gpt-4.1-mini",
            "class": "mini",
            "tokens_per_unit": {
                "doc_page": {"in": 2600, "out": 90},
                "text_page": {"in": 2600, "out": 90},
                "image": {"in": 3476, "out": 170},
                "audio_minute": {"in": 604, "out": 19},
                "video_minute": {"in": 175575, "out": 3103}
            },
            "pricing": {
                "global_regional": {"input_per_mtok": 0.40, "output_per_mtok": 1.60},
                "data_zone": {"input_per_mtok": 0.44, "output_per_mtok": 1.76}
            }
        },
        {
            "name": "gpt-4.1-nano",
            "class": "mini",
            "tokens_per_unit": {
                "doc_page": {"in": 2600, "out": 90},
                "text_page": {"in": 2600, "out": 90},
                "image": {"in": 3476, "out": 170},
                "audio_minute": {"in": 604, "out": 19},
                "video_minute": {"in": 175575, "out": 3103}
            },
            "pricing": {
                "global_regional": {"input_per_mtok": 0.10, "output_per_mtok": 0.40},
                "data_zone": {"input_per_mtok": 0.11, "output_per_mtok": 0.44}
            }
        }
    ],
    "embeddings": {
        "text-embedding-3-small": {
            "tokens_per_call": 1500,
            "price_per_1k_tokens": 0.000022
        },
        "text-embedding-3-large": {
            "tokens_per_call": 1500,
            "price_per_1k_tokens": 0.000143
        },
        "text-embedding-ada-002 (Version 2)": {
            "tokens_per_call": 1500,
            "price_per_1k_tokens": 0.00011
        }
    },
    "page_from_chars": 3000,
    # Token multipliers for advanced features (from MS docs)
    "feature_multipliers": {
        "source_grounding_confidence": 2.0,  # ~2x token usage
        "extractive_mode": 1.5,               # ~1.5x token usage  
        "training_examples": 2.0,             # ~2x token usage
        "segmentation_categorization": 2.0    # ~2x token usage
    }
}

# These retained GPT-4 rates are historical estimates, not verified current prices.
# Preserve the legacy combined key for clients supplying older configurations.
for _model in PRICING_CONFIG["models"]:
    _model["pricing_status"] = "historical estimate; verify current model pricing"
    for _tier in ("global", "regional"):
        _model["pricing"][_tier] = deepcopy(_model["pricing"]["global_regional"])
    for _rates in _model["pricing"].values():
        _rates["cached_input_per_mtok"] = None

for _name in (
    "gpt-6.1-luna", "gpt-6.1-sol", "gpt-6.1-astra",
    "gpt-6-luna", "gpt-6-sol", "gpt-6-astra",
    "gpt-5.6-tera", "gpt-5.6-luna", "gpt-5.6-sol",
    "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.2", "gpt-5.1",
    "gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-6",
):
    _reference = next(model for model in PRICING_CONFIG["models"] if model["name"] == (
        "gpt-4.1-nano" if _name.endswith("-nano")
        else "gpt-4.1-mini" if _name.endswith("-mini") else "gpt-4.1"
    ))
    PRICING_CONFIG["models"].append({
        "name": _name,
        "class": _reference["class"],
        # Planning heuristics only, not measured usage for these model families.
        "tokens_per_unit": deepcopy(_reference["tokens_per_unit"]),
        "pricing_status": (
            "unverified model pricing; rates initially unset; GPT-4 token heuristics"
            + ("; gpt-6 is a configurable family placeholder, not a confirmed model ID"
               if _name == "gpt-6" else "")
        ),
        "pricing": {
            tier: {"input_per_mtok": None, "cached_input_per_mtok": None,
                   "output_per_mtok": None}
            for tier in ("global", "regional", "data_zone", "global_regional")
        },
    })

for _version in ("2024-11-20", "2024-08-06"):
    _versioned_model = deepcopy(PRICING_CONFIG["models"][0])
    _versioned_model["name"] = f"gpt-4o-{_version}"
    PRICING_CONFIG["models"].append(_versioned_model)

PRICING_CONFIG["embeddings"]["text-embedding-ada-002"] = deepcopy(
    PRICING_CONFIG["embeddings"]["text-embedding-ada-002 (Version 2)"]
)

_DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "lib"
PUBLIC_PRICING = json.loads((_DATA_DIR / "azure-openai-pricing.json").read_text(encoding="utf-8"))
INVOICE_BENCHMARK = json.loads((_DATA_DIR / "invoice-token-defaults.json").read_text(encoding="utf-8"))
for _model in PRICING_CONFIG["models"]:
    if _model["name"] in PUBLIC_PRICING["models"]:
        _model["pricing"] = deepcopy(PUBLIC_PRICING["models"][_model["name"]])
        _model["pricing"]["global_regional"] = deepcopy(_model["pricing"]["global"])
        _model["pricing_status"] = (
            f"Public Azure OpenAI USD Standard short-context prices, {PUBLIC_PRICING['region']}, "
            f"retrieved {PUBLIC_PRICING['retrievedAt']}; unpublished rates require an override"
        )
    _measurement = INVOICE_BENCHMARK["models"].get(_model["name"], {})
    _model["document_benchmark"] = _measurement
    if _measurement.get("status") == "measured":
        _per_page = _measurement["perPage"]
        _model["tokens_per_unit"]["doc_page"] = {
            "in": _per_page["input"], "out": _per_page["output"],
            "cached_input": _per_page["cached_input"],
            "contextualization": _per_page["contextualization"],
            "embeddings": _per_page["embeddings"],
        }
for _name, _prices in PUBLIC_PRICING["embeddings"].items():
    PRICING_CONFIG["embeddings"][_name].update(deepcopy(_prices))
PRICING_CONFIG["embeddings"]["text-embedding-ada-002 (Version 2)"] = deepcopy(
    PRICING_CONFIG["embeddings"]["text-embedding-ada-002"]
)


def _nonnegative(name: str, value: float) -> None:
    """Reject invalid quantities and rates before performing billing arithmetic."""
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


class EstimationMode(Enum):
    """Estimation mode - either from actual usage data or schema-based estimation"""
    USAGE_BASED = "usage_based"      # Recommended: Use actual token counts from API
    SCHEMA_BASED = "schema_based"    # Estimate from schema configuration


@dataclass
class UsageData:
    """
    Actual usage data from Azure Content Understanding API response.
    
    This is the RECOMMENDED way to estimate costs - by running test cases
    and using the actual usage object returned by the API.
    
    Example API response usage object:
    ```json
    "usage": {
        "documentPagesMinimal": 0,
        "documentPagesBasic": 0,
        "documentPagesStandard": 2,
        "contextualizationToken": 2000,
        "tokens": {
            "gpt-4.1-input": 10400,
            "gpt-4.1-output": 360
        }
    }
    ```
    """
    input_tokens: int
    output_tokens: int
    contextualization_tokens: int = 0
    document_pages_minimal: int = 0
    document_pages_basic: int = 0
    document_pages_standard: int = 0
    audio_minutes: float = 0.0
    video_minutes: float = 0.0
    embedding_tokens: int = 0
    cached_input_tokens: int = 0
    document_pages_basic_sync: int = 0
    document_pages_standard_sync: int = 0
    embedding_tokens_reported: bool = False

    def __post_init__(self):
        for name, value in asdict(self).items():
            _nonnegative(name, value)
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens cannot exceed total input_tokens")
    
    @classmethod
    def from_api_response(cls, usage: Dict[str, Any]) -> 'UsageData':
        """
        Create UsageData from Azure Content Understanding API response.
        
        Args:
            usage: The 'usage' object from the API response
            
        Returns:
            UsageData instance populated from the response
        """
        tokens = usage.get("tokens", {})
        
        # Extract input/output tokens (may be prefixed with model name)
        input_tokens = 0
        output_tokens = 0
        cached_input_tokens = 0
        for key, value in tokens.items():
            _nonnegative(key, value)
            if key.startswith("text-embedding-"):
                continue
            if "cached" in key.lower() and "input" in key.lower():
                cached_input_tokens += value
            elif "input" in key.lower():
                input_tokens += value
            elif "output" in key.lower():
                output_tokens += value
        
        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            contextualization_tokens=usage.get("contextualizationTokens", usage.get("contextualizationToken", 0)),
            document_pages_minimal=usage.get("documentPagesMinimal", 0),
            document_pages_basic=usage.get("documentPagesBasic", 0),
            document_pages_standard=usage.get("documentPagesStandard", 0),
            audio_minutes=usage.get("audioMinutes", usage.get("audioHours", 0.0) * 60),
            video_minutes=usage.get("videoMinutes", usage.get("videoHours", 0.0) * 60),
            embedding_tokens=usage.get("embeddingTokens", sum(
                value for key, value in tokens.items() if key.startswith("text-embedding-")
            )),
            cached_input_tokens=cached_input_tokens,
            document_pages_basic_sync=usage.get("documentPagesBasicSync", 0),
            document_pages_standard_sync=usage.get("documentPagesStandardSync", 0),
            embedding_tokens_reported="tokens" in usage or "embeddingTokens" in usage,
        )


@dataclass 
class SchemaConfig:
    """
    Schema configuration for schema-based cost estimation.
    
    WARNING: Schema-based estimation provides ROUGH estimates only.
    For accurate cost calculations, run test cases through the actual
    Azure Content Understanding service and use the returned usage data.
    
    Attributes:
        num_fields: Number of fields in your extraction schema
        field_complexity: Average complexity of fields ('simple', 'moderate', 'complex')
        source_grounding_enabled: Whether source grounding is enabled
        confidence_scores_enabled: Whether confidence scores are enabled
        extractive_mode: Whether extractive mode is used
        training_examples_count: Number of training examples (0 if not using knowledge base)
        use_segmentation: Whether segmentation is used
        use_categorization: Whether categorization is used
        avg_field_value_length: Estimated average length of extracted field values (chars)
    """
    num_fields: int = 5
    field_complexity: str = "moderate"  # simple, moderate, complex
    source_grounding_enabled: bool = False
    confidence_scores_enabled: bool = False
    extractive_mode: bool = False
    training_examples_count: int = 0
    use_segmentation: bool = False
    use_categorization: bool = False
    avg_field_value_length: int = 50  # characters per field value

    def __post_init__(self):
        for name in ("num_fields", "training_examples_count", "avg_field_value_length"):
            _nonnegative(name, getattr(self, name))
        if self.field_complexity not in ("simple", "moderate", "complex"):
            raise ValueError("Invalid field_complexity")
    
    def estimate_output_tokens_per_page(self) -> int:
        """
        Estimate output tokens per page based on schema configuration.
        
        This is a ROUGH estimate. Actual token usage varies significantly
        based on document content and structure.
        """
        # Base output tokens (rough estimate)
        complexity_multipliers = {
            "simple": 0.7,
            "moderate": 1.0,
            "complex": 1.5
        }
        multiplier = complexity_multipliers.get(self.field_complexity, 1.0)
        
        # Estimate ~4 tokens per character in field values
        # Plus overhead for JSON structure, field names, etc.
        tokens_per_field = (self.avg_field_value_length / 4) + 10  # ~10 tokens overhead per field
        base_output = int(self.num_fields * tokens_per_field * multiplier)
        
        # Apply feature multipliers
        if self.source_grounding_enabled or self.confidence_scores_enabled:
            base_output = int(base_output * 1.5)  # Grounding/confidence adds ~50% more output
        
        if self.extractive_mode:
            base_output = int(base_output * 1.3)  # Extractive mode adds source text
            
        return max(base_output, 30)  # Minimum reasonable output
    
    def get_token_multiplier(self) -> float:
        """Get combined token multiplier based on enabled features"""
        multiplier = 1.0
        
        if self.source_grounding_enabled and self.confidence_scores_enabled:
            multiplier *= 2.0
        elif self.source_grounding_enabled or self.confidence_scores_enabled:
            multiplier *= 1.5
            
        if self.extractive_mode:
            multiplier *= 1.5
            
        if self.training_examples_count > 0:
            multiplier *= 2.0
            
        if self.use_segmentation or self.use_categorization:
            multiplier *= 2.0
            
        return multiplier


@dataclass
class CostBreakdown:
    """Represents a detailed cost breakdown"""
    ce_cost: float  # Content Extraction
    fe_cost: float  # Field Extraction (LLM)
    ctx_cost: float  # Contextualization
    embeddings_cost: float  # Embeddings
    total_cost: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    units: float
    estimation_mode: str = "schema_based"  # or "usage_based"
    confidence_note: str = ""
    cached_input_tokens: int = 0
    pricing_note: str = ""


@dataclass
class ProcessingRequest:
    """Represents a document processing request"""
    file_type: str  # document, text, image, audio, video
    quantity: float  # pages, characters, images, or minutes
    model_name: str = "gpt-4o"
    deployment_type: str = "global"  # global, regional, data_zone, ptu
    field_extraction_enabled: bool = True
    embeddings_enabled: bool = False
    embeddings_model: str = "text-embedding-3-small"
    # New fields for estimation mode
    usage_data: Optional[UsageData] = None  # For usage-based estimation
    schema_config: Optional[SchemaConfig] = None  # For schema-based estimation
    document_tier: str = "standard"  # basic, standard, basic_sync, standard_sync
    contextualization_tier: str = "standard"  # standard or advanced (preview)
    model_rates: Optional[Dict[str, float]] = None  # USD per million tokens
    cached_input_tokens: Optional[int] = None  # None uses measured planning defaults; usage mode uses UsageData

    def __post_init__(self):
        _nonnegative("quantity", self.quantity)
        if self.cached_input_tokens is not None:
            _nonnegative("cached_input_tokens", self.cached_input_tokens)
        if self.file_type not in ("document", "text", "image", "audio", "video"):
            raise ValueError("Unsupported file_type")
        if self.document_tier not in ("basic", "standard", "basic_sync", "standard_sync"):
            raise ValueError("Unsupported document_tier")
        if self.document_tier.endswith("_sync") and self.file_type != "document":
            raise ValueError("Sync tiers support documents only")
        if self.contextualization_tier not in ("standard", "advanced"):
            raise ValueError("Unsupported contextualization_tier")
        if self.deployment_type not in ("global", "regional", "data_zone", "datazone", "global_regional", "ptu"):
            raise ValueError("Unsupported deployment_type")
        for name, value in (self.model_rates or {}).items():
            if name not in ("input_per_mtok", "cached_input_per_mtok", "output_per_mtok"):
                raise ValueError(f"Unknown model rate: {name}")
            _nonnegative(name, value)


class CostEstimator:
    """
    Main cost estimator class for Azure AI Content Understanding.
    
    Supports two estimation modes:
    
    1. **Usage-based** (Recommended): Provide actual token counts from API responses
       for accurate cost calculations. Get this data by running test cases first.
       
    2. **Schema-based**: Estimate costs from schema configuration. This is useful
       for initial planning but is less accurate than usage-based calculations.
    
    Example (usage-based - recommended):
        ```python
        # After running a test through the API, use the usage object:
        usage = UsageData(
            input_tokens=10400,
            output_tokens=360,
            contextualization_tokens=2000,
            document_pages_standard=2
        )
        request = ProcessingRequest(
            file_type="document",
            quantity=1000,  # Scale up from test results
            model_name="gpt-4.1",
            usage_data=usage
        )
        breakdown = estimator.estimate_from_usage(request, scale_factor=500)  # 2 pages -> 1000
        ```
    
    Example (schema-based - rough estimate):
        ```python
        schema = SchemaConfig(
            num_fields=10,
            field_complexity="moderate",
            source_grounding_enabled=True
        )
        request = ProcessingRequest(
            file_type="document",
            quantity=1000,
            model_name="gpt-4o-mini",
            schema_config=schema
        )
        breakdown = estimator.estimate_from_schema(request)
        ```
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or PRICING_CONFIG
    
    def get_model_config(self, model_name: str) -> Optional[Dict]:
        """Get model configuration by name"""
        for model in self.config["models"]:
            if model["name"] == model_name:
                return model
        return None

    def _request_model(self, request: ProcessingRequest) -> Dict:
        request.__post_init__()
        if request.document_tier.endswith("_sync") or (
            request.usage_data and (
                request.usage_data.document_pages_basic_sync
                or request.usage_data.document_pages_standard_sync
            )
        ):
            return {"name": request.model_name, "class": "unused",
                    "pricing_status": "Sync: content extraction only"}
        model = self.get_model_config(request.model_name)
        if model is None:
            raise ValueError(f"Model {request.model_name} not found")
        model = deepcopy(model)
        tier = self.get_pricing_tier(request.deployment_type)
        rates = self._model_rates(model, request.deployment_type)
        rates.update(request.model_rates or {})
        model["pricing"][tier] = rates
        if request.model_rates:
            model["pricing_status"] = (
                "Caller-provided rate overrides. "
                + model.get("pricing_status", "Custom configured model rates")
            )
        return model

    def _model_rates(self, model: Dict, deployment_type: str) -> Dict:
        tier = self.get_pricing_tier(deployment_type)
        rates = model["pricing"].get(tier)
        if rates is None and tier in ("global", "regional"):
            rates = model["pricing"].get("global_regional")
        return dict(rates or {})

    def _token_cost(self, input_tokens, output_tokens, cached_tokens, model,
                    deployment_type) -> float:
        for name, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens),
                            ("cached_input_tokens", cached_tokens)):
            _nonnegative(name, value)
        if cached_tokens > input_tokens:
            raise ValueError("cached_input_tokens cannot exceed total input_tokens")
        if deployment_type == "ptu":
            return 0.0
        rates = self._model_rates(model, deployment_type)
        total = 0.0
        for key, tokens in (("input_per_mtok", input_tokens - cached_tokens),
                            ("cached_input_per_mtok", cached_tokens),
                            ("output_per_mtok", output_tokens)):
            rate = rates.get(key)
            if rate is not None:
                _nonnegative(key, rate)
            if tokens:
                if rate is None:
                    raise ValueError(
                        f"Missing required {key} for {model['name']} / {deployment_type}; "
                        "provide model_rates (USD per million tokens)"
                    )
                total += tokens / 1_000_000 * rate
        _nonnegative("model cost", total)
        return total

    def _context_rate(self, tier: str) -> float:
        if tier not in ("standard", "advanced"):
            raise ValueError("Unsupported contextualization_tier")
        rate = self.config["ctx"].get(
            f"{tier}_per_mtok",
            self.config["ctx"].get("regular_per_mtok") if tier == "standard" else None,
        )
        _nonnegative(f"{tier} contextualization rate", rate)
        return rate

    def _sync_breakdown(self, request, mode, scale_factor=1.0):
        usage = request.usage_data
        sync_usage = usage is not None and (
            usage.document_pages_basic_sync or usage.document_pages_standard_sync
        )
        if not request.document_tier.endswith("_sync") and not sync_usage:
            return None
        if request.file_type != "document":
            raise ValueError("Sync usage supports documents only")
        pages = request.quantity
        if usage is not None:
            usage.__post_init__()
            if sync_usage and (usage.document_pages_basic or usage.document_pages_standard):
                raise ValueError("Estimate mixed Sync and async usage in separate requests")
            if usage.document_pages_minimal:
                raise ValueError("documentPagesMinimal has no supported Content Understanding rate")
            if usage.document_pages_basic_sync or usage.document_pages_standard_sync:
                cost = scale_factor / 1000 * (
                    usage.document_pages_basic_sync * self._document_rate("basic_sync")
                    + usage.document_pages_standard_sync * self._document_rate("standard_sync")
                )
            else:
                measured = usage.document_pages_basic + usage.document_pages_standard
                pages = measured * scale_factor if measured else pages
                cost = pages / 1000 * self._document_rate(request.document_tier)
        else:
            cost = pages / 1000 * self._document_rate(request.document_tier)
        return CostBreakdown(
            ce_cost=cost, fe_cost=0.0, ctx_cost=0.0, embeddings_cost=0.0,
            total_cost=cost, input_tokens=0, output_tokens=0, total_tokens=0,
            units=request.quantity, estimation_mode=mode,
            confidence_note="Sync preview supports content extraction only; field extraction, contextualization and embeddings excluded.",
            pricing_note="Sync preview content extraction rate",
        )

    def _document_rate(self, tier):
        rate = self.config["ce"].get("document_tiers", {}).get(tier)
        if rate is None and tier == "standard":
            rate = self.config["ce"]["doc_per_1000_pages"]
        _nonnegative(f"{tier} document rate", rate)
        return rate
    
    def get_unit_key(self, file_type: str) -> str:
        """Convert file type to unit key"""
        mapping = {
            "document": "doc_page",
            "text": "text_page",
            "image": "image",
            "audio": "audio_minute",
            "video": "video_minute"
        }
        return mapping.get(file_type, "doc_page")
    
    def convert_text_to_pages(self, characters: float) -> float:
        """Convert text characters to pages"""
        _nonnegative("characters", characters)
        return characters / self.config["page_from_chars"]
    
    def get_units_for_calculation(self, file_type: str, quantity: float) -> float:
        """Get units for calculation (convert text chars to pages if needed)"""
        if file_type == "text":
            return self.convert_text_to_pages(quantity)
        return quantity
    
    def calculate_content_extraction(self, file_type: str, units: float,
                                     document_tier: str = "standard") -> float:
        """Calculate content extraction cost"""
        _nonnegative("units", units)
        if file_type == "document":
            return (units / 1000) * self._document_rate(document_tier)
        elif file_type == "audio":
            _nonnegative("audio rate", self.config["ce"]["audio_per_minute"])
            return units * self.config["ce"]["audio_per_minute"]
        elif file_type == "video":
            _nonnegative("video rate", self.config["ce"]["video_per_minute"])
            return units * self.config["ce"]["video_per_minute"]
        # text is free, image doesn't have CE
        return 0.0
    
    def calculate_field_extraction(
        self, 
        file_type: str, 
        units: float, 
        model: Dict,
        deployment_type: str,
        cached_input_tokens: Optional[int] = None
    ) -> Tuple[int, int, float]:
        """Calculate field extraction tokens and cost
        
        Returns: (input_tokens, output_tokens, cost)
        """
        _nonnegative("units", units)
        unit_key = self.get_unit_key(file_type)
        tokens_per_unit = model["tokens_per_unit"].get(unit_key)
        
        if not tokens_per_unit:
            raise ValueError(f"Missing token estimates for {model['name']} / {file_type}; use usage data")
        
        input_tokens = int(units * tokens_per_unit["in"])
        output_tokens = int(units * tokens_per_unit["out"])
        if cached_input_tokens is None:
            cached_input_tokens = int(units * (tokens_per_unit.get("cached_input") or 0))
        
        # Calculate cost based on deployment type (PTU deployments don't have per-token costs)
        cost = self._token_cost(input_tokens, output_tokens, cached_input_tokens,
                                model, deployment_type)
        
        return input_tokens, output_tokens, cost
    
    def calculate_field_extraction_from_usage(
        self,
        usage: UsageData,
        scale_factor: float,
        model: Dict,
        deployment_type: str
    ) -> Tuple[int, int, float]:
        """Calculate field extraction cost from actual usage data
        
        Args:
            usage: Actual usage data from API
            scale_factor: Multiplier to scale from test to production volume
            model: Model configuration
            deployment_type: Deployment type
            
        Returns: (input_tokens, output_tokens, cost)
        """
        usage.__post_init__()
        _nonnegative("scale_factor", scale_factor)
        input_tokens = int(usage.input_tokens * scale_factor)
        output_tokens = int(usage.output_tokens * scale_factor)
        cached_tokens = int(usage.cached_input_tokens * scale_factor)
        cost = self._token_cost(input_tokens, output_tokens, cached_tokens,
                                model, deployment_type)
        
        return input_tokens, output_tokens, cost
    
    def calculate_embeddings(
        self,
        units: float,
        model: Dict,
        file_type: str,
        embeddings_model: str,
        deployment_type: str
    ) -> Tuple[int, float]:
        """Calculate embeddings tokens and cost
        
        Returns: (total_tokens, cost)
        """
        _nonnegative("units", units)
        embedding_config = self.config["embeddings"].get(embeddings_model)
        if not embedding_config:
            raise ValueError(f"Embeddings model {embeddings_model} not found")
        
        unit_key = self.get_unit_key(file_type)
        tokens_per_unit = model["tokens_per_unit"].get(unit_key)
        
        if not tokens_per_unit:
            raise ValueError(f"Missing embedding token estimates for {file_type}; use usage data")
        
        total_tokens = int(units * tokens_per_unit.get("embeddings", tokens_per_unit["in"]))
        _nonnegative("embedding tokens", total_tokens)
        
        cost = 0.0
        if deployment_type != "ptu":
            cost = (total_tokens / 1000) * self._embedding_rate(embeddings_model, deployment_type)
        
        return total_tokens, cost

    def _embedding_rate(self, name, deployment_type):
        config = self.config["embeddings"].get(name)
        if not config:
            raise ValueError(f"Embeddings model {name} not found")
        tier = self.get_pricing_tier(deployment_type)
        if tier == "global_regional":
            tier = "global"
        rate = config["pricing"].get(tier) if "pricing" in config else config["price_per_1k_tokens"]
        _nonnegative("embedding rate", rate)
        return rate
    
    def calculate_contextualization(self, file_type: str, units: float, model: Dict, original_quantity: float = None,
                                    contextualization_tier: str = "standard") -> Tuple[int, float]:
        """Calculate contextualization tokens and cost
        
        Args:
            file_type: Type of file being processed
            units: Effective units (pages for most types)
            model: Model configuration dictionary
            original_quantity: Original quantity before conversion (for text type)
        
        Returns: (tokens, cost)
        """
        _nonnegative("units", units)
        if original_quantity is not None:
            _nonnegative("original_quantity", original_quantity)
        # For text type, use original character count for CTX calculation
        if file_type == "text" and original_quantity is not None:
            tokens_per_unit = self.config["ctx"]["units"]["text_chars"]
            tokens = int(original_quantity * tokens_per_unit)
        else:
            # Get CTX tokens per unit
            unit_key_mapping = {
                "document": "doc_page",
                "image": "image",
                "audio": "audio_minute",
                "video": "video_minute"
            }
            
            unit_key = unit_key_mapping.get(file_type, "doc_page")
            tokens_per_unit = model.get("tokens_per_unit", {}).get(unit_key, {}).get(
                "contextualization", self.config["ctx"]["units"][unit_key]
            )
            tokens = int(units * tokens_per_unit)
        
        rate_per_mtok = self._context_rate(contextualization_tier)
        _nonnegative("contextualization tokens", tokens)
        
        cost = (tokens / 1_000_000) * rate_per_mtok
        
        return tokens, cost
    
    def calculate_contextualization_from_usage(
        self,
        usage: UsageData,
        scale_factor: float,
        model: Dict,
        contextualization_tier: str = "standard"
    ) -> Tuple[int, float]:
        """Calculate contextualization from actual usage data
        
        Args:
            usage: Actual usage data
            scale_factor: Multiplier to scale from test to production
            model: Model configuration
            
        Returns: (tokens, cost)
        """
        usage.__post_init__()
        _nonnegative("scale_factor", scale_factor)
        tokens = int(usage.contextualization_tokens * scale_factor)
        rate_per_mtok = self._context_rate(contextualization_tier)
        
        cost = (tokens / 1_000_000) * rate_per_mtok
        
        return tokens, cost
    
    def get_pricing_tier(self, deployment_type: str) -> str:
        """Get pricing tier from deployment type
        
        Args:
            deployment_type: Deployment type (global, regional, data_zone, ptu)
            
        Returns:
            Pricing tier string for config lookup
        """
        if deployment_type == "datazone":
            return "data_zone"
        if deployment_type not in ("global", "regional", "data_zone", "global_regional", "ptu"):
            raise ValueError("Unsupported deployment_type")
        return deployment_type
    
    def estimate_from_usage(
        self,
        request: ProcessingRequest,
        scale_factor: float = 1.0,
        test_pages: Optional[int] = None
    ) -> CostBreakdown:
        """
        Estimate cost using actual usage data from API response.
        
        This is the RECOMMENDED method for accurate cost estimation.
        Run test cases through the Azure Content Understanding API first,
        then use the returned usage object to calculate scaled costs.
        
        Args:
            request: Processing request with usage_data populated
            scale_factor: Multiplier to scale from test volume to production
                         (e.g., if you tested 10 pages and want estimate for 1000,
                         use scale_factor=100)
            test_pages: Number of pages in your test (alternative to scale_factor)
            
        Returns:
            CostBreakdown with accurate cost information
        """
        if not request.usage_data:
            raise ValueError("usage_data is required for usage-based estimation")
        
        usage = request.usage_data
        request.__post_init__()
        usage.__post_init__()
        # Calculate scale factor if test_pages provided
        if test_pages is not None:
            _nonnegative("test_pages", test_pages)
            if test_pages == 0:
                raise ValueError("test_pages must be positive")
            scale_factor = request.quantity / test_pages
        _nonnegative("scale_factor", scale_factor)
        sync = self._sync_breakdown(request, "usage_based", scale_factor)
        if sync is not None:
            return sync
        model = self._request_model(request)
        
        # Content Extraction - from usage data
        if usage.document_pages_minimal:
            raise ValueError("documentPagesMinimal has no supported Content Understanding rate")
        has_ce_usage = any((usage.document_pages_basic, usage.document_pages_standard,
                            usage.audio_minutes, usage.video_minutes))
        if has_ce_usage:
            ce_cost = scale_factor * (
                usage.document_pages_basic / 1000 * self._document_rate("basic")
                + usage.document_pages_standard / 1000 * self._document_rate("standard")
                + self.calculate_content_extraction("audio", usage.audio_minutes)
                + self.calculate_content_extraction("video", usage.video_minutes)
            )
        else:
            ce_cost = self.calculate_content_extraction(
                request.file_type, request.quantity, request.document_tier
            )
        
        # Field Extraction (LLM tokens)
        input_tokens, output_tokens, fe_cost = 0, 0, 0.0
        cached_tokens = 0
        if request.field_extraction_enabled:
            input_tokens, output_tokens, fe_cost = self.calculate_field_extraction_from_usage(
                usage, scale_factor, model, request.deployment_type
            )
            cached_tokens = int(usage.cached_input_tokens * scale_factor)
        
        # Contextualization
        ctx_tokens, ctx_cost = self.calculate_contextualization_from_usage(
            usage, scale_factor, model, request.contextualization_tier
        )
        
        # Embeddings
        embeddings_cost = 0.0
        if usage.embedding_tokens > 0:
            embedding_config = self.config["embeddings"].get(request.embeddings_model)
            if not embedding_config:
                raise ValueError(f"Embeddings model {request.embeddings_model} not found")
            if request.deployment_type != "ptu":
                scaled_embedding_tokens = usage.embedding_tokens * scale_factor
                embeddings_cost = (scaled_embedding_tokens / 1000) * self._embedding_rate(
                    request.embeddings_model, request.deployment_type
                )
        elif request.embeddings_enabled and not usage.embedding_tokens_reported:
            embedding_config = self.config["embeddings"].get(request.embeddings_model)
            if not embedding_config:
                raise ValueError(f"Embeddings model {request.embeddings_model} not found")
            if request.deployment_type != "ptu":
                embeddings_cost = usage.input_tokens * scale_factor / 1000 * self._embedding_rate(
                    request.embeddings_model, request.deployment_type
                )
        
        total_cost = ce_cost + fe_cost + ctx_cost + embeddings_cost
        total_tokens = input_tokens + output_tokens + ctx_tokens
        
        return CostBreakdown(
            ce_cost=ce_cost,
            fe_cost=fe_cost,
            ctx_cost=ctx_cost,
            embeddings_cost=embeddings_cost,
            total_cost=total_cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            units=request.quantity,
            estimation_mode="usage_based",
            confidence_note="High confidence token quantities - based on actual API usage data; model rates still require verification.",
            cached_input_tokens=cached_tokens,
            pricing_note=model.get("pricing_status", "Custom configured model rates"),
        )
    
    def estimate_from_schema(self, request: ProcessingRequest) -> CostBreakdown:
        """
        Estimate cost based on schema configuration.
        
        WARNING: This provides ROUGH estimates only. Token usage varies significantly
        based on actual document content, structure, and complexity.
        
        For accurate cost planning, always validate by running representative test
        files through the Azure Content Understanding service and using the returned
        usage data with estimate_from_usage().
        
        Args:
            request: Processing request with schema_config populated
            
        Returns:
            CostBreakdown with estimated costs (includes confidence warning)
        """
        schema = request.schema_config or SchemaConfig()
        request.__post_init__()
        schema.__post_init__()
        sync = self._sync_breakdown(request, "schema_based")
        if sync is not None:
            return sync
        model = self._request_model(request)
        
        units = self.get_units_for_calculation(request.file_type, request.quantity)
        
        # Content Extraction
        ce_cost = self.calculate_content_extraction(request.file_type, units, request.document_tier)
        
        # Field Extraction with schema-based estimation
        unit_key = self.get_unit_key(request.file_type)
        tokens_per_unit = model["tokens_per_unit"].get(unit_key)
        if not tokens_per_unit and request.field_extraction_enabled:
            raise ValueError(f"Missing token estimates for {model['name']} / {request.file_type}; use usage data")
        
        if tokens_per_unit and request.field_extraction_enabled:
            # Base input tokens from model config
            base_input = tokens_per_unit["in"]
            # Estimate output tokens from schema
            estimated_output = schema.estimate_output_tokens_per_page()
            
            # Apply feature multipliers
            multiplier = schema.get_token_multiplier()
            
            input_tokens = int(units * base_input * multiplier)
            output_tokens = int(units * estimated_output * multiplier)
            
            fe_cost = self._token_cost(input_tokens, output_tokens, request.cached_input_tokens or 0,
                                       model, request.deployment_type)
        else:
            input_tokens, output_tokens, fe_cost = 0, 0, 0.0
        
        # Contextualization
        ctx_tokens, ctx_cost = self.calculate_contextualization(
            request.file_type, units, model,
            original_quantity=request.quantity if request.file_type == "text" else None,
            contextualization_tier=request.contextualization_tier,
        )
        
        # Embeddings
        embeddings_cost = 0.0
        if request.embeddings_enabled or schema.training_examples_count > 0:
            _, embeddings_cost = self.calculate_embeddings(
                units, model, request.file_type, request.embeddings_model, request.deployment_type
            )
        
        total_cost = ce_cost + fe_cost + ctx_cost + embeddings_cost
        total_tokens = input_tokens + output_tokens + ctx_tokens
        
        return CostBreakdown(
            ce_cost=ce_cost,
            fe_cost=fe_cost,
            ctx_cost=ctx_cost,
            embeddings_cost=embeddings_cost,
            total_cost=total_cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            units=units,
            estimation_mode="schema_based",
            confidence_note=(
                "LOW confidence - schema-based estimate. Actual costs may vary significantly. "
                "For accurate estimates, run test cases through Azure Content Understanding "
                "and use the returned usage data."
            ),
            cached_input_tokens=(request.cached_input_tokens or 0) if request.field_extraction_enabled else 0,
            pricing_note=model.get("pricing_status", "Custom configured model rates"),
        )
    
    def estimate_cost(self, request: ProcessingRequest) -> CostBreakdown:
        """
        Estimate cost for a processing request.
        
        Automatically chooses the best estimation method based on available data:
        - If usage_data is provided: Uses accurate usage-based estimation
        - If schema_config is provided: Uses schema-based estimation (less accurate)
        - Otherwise: Uses default token estimates (least accurate)
        
        Args:
            request: Processing request with all parameters
            
        Returns:
            CostBreakdown with detailed cost information
        """
        # Prefer usage-based if available
        if request.usage_data:
            return self.estimate_from_usage(request)
        
        # Fall back to schema-based if schema provided
        if request.schema_config:
            return self.estimate_from_schema(request)
        
        # Default: use original estimation method
        request.__post_init__()
        sync = self._sync_breakdown(request, "default")
        if sync is not None:
            return sync
        model = self._request_model(request)
        
        # Calculate units
        units = self.get_units_for_calculation(request.file_type, request.quantity)
        
        # Content Extraction
        ce_cost = self.calculate_content_extraction(request.file_type, units, request.document_tier)
        
        # Field Extraction
        fe_input_tokens, fe_output_tokens, fe_cost = 0, 0, 0.0
        cached_tokens = 0
        if request.field_extraction_enabled:
            unit_defaults = model["tokens_per_unit"][self.get_unit_key(request.file_type)]
            cached_tokens = request.cached_input_tokens if request.cached_input_tokens is not None else int(
                units * (unit_defaults.get("cached_input") or 0)
            )
            fe_input_tokens, fe_output_tokens, fe_cost = self.calculate_field_extraction(
                request.file_type, units, model, request.deployment_type, cached_tokens
            )
        
        # Embeddings
        embeddings_tokens, embeddings_cost = 0, 0.0
        if request.embeddings_enabled:
            embeddings_tokens, embeddings_cost = self.calculate_embeddings(
                units, model, request.file_type, request.embeddings_model, request.deployment_type
            )
        
        # Contextualization - pass original quantity for text type
        ctx_tokens, ctx_cost = self.calculate_contextualization(
            request.file_type, units, model, 
            original_quantity=request.quantity if request.file_type == "text" else None,
            contextualization_tier=request.contextualization_tier,
        )
        
        # Total
        total_cost = ce_cost + fe_cost + embeddings_cost + ctx_cost
        total_tokens = fe_input_tokens + fe_output_tokens + embeddings_tokens + ctx_tokens
        
        return CostBreakdown(
            ce_cost=ce_cost,
            fe_cost=fe_cost,
            ctx_cost=ctx_cost,
            embeddings_cost=embeddings_cost,
            total_cost=total_cost,
            input_tokens=fe_input_tokens,
            output_tokens=fe_output_tokens,
            total_tokens=total_tokens,
            units=units,
            estimation_mode="default",
            confidence_note=(
                (
                    "Measured prebuilt-invoice sample baseline; cached tokens reflect repeated runs of the same invoice. "
                    "Other schemas and real invoice mixes may differ."
                    f" API: {model['document_benchmark'].get('apiVersion', INVOICE_BENCHMARK['apiVersion'])};"
                    f" region: {model['document_benchmark'].get('region', 'not recorded')}."
                    + (
                        " Cached-input counts were not consistently reported; zero cache is a planning assumption."
                        if model.get("document_benchmark", {}).get("perPage", {}).get("cached_input") is None else ""
                    )
                )
                if request.file_type == "document" and model.get("document_benchmark", {}).get("status") == "measured"
                else "MODERATE confidence - using default token estimates. "
                "For more accurate estimates, provide schema_config or "
                "usage_data from actual API calls."
            ),
            cached_input_tokens=cached_tokens,
            pricing_note=model.get("pricing_status", "Custom configured model rates"),
        )
    
    def explain_cost_drivers(self, request: ProcessingRequest, breakdown: CostBreakdown) -> str:
        """Generate natural language explanation of cost drivers
        
        Args:
            request: The processing request parameters
            breakdown: The cost breakdown results
            
        Returns:
            Natural language explanation string
        """
        model = self._request_model(request)
        unit_type = {
            "document": "pages",
            "text": "characters (converted to pages)",
            "image": "images",
            "audio": "minutes",
            "video": "minutes"
        }.get(request.file_type, "units")
        
        explanation = []
        explanation.append(f"Cost Analysis for {request.quantity:,.0f} {unit_type} using {request.model_name}")
        explanation.append("=" * 70)
        explanation.append("")
        explanation.append(f"Pricing: {breakdown.pricing_note}")
        explanation.append(f"Document tier: {request.document_tier}; contextualization: {request.contextualization_tier}")
        if request.document_tier.endswith("_sync") or (
            request.usage_data and (
                request.usage_data.document_pages_basic_sync or request.usage_data.document_pages_standard_sync
            )
        ):
            explanation.append(breakdown.confidence_note)
            explanation.append(f"Total Estimated Cost: ${breakdown.total_cost:.4f}")
            explanation.append("Field extraction, contextualization and embeddings: excluded (Sync)")
            return "\n".join(explanation)
        
        # Estimation mode warning
        if breakdown.estimation_mode == "schema_based":
            explanation.append("⚠️  ESTIMATION MODE: Schema-based (rough estimate)")
            explanation.append("    " + breakdown.confidence_note)
            explanation.append("")
        elif breakdown.estimation_mode == "usage_based":
            explanation.append("ESTIMATION MODE: Usage-based (measured token quantities)")
            explanation.append("    " + breakdown.confidence_note)
            explanation.append("")
        else:
            explanation.append("ℹ️  ESTIMATION MODE: Default estimates")
            explanation.append("    " + breakdown.confidence_note)
            explanation.append("")
        
        # Overall summary
        explanation.append(f"Total Estimated Cost: ${breakdown.total_cost:.4f}")
        explanation.append(f"Effective Units: {breakdown.units:.2f}")
        explanation.append(f"Total Tokens: {breakdown.total_tokens:,}")
        explanation.append("")
        
        # Component breakdown
        explanation.append("Cost Breakdown by Component:")
        explanation.append("-" * 70)
        
        # Content Extraction
        if breakdown.ce_cost > 0:
            percentage = (breakdown.ce_cost / breakdown.total_cost) * 100 if breakdown.total_cost > 0 else 0
            explanation.append(f"1. Content Extraction: ${breakdown.ce_cost:.4f} ({percentage:.1f}%)")
            explanation.append(f"   - Extracts raw content from {request.file_type} files")
            if request.file_type == "document":
                explanation.append(f"   - Selected tier: ${self._document_rate(request.document_tier):.2f} per 1,000 pages (usage counters may contain mixed tiers)")
            elif request.file_type == "audio":
                explanation.append(f"   - Charged at ${self.config['ce']['audio_per_minute']:.4f} per minute")
            elif request.file_type == "video":
                explanation.append(f"   - Charged at ${self.config['ce']['video_per_minute']:.4f} per minute")
            explanation.append("")
        
        # Field Extraction
        if breakdown.fe_cost > 0:
            percentage = (breakdown.fe_cost / breakdown.total_cost) * 100 if breakdown.total_cost > 0 else 0
            explanation.append(f"2. Field Extraction (AI Processing): ${breakdown.fe_cost:.4f} ({percentage:.1f}%)")
            explanation.append(f"   - Uses {request.model_name} ({model['class']} model)")
            explanation.append(f"   - Input tokens: {breakdown.input_tokens:,}")
            explanation.append(f"   - Cached input tokens (included in input): {breakdown.cached_input_tokens:,}")
            explanation.append(f"   - Output tokens: {breakdown.output_tokens:,}")
            
            rates = self._model_rates(model, request.deployment_type)
            explanation.append(f"   - Model rates (USD/M tokens; None = not provided): {rates}")
            explanation.append(f"   - Deployment: {request.deployment_type}")
            explanation.append("")
        
        # Embeddings
        if breakdown.embeddings_cost > 0:
            percentage = (breakdown.embeddings_cost / breakdown.total_cost) * 100 if breakdown.total_cost > 0 else 0
            explanation.append(f"3. Embeddings: ${breakdown.embeddings_cost:.4f} ({percentage:.1f}%)")
            explanation.append(f"   - Model: {request.embeddings_model}")
            embedding_config = self.config["embeddings"][request.embeddings_model]
            if request.deployment_type != "ptu":
                explanation.append(f"   - Rate: ${self._embedding_rate(request.embeddings_model, request.deployment_type):.6f} per 1K tokens")
            explanation.append("")
        
        # Contextualization
        if breakdown.ctx_cost > 0:
            percentage = (breakdown.ctx_cost / breakdown.total_cost) * 100 if breakdown.total_cost > 0 else 0
            rate = self._context_rate(request.contextualization_tier)
            ctx_tokens = int((breakdown.ctx_cost / rate) * 1_000_000)
            explanation.append(f"4. Contextualization: ${breakdown.ctx_cost:.4f} ({percentage:.1f}%)")
            explanation.append(f"   - Maintains document context and relationships")
            explanation.append(f"   - Tokens: {ctx_tokens:,}")
            explanation.append(f"   - {request.contextualization_tier} rate: ${rate:.2f} per million tokens")
            explanation.append("")
        
        # Recommendations for better estimates
        if breakdown.estimation_mode != "usage_based":
            explanation.append("Recommendations for Better Estimates:")
            explanation.append("-" * 70)
            explanation.append("To get more accurate cost estimates:")
            explanation.append("1. Run a small test batch (5-10 documents) through the API")
            explanation.append("2. Check the 'usage' object in the API response")
            explanation.append("3. Use the usage data with estimate_from_usage() method")
            explanation.append("")
            explanation.append("Example usage object from API:")
            explanation.append('  "usage": {')
            explanation.append('    "contextualizationToken": 2000,')
            explanation.append('    "tokens": {')
            explanation.append('      "gpt-4.1-input": 10400,')
            explanation.append('      "gpt-4.1-output": 360')
            explanation.append('    }')
            explanation.append('  }')
            explanation.append("")
        
        # Key cost drivers
        explanation.append("Key Cost Drivers:")
        explanation.append("-" * 70)
        
        drivers = []
        if breakdown.fe_cost > breakdown.total_cost * 0.3:
            drivers.append(f"• AI Model Selection: {request.model_name} is a {model['class']} model")
            drivers.append(f"  Consider using a 'mini' model for lower costs if appropriate")
        
        if request.deployment_type in ("data_zone", "datazone"):
            drivers.append("• Deployment Type: Data Zone; verify deployment-specific model rates")
        
        if request.embeddings_enabled:
            drivers.append(f"• Embeddings: Adding vector embeddings increases cost")
        
        drivers.append(f"• Volume: Processing {breakdown.units:.0f} effective units")
        
        if request.file_type == "video":
            drivers.append(f"• File Type: Video files have high token consumption")
        
        explanation.extend(drivers)
        explanation.append("")
        
        # Optimization tips
        explanation.append("Cost Optimization Tips:")
        explanation.append("-" * 70)
        if model["class"] == "regular":
            explanation.append("• Compare verified model rates and quality before choosing a mini model")
        if request.deployment_type == "data_zone":
            explanation.append("• Use Global or Regional deployment if data residency is not required")
        if request.embeddings_enabled:
            explanation.append("• Disable embeddings if vector search is not needed")
        explanation.append("• Process documents in batches to amortize fixed costs")
        explanation.append("• Use text file type when possible (free content extraction)")
        explanation.append("• Disable source grounding and confidence scores if not needed (~2x savings)")
        
        return "\n".join(explanation)
    
    def analyze_batch_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze a batch of processing results to calculate average costs per page
        
        Args:
            results: List of processing results, each containing:
                - file_name: str
                - file_type: str
                - pages: int (number of pages processed)
                - actual_input_tokens: int
                - actual_output_tokens: int
                - model_name: str
                - deployment_type: str
        
        Returns:
            Dictionary with analysis results
        """
        if not results:
            return {"error": "No results provided"}
        
        total_docs = len(results)
        documents = []
        for result in results:
            file_type = result.get("file_type", "document")
            pages = result.get("pages", 0)
            _nonnegative("pages", pages)
            usage = UsageData(
                input_tokens=result.get("actual_input_tokens", 0),
                output_tokens=result.get("actual_output_tokens", 0),
                cached_input_tokens=result.get("actual_cached_input_tokens", 0),
                contextualization_tokens=result.get("contextualization_tokens", 0),
                embedding_tokens=result.get("embedding_tokens", 0),
            )
            request = ProcessingRequest(
                file_type=file_type, quantity=result.get("quantity", pages),
                model_name=result.get("model_name", "gpt-4o"),
                deployment_type=result.get("deployment_type", "global"),
                document_tier=result.get("document_tier", "standard"),
                contextualization_tier=result.get("contextualization_tier", "standard"),
                model_rates=result.get("model_rates"),
                field_extraction_enabled=result.get("field_extraction_enabled", True),
                embeddings_enabled=result.get("embeddings_enabled", False),
                embeddings_model=result.get("embeddings_model", "text-embedding-3-small"),
                usage_data=usage,
            )
            breakdown = self.estimate_from_usage(request)
            input_tokens, output_tokens = breakdown.input_tokens, breakdown.output_tokens
            documents.append({
                "file_name": result.get("file_name", "unknown"), "pages": pages,
                "cost": breakdown.total_cost,
                "cost_per_page": breakdown.total_cost / pages if pages else 0,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "cached_input_tokens": breakdown.cached_input_tokens,
                "total_tokens": input_tokens + output_tokens,
                "tokens_per_page": (input_tokens + output_tokens) / pages if pages else 0,
                "pricing_note": breakdown.pricing_note,
            })

        total_pages = sum(d["pages"] for d in documents)
        total_input_tokens = sum(d["input_tokens"] for d in documents)
        total_output_tokens = sum(d["output_tokens"] for d in documents)
        total_cost = sum(d["cost"] for d in documents)
        # Calculate averages
        avg_cost_per_page = total_cost / total_pages if total_pages > 0 else 0
        avg_input_tokens_per_page = total_input_tokens / total_pages if total_pages > 0 else 0
        avg_output_tokens_per_page = total_output_tokens / total_pages if total_pages > 0 else 0
        avg_total_tokens_per_page = (total_input_tokens + total_output_tokens) / total_pages if total_pages > 0 else 0
        
        analysis = {
            "summary": {
                "total_documents": total_docs,
                "total_pages": total_pages,
                "total_cost": total_cost,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "total_cached_input_tokens": sum(d["cached_input_tokens"] for d in documents),
                "pricing_note": "Model rates use the public Azure OpenAI snapshot or caller overrides; unpublished rates require an override.",
            },
            "averages": {
                "cost_per_page": avg_cost_per_page,
                "cost_per_document": total_cost / total_docs if total_docs > 0 else 0,
                "input_tokens_per_page": avg_input_tokens_per_page,
                "output_tokens_per_page": avg_output_tokens_per_page,
                "total_tokens_per_page": avg_total_tokens_per_page,
                "pages_per_document": total_pages / total_docs if total_docs > 0 else 0
            },
            "per_document_breakdown": documents
        }
        
        return analysis
    
    def explain_batch_analysis(self, analysis: Dict[str, Any]) -> str:
        """Generate natural language explanation of batch analysis results
        
        Args:
            analysis: Dictionary containing batch analysis results
            
        Returns:
            Natural language explanation string
        """
        if "error" in analysis:
            return f"Error: {analysis['error']}"
        
        summary = analysis["summary"]
        averages = analysis["averages"]
        
        explanation = []
        explanation.append("Batch Processing Analysis")
        explanation.append("=" * 70)
        explanation.append("")
        
        # Summary
        explanation.append("Overall Summary:")
        explanation.append("  " + summary.get("pricing_note", ""))
        explanation.append(f"  • Processed {summary['total_documents']} documents")
        explanation.append(f"  • Total pages: {summary['total_pages']:,}")
        explanation.append(f"  • Total cost: ${summary['total_cost']:.2f}")
        explanation.append(f"  • Total tokens: {summary['total_tokens']:,}")
        explanation.append("")
        
        # Averages
        explanation.append("Average Costs:")
        explanation.append(f"  • Cost per page: ${averages['cost_per_page']:.4f}")
        explanation.append(f"  • Cost per document: ${averages['cost_per_document']:.2f}")
        explanation.append(f"  • Pages per document: {averages['pages_per_document']:.1f}")
        explanation.append("")
        
        explanation.append("Average Token Usage:")
        explanation.append(f"  • Input tokens per page: {averages['input_tokens_per_page']:.0f}")
        explanation.append(f"  • Output tokens per page: {averages['output_tokens_per_page']:.0f}")
        explanation.append(f"  • Total tokens per page: {averages['total_tokens_per_page']:.0f}")
        explanation.append("")
        
        # Cost drivers analysis
        explanation.append("Cost Driver Analysis:")
        explanation.append("-" * 70)
        
        # Find most/least expensive documents
        if analysis["per_document_breakdown"]:
            breakdown = analysis["per_document_breakdown"]
            most_expensive = max(breakdown, key=lambda x: x["cost_per_page"])
            least_expensive = min(breakdown, key=lambda x: x["cost_per_page"])
            
            explanation.append(f"Most expensive per page: {most_expensive['file_name']}")
            explanation.append(f"  • ${most_expensive['cost_per_page']:.4f}/page")
            explanation.append(f"  • {most_expensive['tokens_per_page']:.0f} tokens/page")
            explanation.append("")
            
            explanation.append(f"Least expensive per page: {least_expensive['file_name']}")
            explanation.append(f"  • ${least_expensive['cost_per_page']:.4f}/page")
            explanation.append(f"  • {least_expensive['tokens_per_page']:.0f} tokens/page")
            explanation.append("")
            
            # Variance analysis
            cost_variance = max(d["cost_per_page"] for d in breakdown) - min(d["cost_per_page"] for d in breakdown)
            explanation.append(f"Cost variance: ${cost_variance:.4f} per page")
            explanation.append("This variance is typically driven by:")
            explanation.append("  • Document complexity (tables, images, formatting)")
            explanation.append("  • Content density (text vs whitespace)")
            explanation.append("  • Schema complexity (number of fields extracted)")
            explanation.append("")
        
        # Projections
        explanation.append("Cost Projections:")
        explanation.append("-" * 70)
        for scale in [1000, 10000, 100000, 1000000]:
            projected_cost = averages['cost_per_page'] * scale
            explanation.append(f"  • {scale:,} pages: ${projected_cost:,.2f}")
        
        return "\n".join(explanation)


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(
        description="Azure AI Content Understanding Cost Estimator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Estimate cost for 1000 document pages (default estimation)
  python -m tools.cost_estimator estimate --file-type document --quantity 1000 --model gpt-4o
  
  # Estimate with schema configuration (rough estimate)
  python -m tools.cost_estimator estimate --file-type document --quantity 1000 \\
      --model gpt-4o-mini --schema-fields 10 --schema-complexity moderate
  
  # Estimate from actual usage data (most accurate)
  python -m tools.cost_estimator estimate-usage --input-tokens 1100000 --output-tokens 60000 \\
      --ctx-tokens 1000000 --pages 1000 --model gpt-4o-mini
  
  # Analyze batch processing results
  python -m tools.cost_estimator analyze --results-file batch_results.json
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Estimate command
    estimate_parser = subparsers.add_parser("estimate", help="Estimate cost before processing")
    estimate_parser.add_argument("--file-type", required=True, 
                                choices=["document", "text", "image", "audio", "video"],
                                help="Type of file to process")
    estimate_parser.add_argument("--quantity", type=float, required=True,
                                help="Quantity (pages, characters, images, or minutes)")
    estimate_parser.add_argument("--model", default="gpt-4o",
                                help="Model name (default: gpt-4o)")
    estimate_parser.add_argument("--deployment", default="global",
                                choices=["global", "regional", "data_zone", "datazone", "global_regional", "ptu"],
                                help="Deployment type (default: global)")
    estimate_parser.add_argument("--no-field-extraction", action="store_true",
                                help="Disable field extraction")
    estimate_parser.add_argument("--embeddings", action="store_true",
                                help="Enable embeddings")
    estimate_parser.add_argument("--embeddings-model", default="text-embedding-3-small",
                                help="Embeddings model (default: text-embedding-3-small)")
    # Schema-based estimation options
    estimate_parser.add_argument("--schema-fields", type=int, default=0,
                                help="Number of fields in schema (enables schema-based estimation)")
    estimate_parser.add_argument("--schema-complexity", default="moderate",
                                choices=["simple", "moderate", "complex"],
                                help="Schema complexity level")
    estimate_parser.add_argument("--source-grounding", action="store_true",
                                help="Enable source grounding")
    estimate_parser.add_argument("--confidence-scores", action="store_true",
                                help="Enable confidence scores")
    estimate_parser.add_argument("--json", action="store_true",
                                help="Output as JSON")
    
    # Estimate from usage command (recommended)
    usage_parser = subparsers.add_parser("estimate-usage", 
                                          help="Estimate from actual API usage data (recommended)")
    usage_parser.add_argument("--input-tokens", type=int, required=True,
                             help="Input tokens from API usage")
    usage_parser.add_argument("--output-tokens", type=int, required=True,
                             help="Output tokens from API usage")
    usage_parser.add_argument("--ctx-tokens", type=int, default=0,
                             help="Contextualization tokens from API usage")
    usage_parser.add_argument("--pages", type=int, default=0,
                             help="Number of document pages")
    usage_parser.add_argument("--model", default="gpt-4o",
                             help="Model name (default: gpt-4o)")
    usage_parser.add_argument("--deployment", default="global",
                             choices=["global", "regional", "data_zone", "datazone", "global_regional", "ptu"],
                             help="Deployment type (default: global)")
    usage_parser.add_argument("--scale-to", type=int, default=0,
                             help="Scale estimate to this many pages (0 = use provided pages)")
    usage_parser.add_argument("--json", action="store_true",
                             help="Output as JSON")
    usage_parser.add_argument("--file-type", default="document",
                              choices=["document", "image", "text", "audio", "video"])
    usage_parser.add_argument("--quantity", type=float,
                              help="Measured quantity; replaces --pages (minutes for audio/video)")
    usage_parser.add_argument("--no-field-extraction", action="store_true")
    usage_parser.add_argument("--embeddings", action="store_true")
    usage_parser.add_argument("--embeddings-model", default="text-embedding-3-small")
    usage_parser.add_argument("--embedding-tokens", type=int, default=0)

    for command_parser in (estimate_parser, usage_parser):
        command_parser.add_argument("--document-tier", default="standard",
                                    choices=["basic", "standard", "basic_sync", "standard_sync"],
                                    help="Basic/read or Standard/layout; Sync tiers are preview and CE-only")
        command_parser.add_argument("--contextualization-tier", default="standard",
                                    choices=["standard", "advanced"],
                                    help="Standard $1/M or advanced preview $3/M, independent of model")
        command_parser.add_argument("--cached-input-tokens", type=int, default=None,
                                    help="Cached subset of TOTAL input tokens (not additional input)")
        command_parser.add_argument("--input-rate", type=float, help="USD per million uncached input tokens")
        command_parser.add_argument("--cached-input-rate", type=float, help="USD per million cached input tokens")
        command_parser.add_argument("--output-rate", type=float, help="USD per million output tokens")
        command_parser.add_argument("--pricing-config",
                                    help="JSON pricing config (supports exact custom model IDs and rates)")
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze batch processing results")
    analyze_parser.add_argument("--results-file", required=True,
                               help="JSON file with batch processing results")
    analyze_parser.add_argument("--json", action="store_true",
                               help="Output as JSON instead of human-readable text")
    analyze_parser.add_argument("--pricing-config", help="JSON pricing config")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    config = None
    if args.pricing_config:
        with open(args.pricing_config, encoding="utf-8") as config_file:
            config = json.load(config_file)
    estimator = CostEstimator(config)
    model_rates = {
        key: value for key, value in (
            ("input_per_mtok", getattr(args, "input_rate", None)),
            ("cached_input_per_mtok", getattr(args, "cached_input_rate", None)),
            ("output_per_mtok", getattr(args, "output_rate", None)),
        ) if value is not None
    }
    
    if args.command == "estimate":
        # Create schema config if schema fields specified
        schema_config = None
        _nonnegative("schema_fields", args.schema_fields)
        if args.schema_fields > 0:
            schema_config = SchemaConfig(
                num_fields=args.schema_fields,
                field_complexity=args.schema_complexity,
                source_grounding_enabled=args.source_grounding,
                confidence_scores_enabled=args.confidence_scores
            )
        
        # Create request
        request = ProcessingRequest(
            file_type=args.file_type,
            quantity=args.quantity,
            model_name=args.model,
            deployment_type=args.deployment,
            field_extraction_enabled=not args.no_field_extraction,
            embeddings_enabled=args.embeddings,
            embeddings_model=args.embeddings_model,
            schema_config=schema_config,
            document_tier=args.document_tier,
            contextualization_tier=args.contextualization_tier,
            model_rates=model_rates,
            cached_input_tokens=args.cached_input_tokens,
        )
        
        # Calculate cost
        breakdown = estimator.estimate_cost(request)
        
        if args.json:
            output = {
                "request": {
                    "file_type": request.file_type,
                    "quantity": request.quantity,
                    "model_name": request.model_name,
                    "deployment_type": request.deployment_type,
                    "field_extraction_enabled": request.field_extraction_enabled,
                    "embeddings_enabled": request.embeddings_enabled,
                    "embeddings_model": request.embeddings_model,
                    "document_tier": request.document_tier,
                    "contextualization_tier": request.contextualization_tier,
                    "model_rates": request.model_rates,
                    "cached_input_tokens": request.cached_input_tokens,
                },
                "breakdown": asdict(breakdown)
            }
            print(json.dumps(output, indent=2))
        else:
            explanation = estimator.explain_cost_drivers(request, breakdown)
            print(explanation)
    
    elif args.command == "estimate-usage":
        # Create usage data
        _nonnegative("pages", args.pages)
        _nonnegative("scale_to", args.scale_to)
        measured_quantity = args.quantity if args.quantity is not None else args.pages
        _nonnegative("quantity", measured_quantity)
        ce_usage = {}
        if args.file_type == "document":
            ce_usage[f"document_pages_{args.document_tier}"] = measured_quantity
        elif args.file_type in ("audio", "video"):
            ce_usage[f"{args.file_type}_minutes"] = measured_quantity
        usage = UsageData(
            input_tokens=args.input_tokens,
            output_tokens=args.output_tokens,
            contextualization_tokens=args.ctx_tokens,
            cached_input_tokens=args.cached_input_tokens or 0,
            embedding_tokens=args.embedding_tokens,
            **ce_usage,
        )
        
        # Determine scale
        if args.scale_to and measured_quantity == 0:
            raise ValueError("Scaling requires a positive measured quantity")
        target_pages = args.scale_to if args.scale_to > 0 else measured_quantity
        scale_factor = target_pages / measured_quantity if measured_quantity > 0 else 1.0
        
        request = ProcessingRequest(
            file_type=args.file_type,
            quantity=target_pages,
            model_name=args.model,
            deployment_type=args.deployment,
            usage_data=usage,
            document_tier=args.document_tier,
            contextualization_tier=args.contextualization_tier,
            model_rates=model_rates,
            field_extraction_enabled=not args.no_field_extraction,
            embeddings_enabled=args.embeddings,
            embeddings_model=args.embeddings_model,
        )
        
        breakdown = estimator.estimate_from_usage(request, scale_factor=scale_factor)
        
        if args.json:
            output = {
                "usage_data": asdict(usage),
                "scale_factor": scale_factor,
                "target_pages": target_pages,
                "breakdown": asdict(breakdown)
            }
            print(json.dumps(output, indent=2))
        else:
            explanation = estimator.explain_cost_drivers(request, breakdown)
            print(explanation)
    
    elif args.command == "analyze":
        # Load results file
        results_path = Path(args.results_file)
        if not results_path.exists():
            print(f"Error: Results file not found: {args.results_file}")
            return
        
        with open(results_path, 'r') as f:
            results = json.load(f)
        
        # Analyze
        analysis = estimator.analyze_batch_results(results)
        
        if args.json:
            print(json.dumps(analysis, indent=2))
        else:
            explanation = estimator.explain_batch_analysis(analysis)
            print(explanation)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f"Error: {error}") from None
