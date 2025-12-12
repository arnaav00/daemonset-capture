"""
JSON Schema Inference from actual request/response data
"""

from typing import Any, Dict, List, Optional, Set, Union
from collections import defaultdict
import re


class SchemaInferrer:
    """
    Infers JSON schemas from actual data samples.
    
    Analyzes multiple samples to determine:
    - Data types (string, number, integer, boolean, array, object)
    - Required vs optional fields
    - Nested structures
    - Array item types
    - Enums for fields with limited values
    """
    
    def infer_schema(
        self,
        samples: List[Any],
        max_enum_values: int = 10
    ) -> Dict[str, Any]:
        """
        Infer JSON schema from multiple samples.
        
        Args:
            samples: List of data samples (dicts, lists, or primitives)
            max_enum_values: Max unique values to consider as enum
            
        Returns:
            JSON Schema dict
        """
        if not samples:
            return {"type": "object"}
        
        # Filter out None samples
        samples = [s for s in samples if s is not None]
        
        if not samples:
            return {"type": "object"}
        
        # Determine primary type
        sample_types = [self._get_type(s) for s in samples]
        primary_type = self._get_most_common_type(sample_types)
        
        if primary_type == "object":
            return self._infer_object_schema(samples, max_enum_values)
        elif primary_type == "array":
            return self._infer_array_schema(samples, max_enum_values)
        else:
            return self._infer_primitive_schema(samples, primary_type, max_enum_values)
    
    def _get_type(self, value: Any) -> str:
        """Get JSON schema type for a value"""
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "number"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, list):
            return "array"
        elif isinstance(value, dict):
            return "object"
        else:
            return "string"
    
    def _get_most_common_type(self, types: List[str]) -> str:
        """Get most common type from list"""
        type_counts = defaultdict(int)
        for t in types:
            type_counts[t] += 1
        
        # Prioritize object and array types
        if type_counts.get("object", 0) > 0:
            return "object"
        if type_counts.get("array", 0) > 0:
            return "array"
        
        # Return most common
        return max(type_counts.items(), key=lambda x: x[1])[0]
    
    def _infer_object_schema(
        self,
        samples: List[Dict],
        max_enum_values: int
    ) -> Dict[str, Any]:
        """Infer schema for object type"""
        # Only process dict samples
        samples = [s for s in samples if isinstance(s, dict)]
        
        if not samples:
            return {"type": "object"}
        
        # Collect all field names
        all_fields = set()
        for sample in samples:
            all_fields.update(sample.keys())
        
        # Analyze each field
        properties = {}
        required_fields = []
        
        for field in all_fields:
            # Collect values for this field
            field_values = []
            field_count = 0
            
            for sample in samples:
                if field in sample:
                    field_values.append(sample[field])
                    field_count += 1
            
            # Determine if required (present in >80% of samples)
            if field_count / len(samples) > 0.8:
                required_fields.append(field)
            
            # Infer schema for this field
            if field_values:
                properties[field] = self.infer_schema(field_values, max_enum_values)
        
        schema = {
            "type": "object",
            "properties": properties
        }
        
        if required_fields:
            schema["required"] = sorted(required_fields)
        
        return schema
    
    def _infer_array_schema(
        self,
        samples: List[List],
        max_enum_values: int
    ) -> Dict[str, Any]:
        """Infer schema for array type"""
        # Only process list samples
        samples = [s for s in samples if isinstance(s, list)]
        
        if not samples:
            return {"type": "array", "items": {}}
        
        # Collect all items from all arrays
        all_items = []
        for sample in samples:
            all_items.extend(sample)
        
        # Infer schema for items
        if all_items:
            items_schema = self.infer_schema(all_items, max_enum_values)
        else:
            items_schema = {}
        
        return {
            "type": "array",
            "items": items_schema
        }
    
    def _infer_primitive_schema(
        self,
        samples: List[Any],
        primary_type: str,
        max_enum_values: int
    ) -> Dict[str, Any]:
        """Infer schema for primitive types"""
        schema = {"type": primary_type}
        
        # Check for enum pattern (limited unique values)
        if primary_type in ["string", "integer", "number"]:
            unique_values = set(samples)
            
            if 1 < len(unique_values) <= max_enum_values:
                schema["enum"] = sorted(list(unique_values))
        
        # Add format hints for strings
        if primary_type == "string" and samples:
            schema["format"] = self._detect_string_format(samples[0])
        
        return schema
    
    def _detect_string_format(self, value: str) -> Optional[str]:
        """Detect common string formats"""
        if not isinstance(value, str):
            return None
        
        # Email
        if re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', value):
            return "email"
        
        # UUID
        if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', value, re.IGNORECASE):
            return "uuid"
        
        # Date-time
        if re.match(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', value):
            return "date-time"
        
        # Date
        if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
            return "date"
        
        # URL
        if value.startswith(('http://', 'https://')):
            return "uri"
        
        return None
    
    def select_best_example(
        self,
        samples: List[Any],
        prefer_populated: bool = True
    ) -> Any:
        """
        Select the best example from samples.
        
        Args:
            samples: List of samples
            prefer_populated: Prefer examples with more fields
            
        Returns:
            Best example
        """
        if not samples:
            return None
        
        if not prefer_populated or not isinstance(samples[0], dict):
            return samples[0]
        
        # Score each sample by number of populated fields
        def score_sample(sample):
            if not isinstance(sample, dict):
                return 0
            
            score = 0
            for value in sample.values():
                if value is not None and value != "" and value != []:
                    score += 1
                    # Bonus for nested objects
                    if isinstance(value, (dict, list)):
                        score += 0.5
            return score
        
        # Return sample with highest score
        return max(samples, key=score_sample)


# Singleton instance
_schema_inferrer = SchemaInferrer()


def get_schema_inferrer() -> SchemaInferrer:
    """Get schema inferrer instance"""
    return _schema_inferrer


