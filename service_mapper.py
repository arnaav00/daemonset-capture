#!/usr/bin/env python3
"""
Service mapping and configuration management
"""

import json
import os
import logging
import time
from typing import Dict, Optional, Tuple
from threading import Lock

logger = logging.getLogger(__name__)


class ServiceMapper:
    """Manages service to appId/instanceId mappings"""
    
    def __init__(self, config_path: str = "/etc/traffic-monitor/service_config.json"):
        self.config_path = config_path
        # Use a writable path for saving mappings (ConfigMap is read-only)
        self.write_path = "/tmp/traffic-monitor-service-config.json"
        self.config = {}
        self.config_lock = Lock()
        try:
            self._load_config()
        except Exception as e:
            logger.error(f"Critical error in _load_config, using defaults: {e}")
            self.config = {
                "apiKey": None,
                "autoOnboardNewServices": False,
                "apisecUrl": "https://api.apisecapps.com",
                "serviceMappings": {}
            }
    
    def _load_config(self):
        """Load configuration from file (reads from ConfigMap, can save to writable path)"""
        self.config = {}
        
        # First try to load from ConfigMap (read-only)
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config_content = f.read()
                    logger.info(f"Reading config from {self.config_path}, length: {len(config_content)} chars")
                    self.config = json.loads(config_content)
                    logger.info(f"✓ Loaded service configuration from {self.config_path}")
                    logger.info(f"  apiKey present: {bool(self.config.get('apiKey'))}")
                    logger.info(f"  autoOnboardNewServices: {self.config.get('autoOnboardNewServices', False)}")
                    logger.info(f"  serviceMappings count: {len(self.config.get('serviceMappings', {}))}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error in {self.config_path} at line {e.lineno}, col {e.colno}: {e.msg}")
                logger.error(f"Content snippet around error: {config_content[max(0, e.pos-50):e.pos+50]}")
                # Don't raise - fall through to use defaults
                self.config = {}
            except Exception as e:
                logger.error(f"Error loading config from {self.config_path}: {e}")
                # Don't raise - fall through to use defaults
                self.config = {}
        
        # Also try to load from writable path (may have mappings saved there)
        if os.path.exists(self.write_path):
            try:
                with open(self.write_path, 'r') as f:
                    saved_content = f.read()
                    logger.debug(f"Reading saved config from {self.write_path}, length: {len(saved_content)} chars")
                    saved_config = json.loads(saved_content)
                    logger.info(f"✓ Loaded saved mappings from {self.write_path}")
                    # Merge saved mappings into config (saved mappings take precedence)
                    if "serviceMappings" in saved_config:
                        if "serviceMappings" not in self.config:
                            self.config["serviceMappings"] = {}
                        before_count = len(self.config["serviceMappings"])
                        self.config["serviceMappings"].update(saved_config["serviceMappings"])
                        after_count = len(self.config["serviceMappings"])
                        logger.info(f"  Merged mappings: {after_count - before_count} new mappings added")
            except json.JSONDecodeError as e:
                logger.warning(f"Corrupted JSON in saved config file {self.write_path} at line {e.lineno}, col {e.colno}: {e.msg}")
                logger.warning(f"  Attempting to backup and recreate the file...")
                try:
                    # Backup corrupted file
                    backup_path = f"{self.write_path}.backup.{int(time.time())}"
                    if os.path.exists(self.write_path):
                        os.rename(self.write_path, backup_path)
                        logger.info(f"  Backed up corrupted file to {backup_path}")
                except Exception as backup_error:
                    logger.warning(f"  Could not backup file: {backup_error}")
                # Continue without loading saved config
            except Exception as e:
                logger.warning(f"Could not load saved config from {self.write_path}: {e}")
        
        # If no config found, use defaults
        if not self.config:
            logger.warning("No config loaded, using defaults")
            self.config = {
                "apiKey": None,
                "autoOnboardNewServices": False,
                "apisecUrl": "https://api.apisecapps.com",
                "serviceMappings": {}
            }
    
    def _save_config(self):
        """Save configuration to writable path (ConfigMap is read-only, so save to /tmp)"""
        try:
            os.makedirs(os.path.dirname(self.write_path), exist_ok=True)
            # Save only the serviceMappings to the writable path (merge with existing saved mappings)
            saved_data = {"serviceMappings": self.config.get("serviceMappings", {})}
            if os.path.exists(self.write_path):
                try:
                    with open(self.write_path, 'r') as f:
                        existing = json.load(f)
                        if "serviceMappings" in existing:
                            saved_data["serviceMappings"].update(existing["serviceMappings"])
                except:
                    pass
            with open(self.write_path, 'w') as f:
                json.dump(saved_data, f, indent=2)
            logger.debug(f"Saved service mappings to {self.write_path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def get_api_key(self) -> Optional[str]:
        """Get the top-level API key"""
        with self.config_lock:
            api_key = self.config.get("apiKey")
            if api_key:
                # Strip whitespace and newlines
                api_key = str(api_key).strip()
                if api_key:
                    return api_key
            return None
    
    def get_service_mapping(self, service_name: str) -> Optional[Dict[str, Optional[str]]]:
        """
        Get appId and instanceId for a service (apiKey is top-level)
        
        Returns:
            Dict with appId, instanceId, apiKey keys, or None if not configured
        """
        with self.config_lock:
            api_key = self.config.get("apiKey")
            if not api_key:
                return None  # No API key configured
            
            # Reload config from disk to get latest mappings (in case another thread updated it)
            try:
                # Reload from ConfigMap
                if os.path.exists(self.config_path):
                    with open(self.config_path, 'r') as f:
                        current_config = json.load(f)
                        # Preserve API key and other settings
                        api_key_preserved = self.config.get("apiKey")
                        auto_onboard_preserved = self.config.get("autoOnboardNewServices")
                        apisec_url_preserved = self.config.get("apisecUrl")
                        self.config = current_config
                        # Restore settings from ConfigMap
                        if api_key_preserved:
                            self.config["apiKey"] = api_key_preserved
                        if auto_onboard_preserved is not None:
                            self.config["autoOnboardNewServices"] = auto_onboard_preserved
                        if apisec_url_preserved:
                            self.config["apisecUrl"] = apisec_url_preserved
                
                # Reload saved mappings from writable path
                if os.path.exists(self.write_path):
                    with open(self.write_path, 'r') as f:
                        saved_config = json.load(f)
                        if "serviceMappings" in saved_config:
                            if "serviceMappings" not in self.config:
                                self.config["serviceMappings"] = {}
                            self.config["serviceMappings"].update(saved_config["serviceMappings"])
            except Exception as e:
                logger.debug(f"Could not reload config: {e}")
            
            mapping = self.config.get("serviceMappings", {}).get(service_name)
            if mapping and mapping.get("appId") and mapping.get("instanceId"):
                # Add apiKey to mapping (from top-level)
                result = mapping.copy()
                result["apiKey"] = api_key
                return result
            return None
    
    def set_service_mapping(
        self,
        service_name: str,
        app_id: str,
        instance_id: str
    ):
        """Set mapping for a service (apiKey is top-level, not per-service)"""
        with self.config_lock:
            if "serviceMappings" not in self.config:
                self.config["serviceMappings"] = {}
            
            self.config["serviceMappings"][service_name] = {
                "appId": app_id,
                "instanceId": instance_id
            }
            self._save_config()
            logger.info(f"Updated mapping for service '{service_name}': appId={app_id}, instanceId={instance_id}")
    
    def set_api_key(self, api_key: str):
        """Set the top-level API key"""
        with self.config_lock:
            self.config["apiKey"] = api_key
            self._save_config()
            logger.info("Updated top-level API key")
    
    def is_auto_onboard_enabled(self) -> bool:
        """Check if auto-onboarding is enabled"""
        return self.config.get("autoOnboardNewServices", False)
    
    def get_apisec_url(self) -> str:
        """Get the APISec API URL"""
        return self.config.get("apisecUrl", "https://api.apisecapps.com")
    
    def list_services(self) -> list:
        """List all configured services"""
        return list(self.config.get("serviceMappings", {}).keys())
    
    def is_service_configured(self, service_name: str) -> bool:
        """Check if a service is fully configured (has appId, instanceId and top-level apiKey exists)"""
        api_key = self.get_api_key()
        if not api_key:
            return False
        mapping = self.get_service_mapping(service_name)
        return mapping is not None
    
    def clear_saved_mappings(self):
        """Clear saved service mappings from disk"""
        try:
            if os.path.exists(self.write_path):
                backup_path = f"{self.write_path}.backup.{int(time.time())}"
                os.rename(self.write_path, backup_path)
                logger.info(f"Backed up and cleared saved mappings: {backup_path}")
            # Also clear from memory
            if "serviceMappings" in self.config:
                self.config["serviceMappings"] = {}
            logger.info("Cleared all saved service mappings")
        except Exception as e:
            logger.error(f"Error clearing saved mappings: {e}")

