"""URL parameterization service"""

import re
from typing import List, Dict, Set, Tuple
from urllib.parse import urlparse
from collections import defaultdict


class URLParameterizer:
    """
    Service to parameterize URL paths by detecting and replacing
    dynamic segments with parameter placeholders.
    """
    
    # Common patterns
    UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    NUMERIC_PATTERN = re.compile(r'^\d+$')
    PREFIXED_ID_PATTERN = re.compile(r'^([a-z]{2,5})_([a-z0-9]+)$', re.IGNORECASE)
    HEX_PATTERN = re.compile(r'^[0-9a-f]{16,}$', re.IGNORECASE)
    
    def __init__(self, threshold: float = 0.8):
        """
        Initialize parameterizer.
        
        Args:
            threshold: Minimum ratio of values that must match a pattern (0.8 = 80%)
        """
        self.threshold = threshold
    
    def parameterize_url(self, url: str) -> Tuple[str, str]:
        """
        Parameterize a single URL.
        
        Args:
            url: Full URL to parameterize
        
        Returns:
            Tuple of (base_url, parameterized_path)
        """
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path
        
        # For single URL, we can't detect patterns, so use heuristics
        segments = [s for s in path.split('/') if s]
        parameterized_segments = []
        
        for segment in segments:
            if self.UUID_PATTERN.match(segment):
                parameterized_segments.append('{uuid}')
            elif self.NUMERIC_PATTERN.match(segment):
                parameterized_segments.append('{id}')
            elif self.HEX_PATTERN.match(segment):
                parameterized_segments.append('{hash}')
            elif match := self.PREFIXED_ID_PATTERN.match(segment):
                prefix = match.group(1)
                parameterized_segments.append(f'{{{prefix}_id}}')
            else:
                parameterized_segments.append(segment)
        
        parameterized_path = '/' + '/'.join(parameterized_segments) if parameterized_segments else '/'
        
        return base_url, parameterized_path
    
    def parameterize_urls_batch(self, urls: List[str]) -> Dict[str, Tuple[str, str]]:
        """
        Parameterize a batch of URLs using pattern detection across all URLs.
        
        Args:
            urls: List of URLs to parameterize
        
        Returns:
            Dictionary mapping original URL to (base_url, parameterized_path)
        """
        if not urls:
            return {}
        
        # Group URLs by base URL and path structure
        url_groups = defaultdict(list)
        parsed_urls = {}
        
        for url in urls:
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            path = parsed.path
            segments = tuple(s for s in path.split('/') if s)
            
            parsed_urls[url] = (base_url, path, segments)
            # Group by base_url and number of segments
            url_groups[(base_url, len(segments))].append(url)
        
        # Analyze each group to find parameter positions
        result = {}
        
        for (base_url, segment_count), group_urls in url_groups.items():
            if segment_count == 0:
                # Root path
                for url in group_urls:
                    result[url] = (base_url, '/')
                continue
            
            # Collect values at each position
            position_values = defaultdict(set)
            for url in group_urls:
                _, _, segments = parsed_urls[url]
                for i, segment in enumerate(segments):
                    position_values[i].add(segment)
            
            # Determine which positions should be parameterized
            position_types = {}
            for position, values in position_values.items():
                if len(values) == 1:
                    # Static segment
                    position_types[position] = ('static', list(values)[0])
                else:
                    # Analyze values to determine type
                    position_types[position] = self._determine_parameter_type(values)
            
            # Apply parameterization to each URL in the group
            for url in group_urls:
                base, path, segments = parsed_urls[url]
                parameterized_segments = []
                
                for i, segment in enumerate(segments):
                    param_type, param_name = position_types[i]
                    if param_type == 'static':
                        parameterized_segments.append(segment)
                    else:
                        parameterized_segments.append(f'{{{param_name}}}')
                
                parameterized_path = '/' + '/'.join(parameterized_segments)
                result[url] = (base_url, parameterized_path)
        
        return result
    
    def _determine_parameter_type(self, values: Set[str]) -> Tuple[str, str]:
        """
        Determine the parameter type based on values at a position.
        
        Args:
            values: Set of values observed at this position
        
        Returns:
            Tuple of (type, parameter_name)
        """
        total_count = len(values)
        
        # Check UUID pattern
        uuid_count = sum(1 for v in values if self.UUID_PATTERN.match(v))
        if uuid_count / total_count >= self.threshold:
            return ('param', 'uuid')
        
        # Check numeric pattern
        numeric_count = sum(1 for v in values if self.NUMERIC_PATTERN.match(v))
        if numeric_count / total_count >= self.threshold:
            return ('param', 'id')
        
        # Check hex pattern
        hex_count = sum(1 for v in values if self.HEX_PATTERN.match(v))
        if hex_count / total_count >= self.threshold:
            return ('param', 'hash')
        
        # Check prefixed ID pattern
        prefixed_matches = [self.PREFIXED_ID_PATTERN.match(v) for v in values]
        valid_prefixed = [m for m in prefixed_matches if m]
        if len(valid_prefixed) / total_count >= self.threshold:
            # Use the most common prefix
            prefixes = [m.group(1) for m in valid_prefixed]
            most_common_prefix = max(set(prefixes), key=prefixes.count)
            return ('param', f'{most_common_prefix}_id')
        
        # Default: generic parameter
        return ('param', 'param')
    
    def extract_path_pattern(self, url: str) -> str:
        """
        Extract parameterized path pattern from a URL.
        
        Args:
            url: URL to extract pattern from
        
        Returns:
            Parameterized path pattern
        """
        _, parameterized_path = self.parameterize_url(url)
        return parameterized_path
    
    def group_by_pattern(self, urls: List[str]) -> Dict[str, List[str]]:
        """
        Group URLs by their parameterized pattern.
        
        Args:
            urls: List of URLs to group
        
        Returns:
            Dictionary mapping pattern to list of URLs
        """
        parameterized = self.parameterize_urls_batch(urls)
        pattern_groups = defaultdict(list)
        
        for url, (base_url, path) in parameterized.items():
            full_pattern = f"{base_url}{path}"
            pattern_groups[full_pattern].append(url)
        
        return dict(pattern_groups)


# Singleton instance
_url_parameterizer = URLParameterizer()


def get_url_parameterizer() -> URLParameterizer:
    """Get the URL parameterizer instance"""
    return _url_parameterizer

