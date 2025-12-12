"""Similarity calculation utilities"""

from typing import Dict, Set, Any
import math


def jaccard_similarity(set1: Set[Any], set2: Set[Any]) -> float:
    """
    Calculate Jaccard similarity between two sets.
    
    Args:
        set1: First set
        set2: Second set
    
    Returns:
        Similarity score between 0 and 1
    """
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    
    return intersection / union if union > 0 else 0.0


def cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
    """
    Calculate cosine similarity between two sparse vectors represented as dicts.
    
    Args:
        vec1: First vector
        vec2: Second vector
    
    Returns:
        Similarity score between 0 and 1
    """
    if not vec1 or not vec2:
        return 0.0
    
    # Get common keys
    common_keys = set(vec1.keys()).intersection(set(vec2.keys()))
    
    if not common_keys:
        return 0.0
    
    # Calculate dot product
    dot_product = sum(vec1[key] * vec2[key] for key in common_keys)
    
    # Calculate magnitudes
    magnitude1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
    magnitude2 = math.sqrt(sum(v ** 2 for v in vec2.values()))
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)


def string_similarity(str1: str, str2: str) -> float:
    """
    Calculate similarity between two strings using longest common subsequence.
    
    Args:
        str1: First string
        str2: Second string
    
    Returns:
        Similarity score between 0 and 1
    """
    if str1 == str2:
        return 1.0
    if not str1 or not str2:
        return 0.0
    
    # Simple character-based Jaccard similarity
    set1 = set(str1.lower())
    set2 = set(str2.lower())
    
    return jaccard_similarity(set1, set2)


def dict_similarity(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> float:
    """
    Calculate similarity between two dictionaries based on key-value pairs.
    
    Args:
        dict1: First dictionary
        dict2: Second dictionary
    
    Returns:
        Similarity score between 0 and 1
    """
    if dict1 == dict2:
        return 1.0
    if not dict1 or not dict2:
        return 0.0
    
    # Key similarity
    keys1 = set(dict1.keys())
    keys2 = set(dict2.keys())
    key_sim = jaccard_similarity(keys1, keys2)
    
    # Value similarity for common keys
    common_keys = keys1.intersection(keys2)
    if not common_keys:
        return key_sim * 0.5  # Only key similarity matters
    
    value_matches = sum(1 for key in common_keys if dict1[key] == dict2[key])
    value_sim = value_matches / len(common_keys)
    
    # Combine key and value similarity
    return (key_sim * 0.6) + (value_sim * 0.4)


def path_similarity(path1: str, path2: str) -> float:
    """
    Calculate similarity between two URL paths.
    
    Args:
        path1: First path (e.g., /api/v1/users/123)
        path2: Second path (e.g., /api/v1/users/456)
    
    Returns:
        Similarity score between 0 and 1
    """
    if path1 == path2:
        return 1.0
    
    # Split into segments
    segments1 = [s for s in path1.split('/') if s]
    segments2 = [s for s in path2.split('/') if s]
    
    if not segments1 or not segments2:
        return 0.0
    
    # Calculate segment-wise similarity
    min_len = min(len(segments1), len(segments2))
    max_len = max(len(segments1), len(segments2))
    
    matching_segments = sum(
        1 for i in range(min_len) 
        if segments1[i] == segments2[i]
    )
    
    # Length penalty
    length_similarity = min_len / max_len
    
    # Position-weighted matching
    position_similarity = matching_segments / max_len
    
    return (position_similarity * 0.7) + (length_similarity * 0.3)

