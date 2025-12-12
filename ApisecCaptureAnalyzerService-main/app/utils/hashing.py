"""Hashing utilities for creating signatures"""

import hashlib
import json
from typing import Any, Dict, List, Set


def hash_string(value: str) -> str:
    """Create SHA256 hash of a string"""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def normalize_json_structure(data: Any, depth: int = 0, max_depth: int = 5) -> Dict[str, Any]:
    """
    Extract the structure of JSON data, replacing values with their types.
    
    Args:
        data: The JSON data to normalize
        depth: Current recursion depth
        max_depth: Maximum depth to traverse
    
    Returns:
        Normalized structure with types instead of values
    """
    if depth > max_depth:
        return {"_type": "max_depth_reached"}
    
    if data is None:
        return {"_type": "null"}
    elif isinstance(data, bool):
        return {"_type": "boolean"}
    elif isinstance(data, int):
        return {"_type": "integer"}
    elif isinstance(data, float):
        return {"_type": "number"}
    elif isinstance(data, str):
        return {"_type": "string"}
    elif isinstance(data, list):
        if len(data) == 0:
            return {"_type": "array", "_items": []}
        # Sample first few items to get structure
        sample_size = min(3, len(data))
        items = [normalize_json_structure(data[i], depth + 1, max_depth) for i in range(sample_size)]
        return {"_type": "array", "_items": items}
    elif isinstance(data, dict):
        normalized = {}
        for key, value in data.items():
            normalized[key] = normalize_json_structure(value, depth + 1, max_depth)
        return {"_type": "object", "_fields": normalized}
    else:
        return {"_type": "unknown"}


def hash_json_structure(data: Any) -> str:
    """
    Create a hash of the JSON structure (not values).
    
    Args:
        data: The JSON data to hash
    
    Returns:
        Hash string representing the structure
    """
    normalized = normalize_json_structure(data)
    # Sort keys for consistent hashing
    json_str = json.dumps(normalized, sort_keys=True)
    return hash_string(json_str)


def extract_field_names(data: Any, prefix: str = "") -> Set[str]:
    """
    Extract all field names from a JSON structure.
    
    Args:
        data: The JSON data
        prefix: Current path prefix
    
    Returns:
        Set of field names (including nested paths with dot notation)
    """
    fields = set()
    
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{prefix}.{key}" if prefix else key
            fields.add(current_path)
            fields.update(extract_field_names(value, current_path))
    elif isinstance(data, list) and len(data) > 0:
        # Use first item as representative
        fields.update(extract_field_names(data[0], prefix))
    
    return fields


def calculate_json_depth(data: Any, current_depth: int = 0) -> int:
    """
    Calculate the maximum depth of a JSON structure.
    
    Args:
        data: The JSON data
        current_depth: Current depth level
    
    Returns:
        Maximum depth
    """
    if isinstance(data, dict):
        if not data:
            return current_depth
        return max(calculate_json_depth(v, current_depth + 1) for v in data.values())
    elif isinstance(data, list):
        if not data:
            return current_depth
        return max(calculate_json_depth(item, current_depth + 1) for item in data)
    else:
        return current_depth

