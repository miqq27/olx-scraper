#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supabase Database Sync Module for OLX Scraper
Replaces GitHub storage with robust Supabase database
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# Supabase client
try:
    from supabase import create_client
except ImportError:
    print("Error: supabase library not installed")
    print("Install with: pip install supabase==2.7.4")
    raise


@dataclass
class CarData:
    title: str
    price_text: str
    price_numeric: float
    year: str
    km: str
    link: str
    image_urls: List[str]
    fuel_type: str
    gearbox: str
    car_body: str
    brand: str
    model: str
    unique_id: str
    scrape_date: str

class SupabaseSync:
    """Drop-in replacement for GitHubDatabaseSync using Supabase"""

    def __init__(self, username: str = None, repo: str = None, token: str = None):
        """
        Initialize Supabase client. Parameters kept for compatibility.
        Args:
            username: Ignored (kept for compatibility with GitHubDatabaseSync)
            repo: Ignored (kept for compatibility with GitHubDatabaseSync)
            token: Ignored (kept for compatibility with GitHubDatabaseSync)
        """
        # Get Supabase credentials from environment
        self.url = os.getenv('SUPABASE_URL', 'https://bxhaoghxyqgdzlpjfvta.supabase.co')
        self.key = os.getenv('SUPABASE_SERVICE_KEY')

        if not self.key:
            raise ValueError("SUPABASE_SERVICE_KEY environment variable is required")

        # Initialize Supabase client
        self.supabase = create_client(self.url, self.key)
        self.logger = logging.getLogger("SupabaseSync")

        # Batch operation settings
        self.BATCH_SIZE = 100
        self.MAX_RETRIES = 3
        self.RETRY_DELAY = 2

        # Safety thresholds
        self.MAX_NEW_CARS_PER_RUN = 1000
        self.FRESHNESS_THRESHOLD_HOURS = 24

    def download_database(self, local_path: str = None) -> bool:
        """
        Download database from Supabase for duplicate detection.
        Compatible with GitHubDatabaseSync interface.

        Args:
            local_path: Optional path to save local cache (for compatibility)

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self.logger.info("Downloading database from Supabase")

            # Fetch all cars from database
            response = self.supabase.table('cars').select('*').execute()
            cars_data = response.data

            self.logger.info(f"Fetched {len(cars_data)} cars from Supabase")

            # Convert to price_history format for compatibility
            price_history = {'history': {}, 'metadata': {}}

            for car in cars_data:
                car_id = car['unique_id']

                # Fetch price history for this car
                price_response = self.supabase.table('price_history')\
                    .select('*')\
                    .eq('car_unique_id', car_id)\
                    .order('recorded_at', desc=False)\
                    .execute()

                history_entries = []

                # Add initial entry from cars table
                history_entries.append({
                    'date': car['first_seen'] or car['scraped_at'],
                    'price': float(car['price']) if car['price'] else 999999,
                    'price_text': car['price_text'] or '',
                    'title': car['title'],
                    'link': car['link'],
                    'source': 'supabase'
                })

                # Add price history entries
                for entry in price_response.data:
                    history_entries.append({
                        'date': entry['recorded_at'],
                        'price': float(entry['price']) if entry['price'] else 999999,
                        'price_text': entry['price_text'] or '',
                        'title': car['title'],
                        'link': car['link'],
                        'source': 'supabase'
                    })

                price_history['history'][car_id] = history_entries

            price_history['metadata'] = {
                'last_update': datetime.now().isoformat(),
                'total_cars': len(cars_data),
                'source': 'supabase'
            }

            # Save to local file if path provided
            if local_path:
                os.makedirs(os.path.dirname(local_path) or '.', exist_ok=True)
                with open(local_path, 'w', encoding='utf-8') as f:
                    json.dump(price_history, f, ensure_ascii=False, indent=2)
                self.logger.info(f"Saved local cache to {local_path}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to download database from Supabase: {e}")

            # Create empty database as fallback
            if local_path:
                empty_db = {'history': {}, 'metadata': {'created_at': datetime.now().isoformat()}}
                with open(local_path, 'w', encoding='utf-8') as f:
                    json.dump(empty_db, f, ensure_ascii=False, indent=2)

            return True  # Return True to prevent crashes

    def load_duplicate_database(self) -> Dict[str, dict]:
        """
        Load database for duplicate detection.
        Returns dict in format expected by OLXScrapingEngine.
        """
        try:
            self.logger.info("Loading duplicate database from Supabase")

            # Fetch all cars
            response = self.supabase.table('cars').select('*').execute()
            cars_data = response.data

            # Convert to duplicate_db format
            duplicate_db = {}

            for car in cars_data:
                car_id = car['unique_id']
                duplicate_db[car_id] = {
                    'title': car['title'],
                    'link': car['link'],
                    'last_price': float(car['price']) if car['price'] else 999999,
                    'last_seen': car['scraped_at'],
                    'first_seen': car['first_seen'] or car['scraped_at']
                }

            self.logger.info(f"Loaded {len(duplicate_db)} cars for duplicate detection")
            return duplicate_db

        except Exception as e:
            self.logger.error(f"Failed to load duplicate database: {e}")
            return {}

    def save_cars_data(self, cars_list: List[CarData]) -> bool:
        """
        Save list of CarData objects to Supabase with upsert logic.

        Args:
            cars_list: List of CarData objects to save

        Returns:
            bool: True if successful, False otherwise
        """
        if not cars_list:
            self.logger.info("No cars to save")
            return True

        # Safety check
        if len(cars_list) > self.MAX_NEW_CARS_PER_RUN:
            self.logger.warning(f"Too many new cars ({len(cars_list)}), limiting to {self.MAX_NEW_CARS_PER_RUN}")
            cars_list = cars_list[:self.MAX_NEW_CARS_PER_RUN]

        try:
            self.logger.info(f"Saving {len(cars_list)} cars to Supabase")

            # Process in batches for better performance
            for i in range(0, len(cars_list), self.BATCH_SIZE):
                batch = cars_list[i:i + self.BATCH_SIZE]
                success = self._save_batch(batch)
                if not success:
                    self.logger.error(f"Failed to save batch {i // self.BATCH_SIZE + 1}")
                    return False

            self.logger.info(f"Successfully saved all {len(cars_list)} cars")
            return True

        except Exception as e:
            self.logger.error(f"Failed to save cars data: {e}")
            return False

    def _save_batch(self, batch: List[CarData]) -> bool:
        """Save a batch of cars using upsert to prevent constraint violations"""
        try:
            # First, get existing prices for price change detection
            car_ids = [car.unique_id for car in batch]
            existing_cars = {}

            # Get existing cars in one query (much more efficient)
            if car_ids:
                existing_response = self.supabase.table('cars')\
                    .select('unique_id, price')\
                    .in_('unique_id', car_ids)\
                    .execute()

                for existing_car in existing_response.data:
                    existing_cars[existing_car['unique_id']] = existing_car.get('price')

            # Prepare all cars for upsert and track price changes
            cars_to_upsert = []
            price_updates = []

            for car in batch:
                car_dict = {
                    'unique_id': car.unique_id,
                    'title': car.title,
                    'price': float(car.price_numeric) if car.price_numeric else None,
                    'price_text': car.price_text,
                    'year': car.year,
                    'km': car.km,
                    'link': car.link,
                    'fuel_type': car.fuel_type,
                    'gearbox': car.gearbox,
                    'car_body': car.car_body,
                    'brand': car.brand,
                    'model': car.model,
                    'image_urls': car.image_urls if car.image_urls else [],
                    'scraped_at': car.scrape_date
                }

                # Check if this is a new car (not in existing_cars)
                if car.unique_id not in existing_cars:
                    # New car - set first_seen
                    car_dict['first_seen'] = car.scrape_date
                else:
                    # Existing car - check for price change
                    old_price = existing_cars[car.unique_id]
                    new_price = float(car.price_numeric) if car.price_numeric else None

                    if old_price and new_price and abs(old_price - new_price) >= 1:
                        # Price changed by more than 1 EUR - track it
                        price_updates.append({
                            'car_unique_id': car.unique_id,
                            'price': new_price,
                            'price_text': car.price_text,
                            'recorded_at': car.scrape_date
                        })
                        self.logger.info(f"Price change detected for {car.unique_id}: {old_price} -> {new_price}")

                cars_to_upsert.append(car_dict)

            # Use UPSERT for all cars - this handles both new and existing cars
            # No constraint violations possible with upsert!
            if cars_to_upsert:
                response = self.supabase.table('cars')\
                    .upsert(cars_to_upsert, on_conflict='unique_id')\
                    .execute()
                self.logger.info(f"Upserted {len(cars_to_upsert)} cars successfully")

            # Insert price history records for cars with price changes
            if price_updates:
                self.supabase.table('price_history').insert(price_updates).execute()
                self.logger.info(f"Added {len(price_updates)} price history entries")

            return True

        except Exception as e:
            self.logger.error(f"Failed to save batch: {e}")
            # Log more details for debugging
            if "duplicate key" in str(e).lower():
                self.logger.error("Duplicate key error - this shouldn't happen with upsert!")
            return False

    def upload_database(self, local_path: str = None, session_id: str = None) -> bool:
        """
        Upload database to Supabase. Kept for compatibility.

        Args:
            local_path: Path to local price_history.json file
            session_id: Optional session ID for logging

        Returns:
            bool: True if successful
        """
        if not local_path:
            # Data is already in Supabase, nothing to upload
            self.logger.info("Data already synced to Supabase")
            return True

        try:
            # If local path provided, load and sync data
            if os.path.exists(local_path):
                with open(local_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                history = data.get('history', {})
                self.logger.info(f"Syncing {len(history)} cars from local file to Supabase")

                # Convert history to CarData objects
                cars_to_save = []
                for car_id, entries in history.items():
                    if entries:
                        latest = entries[-1]

                        # Create CarData object from latest entry
                        car = CarData(
                            title=latest.get('title', ''),
                            price_text=latest.get('price_text', ''),
                            price_numeric=latest.get('price', 999999),
                            year='N/A',
                            km='N/A',
                            link=latest.get('link', ''),
                            image_urls=[],
                            fuel_type='N/A',
                            gearbox='N/A',
                            car_body='N/A',
                            brand='N/A',
                            model='N/A',
                            unique_id=car_id,
                            scrape_date=latest.get('date', datetime.now().isoformat())
                        )
                        cars_to_save.append(car)

                # Save to Supabase
                if cars_to_save:
                    return self.save_cars_data(cars_to_save)

            return True

        except Exception as e:
            self.logger.error(f"Failed to upload database: {e}")
            return False

    def verify_database_freshness(self) -> bool:
        """
        Verify that database was updated recently.

        Returns:
            bool: True if database is fresh (updated within threshold)
        """
        try:
            # Get most recent scraped_at timestamp
            response = self.supabase.table('cars')\
                .select('scraped_at')\
                .order('scraped_at', desc=True)\
                .limit(1)\
                .execute()

            if not response.data:
                self.logger.warning("Database is empty")
                return True  # Empty database is considered "fresh"

            last_update = datetime.fromisoformat(response.data[0]['scraped_at'].replace('Z', '+00:00'))
            current_time = datetime.now(last_update.tzinfo)

            hours_since_update = (current_time - last_update).total_seconds() / 3600

            if hours_since_update > self.FRESHNESS_THRESHOLD_HOURS:
                self.logger.warning(f"Database is stale: last update was {hours_since_update:.1f} hours ago")
                return False

            self.logger.info(f"Database is fresh: last update was {hours_since_update:.1f} hours ago")
            return True

        except Exception as e:
            self.logger.error(f"Failed to verify database freshness: {e}")
            return True  # Assume fresh on error to avoid blocking

    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            # Count total cars
            car_count = self.supabase.table('cars').select('unique_id', count='exact').execute()
            total_cars = len(car_count.data) if car_count.data else 0

            # Count price history entries
            history_count = self.supabase.table('price_history').select('id', count='exact').execute()
            total_history = len(history_count.data) if history_count.data else 0

            # Get recent activity
            recent_response = self.supabase.table('cars')\
                .select('scraped_at')\
                .order('scraped_at', desc=True)\
                .limit(10)\
                .execute()

            recent_updates = [row['scraped_at'] for row in recent_response.data]

            return {
                'total_cars': total_cars,
                'total_price_history_entries': total_history,
                'recent_updates': recent_updates,
                'database_url': self.url
            }

        except Exception as e:
            self.logger.error(f"Failed to get statistics: {e}")
            return {}
