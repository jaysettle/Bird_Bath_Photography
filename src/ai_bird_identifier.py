#!/usr/bin/env python3
"""
AI Bird Species Identifier using OpenAI Vision API
Part of 30-Day Improvement Plan - Day 1
"""

import os
import json
import base64
import logging
from datetime import datetime
from pathlib import Path
import requests
from typing import Dict, Optional, List

from .logger import get_logger

logger = get_logger(__name__)

class AIBirdIdentifier:
    """Identifies bird species using OpenAI Vision API"""
    
    def __init__(self, config: dict):
        """Initialize with OpenAI API key from config"""
        self.api_key = config.get('openai', {}).get('api_key')
        if not self.api_key:
            logger.warning("OpenAI API key not found in config")
            self.enabled = False
        else:
            self.enabled = True
            
        # Rate limiting: 2 minutes between API calls
        self.min_time_between_calls = 120  # seconds
        self.last_api_call_time = 0
        
        # Create species database file if it doesn't exist
        self.db_path = Path(__file__).parent.parent / "species_database.json"
        if not self.db_path.exists():
            self.db_path.write_text(json.dumps({
                "species": {},
                "sightings": [],
                "daily_stats": {}
            }, indent=2))
            
        self.load_database()
        
    def load_database(self):
        """Load species database"""
        try:
            with open(self.db_path, 'r') as f:
                self.database = json.load(f)
                # Ensure daily_stats exists
                if "daily_stats" not in self.database:
                    self.database["daily_stats"] = {}
        except Exception as e:
            logger.error(f"Error loading species database: {e}")
            self.database = {"species": {}, "sightings": [], "daily_stats": {}}
    
    def save_database(self):
        """Save species database"""
        try:
            with open(self.db_path, 'w') as f:
                json.dump(self.database, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving species database: {e}")
            
    def increment_daily_count(self):
        """Increment today's API call count"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.database["daily_stats"]:
            self.database["daily_stats"][today] = 0
        self.database["daily_stats"][today] += 1
        self.save_database()
        
    def get_daily_count(self):
        """Get today's API call count"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.database["daily_stats"].get(today, 0)
    
    def encode_image(self, image_path: str) -> Optional[str]:
        """Encode image to base64"""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encoding image: {e}")
            return None
    
    def identify_bird(self, image_path: str) -> Optional[Dict]:
        """Identify bird species in image"""
        logger.info(f"Starting bird identification for: {image_path}")
        
        if not self.enabled:
            logger.warning("AI Bird Identifier is disabled - no API key found")
            return None
        
        # Check rate limiting
        import time
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call_time
        
        if time_since_last_call < self.min_time_between_calls:
            wait_time = self.min_time_between_calls - time_since_last_call
            logger.info(f"Rate limit active: Skipping API call. Next call allowed in {wait_time:.0f} seconds")
            return {
                "identified": False,
                "rate_limited": True,
                "wait_time": wait_time,
                "reason": f"Rate limit: Please wait {wait_time:.0f} seconds before next identification"
            }
            
        # Encode image
        logger.debug("Encoding image to base64...")
        base64_image = self.encode_image(image_path)
        if not base64_image:
            logger.error("Failed to encode image")
            return None
        
        logger.debug(f"Image encoded, size: {len(base64_image)} characters")
        
        try:
            logger.debug("Preparing OpenAI API request...")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """Analyze this image and identify the bird species. 
                                Provide a JSON response with:
                                {
                                    "identified": true/false,
                                    "species_common": "Common name",
                                    "species_scientific": "Scientific name",
                                    "confidence": 0.0-1.0,
                                    "characteristics": ["list", "of", "visible", "features"],
                                    "behavior": "observed behavior if any",
                                    "conservation_status": "LC/NT/VU/EN/CR/EW/EX/DD/NE",
                                    "fun_fact": "interesting fact about this species"
                                }
                                If no bird is detected, set identified to false."""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 500
            }
            
            logger.debug("Sending request to OpenAI API...")
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            # Update last API call time immediately after making the request
            self.last_api_call_time = time.time()
            
            logger.debug(f"OpenAI API response status: {response.status_code}")
            
            if response.status_code == 200:
                logger.debug("Successfully received response from OpenAI")
                # Increment daily count on successful API call
                self.increment_daily_count()
                result = response.json()
                content = result['choices'][0]['message']['content']
                logger.debug(f"AI response content: {content[:200]}...")
                
                # Parse JSON from response
                try:
                    # Extract JSON from the response
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        logger.debug("Found JSON in response, parsing...")
                        bird_data = json.loads(json_match.group())
                        logger.info(f"Parsed bird data: {bird_data}")
                        
                        if bird_data.get('identified'):
                            # Record sighting
                            logger.info("Bird identified! Recording sighting...")
                            self.record_sighting(bird_data, image_path)
                            logger.info(f"✅ SUCCESS: Identified {bird_data.get('species_common')} "
                                      f"(confidence: {bird_data.get('confidence', 0):.2f})")
                        else:
                            logger.info("No bird identified in image")
                        
                        return bird_data
                    else:
                        logger.error("No JSON found in AI response")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse AI response JSON: {e}")
                    logger.error(f"Raw content: {content}")
                    
            else:
                logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"Error identifying bird: {e}")
            
        return None
    
    def record_sighting(self, bird_data: Dict, image_path: str):
        """Record bird sighting in database"""
        logger.debug(f"Recording sighting for: {bird_data}")
        species_key = bird_data.get('species_scientific', 'unknown')
        
        # Update species info if new or more detailed
        if species_key not in self.database['species']:
            self.database['species'][species_key] = {
                'common_name': bird_data.get('species_common'),
                'scientific_name': bird_data.get('species_scientific'),
                'conservation_status': bird_data.get('conservation_status'),
                'characteristics': bird_data.get('characteristics', []),
                'fun_facts': [bird_data.get('fun_fact')] if bird_data.get('fun_fact') else [],
                'first_seen': datetime.now().isoformat(),
                'sighting_count': 0,
                'last_photo': image_path,
                'photo_gallery': [image_path]  # New: Store multiple photos
            }
        else:
            # Update last photo and add to gallery for existing species
            self.database['species'][species_key]['last_photo'] = image_path
            
            # Add to photo gallery (keep last 10 photos per species)
            if 'photo_gallery' not in self.database['species'][species_key]:
                self.database['species'][species_key]['photo_gallery'] = []
            
            gallery = self.database['species'][species_key]['photo_gallery']
            if image_path not in gallery:
                gallery.append(image_path)
                # Keep only last 10 photos per species
                if len(gallery) > 10:
                    self.database['species'][species_key]['photo_gallery'] = gallery[-10:]
        
        # Increment sighting count
        self.database['species'][species_key]['sighting_count'] += 1
        
        # Record individual sighting
        sighting = {
            'timestamp': datetime.now().isoformat(),
            'species': species_key,
            'confidence': bird_data.get('confidence', 0),
            'image_path': image_path,
            'behavior': bird_data.get('behavior'),
            'characteristics_observed': bird_data.get('characteristics', [])
        }
        
        self.database['sightings'].append(sighting)
        
        # Keep only last 1000 sightings
        if len(self.database['sightings']) > 1000:
            self.database['sightings'] = self.database['sightings'][-1000:]
        
        self.save_database()
    
    def get_species_stats(self) -> Dict:
        """Get species diversity statistics"""
        if not self.database['species']:
            return {
                'total_species': 0,
                'total_sightings': 0,
                'rarest_species': None,
                'most_common': None
            }
        
        species_list = [(k, v['sighting_count']) for k, v in self.database['species'].items()]
        species_list.sort(key=lambda x: x[1])
        
        return {
            'total_species': len(self.database['species']),
            'total_sightings': len(self.database['sightings']),
            'rarest_species': species_list[0] if species_list else None,
            'most_common': species_list[-1] if species_list else None,
            'species_list': self.database['species']
        }
    
    def check_rare_species(self, species_scientific: str) -> bool:
        """Check if species is rare (seen less than 3 times)"""
        species = self.database['species'].get(species_scientific, {})
        return species.get('sighting_count', 0) < 3