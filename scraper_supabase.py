#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modified OLXScrapingEngine to use Supabase instead of GitHub
"""

import os
import sys
import time
import random
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime

# Import base scraper components
from scraper_dev_backup import (
    OLXScrapingEngine as BaseOLXScrapingEngine,
    CarData, SearchConfig,
    generate_car_id, PRICE_CHANGE_THRESHOLD,
    RESULTS_DIR
)

# Import Supabase sync
from supabase_sync import SupabaseSync


class OLXScrapingEngineSupabase(BaseOLXScrapingEngine):
    """Extended OLX Scraping Engine with Supabase integration"""

    def __init__(self):
        """Initialize scraper with Supabase support"""
        super().__init__()
        self.supabase_sync = None
        self.logger = logging.getLogger("OLXScrapingEngineSupabase")

    def init_supabase(self):
        """Initialize Supabase connection"""
        try:
            self.supabase_sync = SupabaseSync()
            self.logger.info("Supabase sync initialized")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Supabase: {e}")
            return False

    def load_duplicate_database(self, database_content: dict = None):
        """
        Load duplicate database from Supabase instead of local file.
        Overrides parent method to use Supabase.
        """
        if not self.supabase_sync:
            if not self.init_supabase():
                # Fallback to parent implementation if Supabase fails
                super().load_duplicate_database(database_content)
                return

        try:
            # Load from Supabase
            self.duplicate_db = self.supabase_sync.load_duplicate_database()

            cars_count = len(self.duplicate_db)
            self.logger.info(f"Loaded {cars_count} cars from Supabase")

            if cars_count < 100 and cars_count > 0:
                print(f"[DATABASE] WARNING: Database suspiciously small ({cars_count} cars)")

            # Sample logging
            if cars_count > 0:
                sample_ids = list(self.duplicate_db.keys())[:5]
                print(f"[DATABASE] Sample IDs from Supabase: {sample_ids}")

        except Exception as e:
            print(f"[DATABASE] Error loading from Supabase: {e}")
            self.logger.error(f"Supabase load fail: {e}")
            self.duplicate_db = {}

    def save_duplicate_database(self, new_cars: List[CarData]):
        """
        Save cars to Supabase instead of local file.
        Overrides parent method to use Supabase.
        """
        if not new_cars:
            self.logger.info("No new cars to save")
            return

        if not self.supabase_sync:
            if not self.init_supabase():
                # Fallback to parent implementation if Supabase fails
                super().save_duplicate_database(new_cars)
                return

        try:
            print(f"\n[DATABASE SAVE] Saving {len(new_cars)} cars to Supabase")

            # Save to Supabase
            success = self.supabase_sync.save_cars_data(new_cars)

            if success:
                print(f"[DATABASE SAVE] Successfully saved to Supabase")
                self.logger.info(f"Saved {len(new_cars)} cars to Supabase")

                # Update local duplicate_db for consistency
                for car in new_cars:
                    self.duplicate_db[car.unique_id] = {
                        'title': car.title,
                        'link': car.link,
                        'last_price': float(car.price_numeric),
                        'last_seen': car.scrape_date,
                        'first_seen': car.scrape_date
                    }
            else:
                print(f"[DATABASE SAVE] Failed to save to Supabase")
                self.logger.error("Failed to save cars to Supabase")

        except Exception as e:
            print(f"[DATABASE SAVE] Error saving to Supabase: {e}")
            self.logger.error(f"Supabase save error: {e}")

    def filter_duplicates(self, cars_data: List[CarData]) -> List[CarData]:
        """
        Filter duplicates using Supabase data.
        Maintains same interface as parent class.
        """
        # Use parent implementation which works with self.duplicate_db
        # Since we've loaded duplicate_db from Supabase, this will work correctly
        return super().filter_duplicates(cars_data)


def run_scraper_with_supabase(config: SearchConfig, session_id: str = None):
    """
    Run the scraper with Supabase integration.

    Args:
        config: Search configuration
        session_id: Optional session ID for tracking

    Returns:
        List of scraped cars
    """
    engine = OLXScrapingEngineSupabase()

    try:
        print("[WORKFLOW] Step 1: Initializing Supabase connection")
        if not engine.init_supabase():
            print("[ERROR] Failed to initialize Supabase")
            return []

        print("[WORKFLOW] Step 2: Loading duplicate database from Supabase")
        engine.load_duplicate_database()

        print("[WORKFLOW] Step 3: Starting scraping process")
        engine.setup_driver()

        all_cars = []
        for brand in config.brands:
            print(f"\n[SCRAPING] Processing brand: {brand}")

            # Build search URL
            base_url = f"https://www.olx.ro/auto-masini-moto-ambarcatiuni/autoturisme/{brand}/"
            params = []

            if config.price_min > 0:
                params.append(f"search[filter_float_price:from]={config.price_min}")
            if config.price_max < 999999:
                params.append(f"search[filter_float_price:to]={config.price_max}")
            if config.year_min > 0:
                params.append(f"search[filter_float_rulaj_pana:from]={config.km_min}")
            if config.year_max < 999999:
                params.append(f"search[filter_float_rulaj_pana:to]={config.km_max}")

            search_url = base_url
            if params:
                search_url += "?" + "&".join(params)

            # Scrape brand
            cars = engine.scrape_brand(
                brand=brand,
                search_url=search_url,
                max_pages=config.max_pages_per_brand
            )

            all_cars.extend(cars)

        print(f"\n[WORKFLOW] Step 4: Filtering duplicates")
        filtered_cars = engine.filter_duplicates(all_cars)

        print(f"[WORKFLOW] Step 5: Saving {len(filtered_cars)} new/updated cars to Supabase")
        engine.save_duplicate_database(filtered_cars)

        # Also save to CSV for compatibility
        if filtered_cars:
            csv_file = os.path.join(RESULTS_DIR, f'cars_data_{session_id or "supabase"}.csv')
            import pandas as pd
            df = pd.DataFrame([{
                'Title': car.title,
                'Price': car.price_text,
                'Year': car.year,
                'KM': car.km,
                'Fuel': car.fuel_type,
                'Gearbox': car.gearbox,
                'Body': car.car_body,
                'Brand': car.brand,
                'Model': car.model,
                'Link': car.link
            } for car in filtered_cars])
            df.to_csv(csv_file, index=False)
            print(f"[WORKFLOW] Saved CSV to {csv_file}")

        print(f"\n[WORKFLOW] Complete! Scraped {len(all_cars)} total, {len(filtered_cars)} new/updated")
        return filtered_cars

    except Exception as e:
        print(f"[ERROR] Scraping failed: {e}")
        import traceback
        traceback.print_exc()
        return []

    finally:
        if engine.driver:
            engine.driver.quit()


if __name__ == "__main__":
    # Test configuration
    test_config = SearchConfig(
        brands=["dacia", "volkswagen"],
        models_by_brand={},
        fuel_types=[],
        car_bodies=[],
        gearbox_types=[],
        car_states=[],
        price_min=1000,
        price_max=15000,
        year_min=2010,
        year_max=2024,
        km_min=0,
        km_max=200000,
        power_min=0,
        power_max=999,
        currency="EUR",
        max_pages_per_brand=2
    )

    # Run test scraper
    print("Starting test scrape with Supabase integration...")
    results = run_scraper_with_supabase(test_config, session_id="test_supabase")
    print(f"Test complete: {len(results)} cars processed")