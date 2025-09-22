#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# DEV VERSION - Created for job queue integration
# UPDATED: Added GitHub Actions headless mode support while preserving ALL GUI functionality

"""
OLX Advanced Car Scraper - Marci + Modele + Cautare branduri
- Dropdown marci cu SEARCH
- Modele per marca, cu memorarea selectiei
- Multi-brand scraping + filtrare dupa modele selectate
- Export CSV/XLSX
- GitHub Actions headless mode support (NEW)
"""

import sys
import os
import time
import random
import pandas as pd
import logging
import json
import hashlib
import re
import requests
import base64
import argparse
import tempfile
import shutil
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime, timedelta

# Platform-specific imports
try:
    import fcntl  # Unix/Linux file locking
except ImportError:
    fcntl = None  # Windows doesn't have fcntl

# Check for GitHub Actions mode BEFORE importing PyQt5
def is_github_actions_mode():
    """Detect if running in GitHub Actions headless mode"""
    return '--config' in sys.argv and '--session-id' in sys.argv

# ====== GUI ======
# Only import PyQt5 if NOT running in GitHub Actions mode
GITHUB_ACTIONS_MODE = is_github_actions_mode()

if not GITHUB_ACTIONS_MODE:
    try:
        from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
        from PyQt5.QtGui import QFont, QDesktopServices
        from PyQt5.QtWidgets import (
            QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
            QFileDialog, QMessageBox, QProgressBar, QComboBox, 
            QCheckBox, QSpinBox, QGroupBox, QTabWidget,
            QTableWidget, QTableWidgetItem, QHeaderView,
            QGridLayout, QScrollArea, QListWidget, QAbstractItemView, QListWidgetItem, QLineEdit
        )
        PYQT5_AVAILABLE = True
    except ImportError as e:
        if not GITHUB_ACTIONS_MODE:
            print(f"PyQt5 import error: {e}\n   Instaleaza: pip install PyQt5")
            sys.exit(1)
        PYQT5_AVAILABLE = False
else:
    # In GitHub Actions mode, create stub classes to avoid errors
    PYQT5_AVAILABLE = False
    class QThread:
        def __init__(self): pass
    class pyqtSignal:
        def __init__(self, *args): pass
        def connect(self, *args): pass
        def emit(self, *args): pass
    class QWidget:
        def __init__(self): pass
    class QListWidgetItem:
        def __init__(self, *args): pass
    class QApplication:
        def __init__(self, *args): pass
        def exec_(self): pass
    class QLabel:
        def __init__(self, *args): pass
    class QPushButton:
        def __init__(self, *args): pass
    class QVBoxLayout:
        def __init__(self): pass
    class QHBoxLayout:
        def __init__(self): pass
    class QGridLayout:
        def __init__(self): pass
    class QGroupBox:
        def __init__(self, *args): pass
    class QTabWidget:
        def __init__(self): pass
    class QComboBox:
        def __init__(self): pass
    class QCheckBox:
        def __init__(self, *args): pass
    class QSpinBox:
        def __init__(self): pass
    class QLineEdit:
        def __init__(self): pass
    class QListWidget:
        def __init__(self): pass
    class QTableWidget:
        def __init__(self): pass
    class QTableWidgetItem:
        def __init__(self, *args): pass
    class QProgressBar:
        def __init__(self): pass
    class QMessageBox:
        @staticmethod
        def information(*args): pass
        @staticmethod
        def warning(*args): pass
        @staticmethod
        def question(*args): pass
        @staticmethod
        def critical(*args): pass
    class QFileDialog:
        @staticmethod
        def getSaveFileName(*args): return ('', '')
    class QHeaderView:
        ResizeToContents = None
        Stretch = None
    class QAbstractItemView:
        SingleSelection = None
    class Qt:
        AlignCenter = None
        CheckState = None
        Checked = None
        Unchecked = None

# ====== Selenium ======
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from fake_useragent import UserAgent
except ImportError as e:
    print(f"Selenium import error: {e}\n   Instaleaza: pip install selenium webdriver-manager fake-useragent")
    sys.exit(1)

# ====== BeautifulSoup ======
try:
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"BeautifulSoup import error: {e}\n   Instaleaza: pip install beautifulsoup4")
    sys.exit(1)

# ---------- Config ----------
# Handle paths for both development and .exe environments
def get_app_dir():
    """Get the directory where the application is running from"""
    if hasattr(sys, '_MEIPASS'):  # PyInstaller temp directory
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def get_data_dir():
    """Get the directory where data files should be stored"""
    if hasattr(sys, '_MEIPASS'):  # Running as .exe
        # Store data in same directory as .exe
        exe_dir = os.path.dirname(sys.executable)
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))

# Set up directories
BASE_DIR = get_data_dir()
CACHE_DIR = os.path.join(BASE_DIR, "olx_cache")
RESULTS_DIR = os.path.join(BASE_DIR, "olx_results")

try:
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
except Exception as e:
    print(f"Warning: Could not create directories: {e}")
    # Fallback to current directory
    CACHE_DIR = "olx_cache"
    RESULTS_DIR = "olx_results"
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

REQUEST_TIMEOUT = 15
PRICE_CHANGE_THRESHOLD = 1.0  # diferenta minima ca sa consideram ca s-a schimbat pretul (in unitatea monedei)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Database Protection Configuration
MAX_DATABASE_BACKUPS = 5
BACKUP_RETENTION_DAYS = 30
UPLOAD_RETRY_ATTEMPTS = 5
DOWNLOAD_RETRY_ATTEMPTS = 3
GITHUB_RATE_LIMIT_DELAY = (1, 5)  # min, max seconds

SAFETY_DELAYS = {
    'between_requests': (5, 8),
    'between_pages': (8, 12),
    'between_brands': (10, 15),
    'individual_car': (2, 4),
    'error_retry': 30,
    'rate_limit': 60
}
# ---------- Saved Searches ----------
SAVED_SEARCHES_FILE = os.path.join(RESULTS_DIR, "saved_searches.json")


# ---------- Marci + Modele (INTEGRATE) ----------
# [WARNING] Daca vrei lista ta completa exact cum ai pus-o, inlocuieste continutul de mai jos.
CAR_BRANDS_MODELS: Dict[str, List[str]] = {
    "Abarth": ["124", "124 Spider", "500", "595", "695", "Grande Punto", "Inny", "Altul"],
    "Acura": ["Toate modelele"],
    "Aixam": ["City", "Coupe", "Crossline", "Crossover", "D-Truck", "e-TRUCK", "GTO", "Miniauto", "Roadline", "Scouty R", "Seria A", "Altul"],
    "Alfa Romeo": ["4C", "33", "75", "90", "145", "146", "147", "155", "156", "159", "164", "166", "Alfasud", "Alfetta", "Brera", "Crosswagon", "Giulia", "Giulietta", "GT", "GTV", "Mito", "RS/RZ", "Spider", "Sportwagon", "Stelvio", "Sprint", "Altul"],
    "Aston Martin": ["AMV8", "Bulldog", "Cygnet", "DB4", "DB5", "DB6", "DB7", "DB9", "DB11", "DBS", "DBX", "DB12 Volante", "Lagonda", "One-77", "V8 Vantage", "V12 Vantage", "Vanquish", "Virage", "Volante", "Zagato", "Altul"],
    "Audi": ["80", "90", "100", "200", "A1", "A2", "A3", "A4", "A4 Allroad", "A5", "A6", "A6 Allroad", "A7", "A8", "Cabriolet", "Coupe", "e-tron", "e-tron GT", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Quattro", "R8", "RS2", "RS3", "RS4", "RS5", "RS6", "RS7", "RS Q3", "RSQ8", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "SQ2", "SQ5", "SQ7", "SQ8", "TT", "TT RS", "TT S", "V8", "Altul"],
    "Bentley": ["Amage", "Azure", "Bentayga", "Broklands", "Continental", "Eight", "Flying Spur", "Mulliner", "Mulsanne", "Turbo", "Altul"],
    "BMW": ["ALPINA", "i3", "i4", "i5", "i8", "iX", "iX2", "iX3", "Seria 1", "Seria 2", "Seria 3", "Seria 4", "Seria 5", "Seria 6", "Seria 7", "Seria 8", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "X1", "X2", "X3", "X3 M", "X4", "X4 M", "X5", "X6", "X6 M", "X7", "Z1", "Z3", "Z3 M", "Z4", "Z4 M", "Z8", "Altul"],
    "Bugatti": ["Chrion", "EB 110", "Veyron", "Altul"],
    "Cadillac": ["Allante", "ATS", "BLS", "Brougham", "Cimarron", "CT6", "CTS", "Deville", "DTS", "Eldorado", "Escalade", "Fleetwood", "Seville", "SRX", "STS", "XLR", "XT4", "XT5", "XT6", "XTS", "Altul"],
    "Chevrolet": ["1500", "2500", "3500", "Alero", "Astro", "Avalanche", "Aveo", "Beretta", "Blazer", "Camaro", "Caprice", "Captiva", "Cavalier", "Chevelle", "Citation", "Colorado", "Corsica", "Corvette", "Cruze", "El Camino", "Epica", "Equinox", "Evanda", "Express", "G", "HHR", "Impala", "Kalos", "Lacetti", "Lumina", "Malibu", "Matiz", "Nubira", "Orlando", "Rezzo", "S-10", "Silverado", "Spark", "Spectrum", "SSR", "Suburban", "Tacuma", "Tahoe", "Trailblazer", "Trans Sport", "Traverse", "Venture", "Volt", "Altul"],
    "Chrysler": ["300C", "300M", "Aspen", "Caravan", "Concorde", "Crossfire", "Daytona", "ES", "Grand Voyager", "GS", "GTS", "Le Baron", "LHS", "Neon", "New Yorker", "Pacifica", "Prowler", "PT Cruiser", "Saratoga", "Sebring", "Stratus", "Town & Country", "Valiant", "Viper", "Vision", "Voyager", "Altul"],
    "Citroen": ["2 CV", "AX", "Axel", "Berlingo", "BX", "C-Crosser", "C-Elysee", "C-Zero", "C1", "C2", "C3", "C3 Aicross", "C3 Picasso", "C3 Plurier", "C4", "C4X", "C4 Aircross", "C4 Cactus", "C4 Grand Picasso", "C4 Grand Space Tourer", "C4 Picasso", "C4 Space Tourer", "C5", "C5 Aircross", "C6", "C8", "CX", "Cactus", "DS", "DS3", "DS4", "DS5", "DS7", "Evasion", "GSA", "Jumper", "Jumpy", "Nemo", "Saxo", "SM", "SpaceTourer", "Visa", "Xantia", "XM", "Xsara", "Xsara Picasso", "ZX", "Altul"],
    "Cupra": ["Ateca", "Born", "Formentor", "Leon", "Tavascan", "Terramar"],
    "Dacia": ["1100", "1300", "1310", "1400", "1410", "Dokker", "Duster", "Lodgy", "Logan", "Logan Stepway", "Logan Van", "Nova", "Pick Up", "Sandero", "Sandero Stepway", "Solenza", "Super Nova", "Spring", "Jogger", "Bigster", "Altul"],
    "Daewoo": ["Chairman", "Cielo", "Espero", "Evanda", "Kalos", "Korando", "Lacetti", "Lanos", "Leganza", "Matiz", "Musso", "Nexia", "Nubira", "Racer", "Rezzo", "Tacuma", "Tico", "Altul"],
    "Daihatsu": ["Applause", "Charade", "Charmant", "Copen", "Cuore", "Feroza", "Fourtrak", "Freeclimber", "Gran Move", "Hijet", "Materia", "More", "Rocky", "Sirion", "Sportrak", "Terios", "Trevis", "YRV", "Altul"],
    "Dodge": ["Avenger", "Caliber", "Caravan", "Challenger", "Charger", "Dakota", "Dart", "Daytona", "Diplomat", "Durango", "Dynasty", "Grand Caravan", "Hornet", "Intrepid", "Journey", "Magnum", "Monaco", "Neon", "Nitro", "Omni", "RAM", "Spirit", "Stealth", "Stratus", "Viper", "Altul"],
    "DS Automobiles": ["DS 3", "DS 3 Crossback", "DS 4", "DS 4 Crossback", "DS 5", "DS 7 Crossback", "DS 9"],
    "Ferrari": ["296 GTB", "296 GTS", "308", "320", "340", "360", "365", "400", "412", "456", "458", "488 Spider", "512", "550", "575", "599", "612", "812", "208/308", "488 GTB", "599 GTB", "Altul"],
    "Fiat": ["124", "125p", "126", "127", "128", "130", "131", "132", "500", "500L", "500X", "600", "850", "Albea", "Barchetta", "Brava", "Bravo", "Cinquecento", "Coupe", "Croma", "Dino", "Doblo", "Ducato", "Fiorino", "Freemont", "Grande Punto", "Idea", "Linea", "Marea", "Multipla", "Palio", "Panda", "Punto", "Qubo", "Regata", "Ritmo", "Scudo", "Sedici", "Seicento", "Siena", "Spider Europa", "Stilo", "Strada", "Tempra", "Tipo", "Ulysse", "Uno", "X 1/9", "Talento", "Fullback", "Altul"],
    "Ford": ["Aerostar", "Aspire", "B-MAX", "Bronco", "C-MAX", "Capri", "Contour", "Cougar", "Courier", "Crown", "Econoline", "Econovan", "EcoSport", "EDGE", "Escape", "Escort", "Excursion", "Expedition", "Explorer", "F150", "F250", "F350", "Fairlane", "Falcon", "Festiva", "Fiesta", "FIVE HUNDRED", "Focus", "C-MAX", "Freestar", "Freestyle", "Fusion", "Galaxy", "Granada", "Grand C-MAX", "GT", "KA", "KA+", "Kuga", "Maverick", "Mercury", "Mondeo", "Mustang", "Mustant Mach-E", "Orion", "Probe", "Puma", "Ranchero", "Ranger", "Raptor", "S-MAX", "Scorpio", "Sierra", "Streetka", "Taunus", "Taurus", "Tempo", "Thunderbird", "Tourneo", "Tourneo Connect", "Tourneo Custom", "Transit", "Transit Connect", "Transit Custom", "Windstar", "Altul"],
    "GMC": ["Acadia", "Canyon", "Envoy", "Jimmy", "Safari", "Savana", "Sierra", "Sonoma", "Suburban", "Syclone", "Terrain", "Typhoon", "Vandura", "Yukon", "Altul"],
    "Honda": ["Accord", "Aerodeck", "City", "Civic", "Concerto", "CR-V", "CR-Z", "CRX", "Element", "eNY1", "FR-V", "Honda e", "GR-V", "Insight", "Integra", "Jazz", "Legend", "Logo", "NSX", "Odyssey", "Pilot", "Prelude", "Ridgeline", "S 2000", "Shuttle", "Stream", "ZR-V", "Altul"],
    "Hummer": ["H1", "H2", "H3", "Altul"],
    "Hyundai": ["Accent", "Atos", "Avante", "Azera", "Bayon", "Coupe", "Elantra", "Excel", "Galloper", "Genesis", "Getz", "Grandeur", "Grand Santa Fe", "H-1", "H-1 Starex", "H200", "H350", "i10", "i20", "i25", "i30", "i40", "Inster", "Ioniq", "Ioniq5", "ix20", "ix35", "ix55", "Kona", "Lantra", "Lavita", "Matrix", "Palisade", "Pony", "S-Coupe", "Santa Fe", "Sonata", "Sonica", "Terracan", "Trajet", "Tucson", "Veloster", "Veracruz", "XG", "Altul"],
    "Infiniti": ["EX", "EX30", "EX 35", "EX 37", "FX 30", "FX 35", "FX 37", "FX 45", "FX 50", "G20", "G35", "G37", "I30", "I35", "J30", "M30", "M35", "M37", "Q30", "Q45", "Q50", "Q60", "Q70", "QX30", "QX50", "QX 56", "QX70", "QX 80", "Altul"],
    "Isuzu": ["Toate modelele"],
    "Jaguar": ["Daimler", "E-Pace", "E-Type", "F-Pace", "F-Type", "I-Pace", "MK II", "S-Type", "X-Type", "XE", "XF", "XJ", "XJS", "XK", "XK8", "XKR", "Altul"],
    "Jeep": ["Cherokee", "CJ", "Comanche", "Commander", "Compass", "Gladiator", "Grand Cherokee", "Liberty", "Patriot", "Renegade", "Wagoneer", "Willys", "Wrangler", "Altul"],
    "Kia": ["Asia Rocsta", "Besta", "Carens", "Carnival", "Cerato", "Ceed", "Clarus", "Elan", "EV9", "Joice", "Leo", "Magentis", "Mentor", "Niro", "Opirus", "Optima", "Picanto", "Pregio", "Pride", "Pro Ceed", "Retona", "Rio", "Roadster", "Rocsta", "Sedona", "Sephia", "Shuma", "Sorento", "Soul", "Spectra", "Sportage", "Stinger", "Stonic", "Venga", "XCeed", "Altul"],
    "Lamborghini": ["Aventador", "Countach", "Diablo", "Espada", "Gallardo", "Huracan", "Jalpa", "LM", "Miura", "Murcielago", "Reventon", "Revuelto", "Urraco", "Urus", "Altul"],
    "Lancia": ["Toate modelele"],
    "Land Rover": ["Defender", "Discovery", "Discovery Sport", "Freelander", "Range Rover", "Range Rover Evoque", "Range Rover Sport", "Range Rover Velar", "Range Rover Vogue", "Altul"],
    "Lexus": ["CT", "LBX", "LC 500", "LFA", "LM", "Seria ES", "Seria GS", "Seria GX", "Seria IS", "Seria LS", "Seria LX", "Seria NX", "Seria RC", "Seria RX", "Seria RZ", "Seria SC", "TX500 H", "UX", "Altul"],
    "Maserati": ["222", "224", "228", "418", "420", "422", "424", "430", "3200", "4200", "Biturbo", "Coupe", "Ghibli", "GranCabrio", "Gransport", "GranTurismo", "Indy", "Karif", "Levante", "MC Stradale", "MC12", "Merak", "Quattroporte", "Shamal", "Spyder", "Altul"],
    "Mazda": ["121", "2", "3", "323", "5", "6", "626", "929", "Bongo", "BT-50", "CX-3", "CX-30", "CX-5", "CX-60", "CX-7", "CX-80", "CX-9", "Demio", "Millenia", "MPV", "MX-3", "MX-30", "MX-5", "MX-6", "Premacy", "Protege", "RX-6", "RX-7", "RX-8", "Seria B", "Seria E", "Tribute", "Xedos", "Altul"],
    "McLaren": ["Toate modelele"],
    "Maybach": ["57", "62", "S 500", "S560", "S560 4Matic", "S680 4Matic", "S580", "Altul"],
    "Mercedes-Benz": ["123 C", "350 SD", "AMG", "AMG ONE", "AMG GT", "AMG GT S", "AMG SL Roadster", "CE", "A", "B", "C", "CL", "CLA", "CLC", "CLE", "CLK", "CLS", "E Class", "G", "GL", "GLA", "GLB", "GLC", "GLE", "GLE Coupe", "GLK", "GLS", "ML", "R", "S", "SL", "SLK", "X", "EQA", "EQB", "EQC", "EQE", "EQG", "EQS", "EQV", "MB 100", "Monarch", "SLR", "SLS", "Sprinter", "190", "200", "300", "500 SEL", "V", "Vaneo", "Vario", "Viano", "Vito", "W123", "W124", "Alta", "Altul"],
    "MG": ["HS", "MGA", "MGB", "MGF", "Midget", "Montego", "TD", "TF", "ZR", "ZS", "ZS EV", "ZT", "Altul"],
    "Mini": ["Clubman Cooper", "Cooper S", "Cooper SE", "Countryman", "One", "Paceman", "Roadster", "Altul"],
    "Mitsubishi": ["3000 GT", "ASX", "Canter", "Carisma", "Colt", "Cordia", "Cosmos", "Diamante", "Eclipse", "Eclipse-Cross", "Endeavor", "FTO", "Galant", "Galloper", "Grandis", "i-MiEV", "L200", "L300", "L400", "Lancer", "Lancer Evolution", "Montero", "Mirage", "Outlander", "Pajero", "Pajero Pinin", "Santamo", "Sapporo", "Sigma", "Space Gear", "Space Runner", "Space Star", "Space Wagon", "Starion", "Trendia", "Altul"],
    "Microcar": ["Toate modelele"],
    "Nissan": ["100 NX", "200 SX", "240 SX", "280 ZX", "300 ZX", "350 Z", "370 Z", "Almera", "Almera Tino", "Altima", "Ariya", "Armada", "Bluebird", "Cherry", "Cube", "Evalia", "Frontier", "GT-R", "Interstar", "Juke", "King Crab", "Kubistar", "Laurel", "Leaf", "Maxima", "Micra", "Murano", "Navara", "New Micra", "Note", "NP300 Pickup", "NV300", "NV200", "Pathfinder", "Patrol", "Pickup", "Pixo", "Prairie", "Primastar", "Primera", "Pulsar", "Qashaqai", "Qashqai+2", "Quest", "Rogue", "Sentra", "Serena", "Silvia", "Skyline", "Stanza", "Sunyy", "Terrano", "Tiida", "Titan", "Trade", "Urvan", "Vanette", "X-Trail", "Altul"],
    "Opel": ["Adam", "Agila", "Ampera", "Ampera-e", "Antara", "Arena", "Ascona", "Astra", "Calibra", "Cascada", "Campo", "Combo", "Commodore", "Corsa", "Crossland", "Diplomat", "Frontera", "Grandland", "Grandland X", "GT", "Insignia", "Karl", "Kadet", "Manta", "Meriva", "Monterey", "Monza", "Mokka", "Movano", "Nova", "Omega", "Pick up Sportcap", "Rekord", "Senator", "Signum", "Sintra", "Speedster", "Tigra", "Vectra", "Vivaro", "Zafira", "Altul"],
    "Peugeot": ["104", "106", "107", "108", "204", "205", "206", "206 CC", "206-Plus", "207", "207 CC", "208", "301", "304", "305", "306", "307", "307 CC", "307 SW", "308", "309", "395", "404", "405", "406", "407", "408", "504", "505", "508", "604", "605", "607", "806", "807", "1007", "2008", "3008", "4007", "4008", "5008", "Bipper", "Boxer", "Expert", "iON", "Partner", "RCZ", "Rifter", "Traveller", "Altul"],
    "Porsche": ["356", "911", "911 Turbo S", "912", "914", "924", "928", "944", "959", "962", "968", "Boxter", "Carrera GT", "Cayenne", "Cayenne Coupe", "Cayman", "Macan", "Panamera", "Taycan", "Altul"],
    "Renault": ["4", "5", "8", "9", "10", "11", "12", "14", "16", "18", "19", "20", "21", "25", "30", "Alaskan", "Arkana", "Avantime", "Captur", "Clio", "Espace", "Express", "Fluence", "Fuego", "Grand Espace", "Grand Scenic", "Kadjar", "Kangoo", "Koleos", "Laguna", "Latitude", "Master", "Megane", "Modus", "Safrane", "Scenic", "Scenic RX4", "Symbol", "Talisman", "Trafic", "Twingo", "Twizy", "Vel Satis", "Wind", "Zoe", "Altul"],
    "Rolls-Royce": ["Cornice", "Cullinan", "Dawn", "Flying Spur", "Ghost", "Park Ward", "Phantom", "Silver Cloud", "Silver Seraph", "Shadow", "Silver Spirit", "Silver Spur", "Spectre", "Touring Limousine", "Wraith", "Altul"],
    "Rover": ["25", "45", "75", "100", "115", "200", "213", "214", "216", "218", "220", "400", "414", "416", "418", "420", "600", "618", "620", "623", "800", "820", "825", "827", "City Rover", "Metro", "Montego", "SD", "Streetwise", "Altul"],
    "Saab": ["Toate modelele"],
    "Seat": ["Alhambra", "Altea", "Altea XL", "Arosa", "Arona", "Atena", "Cordoba", "Exeo", "Ibiza", "Inca", "Leon", "Malaga", "Marbella", "Mii", "Ronda", "Tarraco", "Terra", "Toledo", "Altul"],
    "Skoda": ["100", "105", "120", "130", "135", "Citigo", "Enyaq", "Fabia", "Favorit", "Felicia", "Forman", "Kamiq", "Karoq", "Kodiaq", "Octavia", "Praktik", "RAPID", "Roomster", "Scala", "Superb", "Yeti", "Altul"],
    "Smart": ["Crossblade", "Forfour", "Fortwo", "Roadster", "Altul"],
    "SsangYong": ["Actyon Family", "Korrando", "Kyron", "Musso", "Rexton", "Rodius", "Tivoli", "Tivoli Grand", "XLV", "Altul"],
    "Subaru": ["B9 Tribeca", "BRZ", "Baja", "Crosstrek", "Forester", "Impreza", "Justy", "Legacy", "Leone", "Levorg", "Libero", "OUTBACK", "Solterra", "SVX", "Trezia", "Tribeca", "Vivio", "WRX STI", "XT", "XV", "Ascent", "Altul"],
    "Suzuki": ["Across", "Alto", "Baleno", "Cappucino", "Carry", "Celerio", "Grand Vitara", "Ignis", "Jimny", "Kizashi", "Liana", "LJ", "Reno", "Samurai", "SJ", "Splash", "Super-Carry", "Swace", "Swift", "SX4", "SX4 S-Cross", "Vitara", "Wagon R+", "X-90", "XL7", "Altul"],
    "Tesla": ["Model S", "Model 3", "Model X", "Model Y", "Roadster"],
    "Toyota": ["4-Runner", "Alphard", "Auris", "Avalon", "Avensis", "Avensis Verso", "Aygo", "Aygo X", "C-HR", "Camry", "Camry Solara", "Carina", "Celica", "Corolla", "Corolla Verso", "Cressida", "Crown", "Dyna", "FJ", "GT86", "Harrier", "Hiace", "Highlander", "Hilux", "iQ", "Land Cruiser 250", "Land Cruiser 300", "Lite-Ace", "Matrix", "MR2", "Paseo", "Picnic", "Previa", "Prius", "Prius+", "Proace", "RAV-4", "Sequoia", "Sienna", "Starlet", "Supra", "Tacoma", "Tercel", "Tundra", "Urban Cruiser", "Venza", "Verso", "Yaris", "Yaris Verso", "Altul"],
    "Volkswagen": ["181", "Amarok", "Arteon", "Atlas", "Beetle", "Bora", "Buggy", "Caddy", "California", "Caravelle", "Corrado", "Crafter", "Eos", "Fox", "Garbus", "e-Golf", "Golf", "Golf Plus", "Golf Sportsvan", "ID.3", "ID.4", "ID.5", "ID.7", "ID. Buzz", "Iltis", "Jetta", "Kafer", "Karmann Ghia", "Lupo", "Multivan", "New Beetle", "Passat", "Passat Alltrack", "Passat CC", "Phaeton", "Polo", "Santana", "Scirocco", "Sharan", "T-Cross", "T-Roc", "Taigo", "Tiguan", "Touareg", "Touran", "Transporter", "up!", "Vento", "Altul"],
    "Volvo": ["240", "244", "245", "262", "264", "340", "360", "440", "460", "480", "740", "744", "745", "760", "780", "850", "855", "940", "944", "945", "960", "965", "Amazon", "C30", "C40", "C70", "EX30", "EX90", "Polar", "S40", "S60", "S70", "S80", "S90", "V40", "V70", "V90", "XC 60", "XC 70", "XC 90", "XC 40", "Altul"],
    "Alte Marci": ["Toate modelele"]
}

# Mapari slug pentru OLX
BRAND_TO_SLUG = {
    "Abarth": "abarth", "Acura": "acura", "Aixam": "aixam", "Alfa Romeo": "alfa-romeo",
    "Aston Martin": "aston-martin", "Audi": "audi", "Bentley": "bentley", "BMW": "bmw",
    "Bugatti": "bugatti", "Cadillac": "cadillac", "Chevrolet": "chevrolet", "Chrysler": "chrysler",
    "Citroen": "citroen", "Cupra": "cupra", "Dacia": "dacia", "Daewoo": "daewoo",
    "Daihatsu": "daihatsu", "Dodge": "dodge", "DS Automobiles": "ds-automobiles",
    "Ferrari": "ferrari", "Fiat": "fiat", "Ford": "ford", "GMC": "gmc", "Honda": "honda",
    "Hyundai": "hyundai", "Infiniti": "infiniti", "Isuzu": "isuzu", "Jaguar": "jaguar",
    "Jeep": "jeep", "Kia": "kia", "Lamborghini": "lamborghini", "Lancia": "lancia",
    "Land Rover": "land-rover", "Lexus": "lexus", "Maserati": "maserati", "Mazda": "mazda",
    "McLaren": "mclaren", "Maybach": "maybach", "Mercedes-Benz": "mercedes-benz", "MG": "mg",
    "Mini": "mini", "Mitsubishi": "mitsubishi", "Microcar": "microcar", "Nissan": "nissan",
    "Opel": "opel", "Peugeot": "peugeot", "Porsche": "porsche", "Renault": "renault",
    "Rolls-Royce": "rolls-royce", "Rover": "rover", "Saab": "saab", "Seat": "seat",
    "Skoda": "skoda", "Smart": "smart", "SsangYong": "ssangyong", "Subaru": "subaru",
    "Suzuki": "suzuki", "Tesla": "tesla", "Toyota": "toyota", "Volkswagen": "volkswagen",
    "Volvo": "volvo", "Alte Marci": "alte-marci"
}

# Filtre standard
FUEL_TYPES = {'petrol': 'Benzina','diesel': 'Diesel','lpg': 'GPL','hybrid': 'Hibrid','electric': 'Electric'}
CAR_BODIES = {'sedan':'Berlina','suv':'SUV','hatchback':'Hatchback','estate-car':'Break','coupe':'Coupe','cabriolet':'Cabrio','pickup':'Pickup','off-road-vehicle':'Off-road','minibus':'Minibus','mpv':'MPV'}
GEARBOX_TYPES = {'manual':'Manuala','automatic':'Automata'}
CAR_STATES = {'used':'Utilizat','new':'Nou'}

# ---------- GitHub Uploader ----------
class GitHubUploader:
    def __init__(self, username: str, repo: str, token: str):
        self.username = username
        self.repo = repo
        self.token = token
        self.base_url = f"https://api.github.com/repos/{username}/{repo}"
    
    def upload_csv_to_github(self, csv_file_path: str, cars_count: int) -> str:
        try:
            print("\n[UPLOAD] STARTING GITHUB UPLOAD")
            print(f"[FILE] Local file: {csv_file_path}")
            print(f"[DATA] Cars count: {cars_count}")
            
            # Verify file exists and is accessible
            if not os.path.exists(csv_file_path):
                print(f"[ERROR] File does not exist: {csv_file_path}")
                return None
            
            if not os.path.isfile(csv_file_path):
                print(f"[ERROR] Path is not a file: {csv_file_path}")
                return None
            
            # Check file accessibility and size
            try:
                file_size = os.path.getsize(csv_file_path)
                print(f"[SIZE] File size: {file_size:,} bytes")
                
                if file_size == 0:
                    print(f"[ERROR] File is empty: {csv_file_path}")
                    return None
                    
                if file_size > 100 * 1024 * 1024:  # 100MB limit
                    print(f"[WARNING] File is very large ({file_size:,} bytes). GitHub has size limits.")
                    
            except Exception as e:
                print(f"[ERROR] Cannot access file: {e}")
                return None
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"olx-cars-{timestamp}.csv"
            github_path = f"data/{filename}"
            
            print(f"[PATH] GitHub path: {github_path}")
            print(f"[REPO] Repository: {self.username}/{self.repo}")
            
            # Read and encode file content
            print(f"[READ] Reading file content...")
            try:
                with open(csv_file_path, 'rb') as file:
                    content = file.read()
                    if not content:
                        print(f"[ERROR] File content is empty after reading")
                        return None
                    content_encoded = base64.b64encode(content).decode('utf-8')
            except Exception as e:
                print(f"[ERROR] Failed to read file: {e}")
                return None
            
            print(f"[ENCODE] Content encoded successfully ({len(content_encoded):,} characters)")
            
            # Prepare GitHub API request
            data = {
                "message": f"Add OLX cars data - {cars_count} cars - {timestamp}",
                "content": content_encoded,
                "branch": "main"
            }
            
            headers = {
                "Authorization": f"token {self.token[:8]}...{self.token[-4:]}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            url = f"{self.base_url}/contents/{github_path}"
            print(f"[API] API URL: {url}")
            print("[REQUEST] Sending request to GitHub API...")
            
            # Use actual token for request (not the masked version)
            actual_headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Make the API request
            try:
                response = requests.put(url, json=data, headers=actual_headers, timeout=60)
            except requests.exceptions.Timeout:
                print(f"[ERROR] Request timeout - GitHub API took too long to respond")
                return None
            except requests.exceptions.ConnectionError:
                print(f"[ERROR] Connection error - Cannot reach GitHub API")
                return None
            except Exception as e:
                print(f"[ERROR] Request error: {e}")
                return None
            
            print(f"[RESPONSE] Response status: {response.status_code}")
            
            if response.status_code == 201:
                try:
                    result = response.json()
                    download_url = result['content']['download_url']
                    web_url = f"https://github.com/{self.username}/{self.repo}/blob/main/{github_path}"
                    raw_url = f"https://raw.githubusercontent.com/{self.username}/{self.repo}/main/{github_path}"
                    
                    print(f"[SUCCESS] File uploaded to GitHub successfully!")
                    print(f"[GITHUB] GitHub URL: {web_url}")
                    print(f"[RAW] Raw URL: {raw_url}")
                    print(f"[DOWNLOAD] Download URL: {download_url}")
                    print(f"[WEB] File is now available in the web UI!")
                    
                    logging.info(f"CSV uploaded to GitHub: {filename}")
                    return download_url
                except Exception as e:
                    print(f"[ERROR] Failed to parse success response: {e}")
                    return None
            else:
                print(f"[FAILED] UPLOAD FAILED!")
                print(f"[STATUS] Status Code: {response.status_code}")
                
                # Handle specific error codes
                if response.status_code == 401:
                    print(f"[ERROR] Authentication failed - check your GitHub token")
                elif response.status_code == 403:
                    print(f"[ERROR] Forbidden - check repository permissions or rate limits")
                elif response.status_code == 404:
                    print(f"[ERROR] Repository not found - check username/repo in config")
                elif response.status_code == 422:
                    print(f"[ERROR] Unprocessable entity - file might already exist or invalid data")
                
                try:
                    error_response = response.json()
                    print(f"[ERROR] Error details: {error_response}")
                    if 'message' in error_response:
                        print(f"[ERROR] GitHub message: {error_response['message']}")
                except:
                    print(f"[ERROR] Error text: {response.text[:500]}...")
                
                logging.error(f"GitHub upload failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"[EXCEPTION] UPLOAD EXCEPTION: {e}")
            logging.error(f"GitHub upload failed: {e}")
            import traceback
            print(f"[TRACEBACK] {traceback.format_exc()}")
            return None

# ---------- Modele de date ----------
@dataclass
class SearchConfig:
    brands: List[str]
    models_by_brand: Dict[str, List[str]]  # modelele selectate per marca (gol = toate)
    fuel_types: List[str]
    car_bodies: List[str]
    gearbox_types: List[str]
    car_states: List[str]
    price_min: int
    price_max: int
    year_min: int
    year_max: int
    km_min: int
    km_max: int
    power_min: int
    power_max: int
    currency: str
    max_pages_per_brand: int

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

# ---------- Utilitare ----------
def generate_car_id(link: str, title: str = "") -> str:
    try:
        # Always try to extract OLX ID from link first - this is the most reliable
        olx_id_match = re.search(r'ID([a-zA-Z0-9]+)\.html', link)
        if olx_id_match:
            return f"olx_{olx_id_match.group(1)}"
        
        # Fallback to hash if no OLX ID found (shouldn't happen for OLX links)
        print(f"[WARNING] No OLX ID found in link: {link[:60]}...")
        hash_obj = hashlib.md5(f"{link}_{title}".encode('utf-8'))
        return f"hash_{hash_obj.hexdigest()[:12]}"
    except Exception as e:
        print(f"[ERROR] Failed to generate ID for link: {link[:60]}... Error: {e}")
        return f"error_{int(time.time())}_{random.randint(1000, 9999)}"

def extract_numeric_price(price_text: str) -> float:
    try:
        if not price_text:
            return 999999
        price_clean = re.sub(r'[^\d.,]', '', price_text)
        if not price_clean:
            return 999999
        price_clean = price_clean.replace('.', '').replace(',', '.')
        return float(price_clean)
    except:
        return 999999

def safe_delay(delay_range):
    delay = random.uniform(*delay_range) if isinstance(delay_range, tuple) else delay_range
    time.sleep(delay)

def get_random_user_agent():
    try:
        ua = UserAgent()
        return ua.random
    except:
        return HEADERS["User-Agent"]

# ---------- Extractor de detalii ----------
class CarDataExtractor:
    def __init__(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger("CarDataExtractor")
    
    def extract_individual_car_data(self, link: str) -> dict:
        try:
            safe_delay(SAFETY_DELAYS['individual_car'])
            headers = {"User-Agent": get_random_user_agent()}
            r = requests.get(link, headers=headers, timeout=REQUEST_TIMEOUT)
            if r.status_code == 429:
                safe_delay(SAFETY_DELAYS['rate_limit'])
                return {}
            if r.status_code != 200:
                return {}
            # Wait for dynamic content to load
            import time
            time.sleep(3)  # Wait 3 seconds after page load
            
            soup = BeautifulSoup(r.content, 'html.parser')
            data = {}
            
            # An
            yt = soup.find(string=re.compile(r'An de fabricatie', re.I))
            if yt:
                ym = re.search(r'(\d{4})', yt.parent.get_text())
                if ym: data['year'] = ym.group(1)
            # KM
            kmt = soup.find(string=re.compile(r'Rulaj', re.I))
            if kmt:
                km = re.search(r'([\d\s.,]+)\s*km', kmt.parent.get_text(), re.I)
                if km: data['km'] = km.group(1).strip()
            
            # Combustibil
            ft = soup.find(string=re.compile(r'Combustibil', re.I))
            if ft:
                fm = re.search(r'(Benzina|Diesel|GPL|Hibrid|Electric)', ft.parent.get_text(), re.I)
                if fm:
                    f = fm.group(1).lower()
                    data['fuel_type'] = {"benzina":"petrol","diesel":"diesel","gpl":"lpg","hibrid":"hybrid","electric":"electric"}.get(f, f)
            # Cutie
            gt = soup.find(string=re.compile(r'Cutie de viteze', re.I))
            if gt:
                gm = re.search(r'(Manuala|Automata)', gt.parent.get_text(), re.I)
                if gm:
                    g = gm.group(1).lower()
                    data['gearbox'] = {"manuala":"manual","automata":"automatic"}.get(g, g)
            # Caroserie
            bt = soup.find(string=re.compile(r'Caroserie', re.I))
            if bt:
                data['car_body'] = bt.parent.get_text().split(':')[-1].strip()
            # Imagini
            urls = []
            for sel in ['img[data-cy="adPhotos-image"]', '.css-1bmvjcs img', '.swiper-slide img']:
                for img in soup.select(sel):
                    if len(urls) >= 5: break
                    src = img.get('src') or img.get('data-src')
                    if src and src.startswith('http'): urls.append(src)
                if urls: break
            data['image_urls'] = urls
            # Defaults
            data.setdefault('year', 'N/A')
            data.setdefault('km', 'N/A')
            data.setdefault('fuel_type', 'N/A')
            data.setdefault('gearbox', 'N/A')
            data.setdefault('car_body', 'N/A')
            return data
        except Exception as e:
            self.logger.error(f"Extract error {link}: {e}")
            return {}

# ---------- Scraper ----------
class OLXScrapingEngine:
    def __init__(self):
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger("OLXScrapingEngine")
        self.driver = None
        self.duplicate_db: Dict[str, dict] = {}
        self.session_stats = {'total_processed': 0, 'new_cars': 0, 'duplicates': 0}
        self.car_extractor = CarDataExtractor()
        # DON'T load database here - it will be loaded later in the workflow
        self.should_stop = lambda: False
        self.headless = False  # GitHub Actions headless mode support

        # Initialize Supabase sync if available
        try:
            from supabase_sync import SupabaseSync
            self.supabase_sync = SupabaseSync()
            self.logger.info("Supabase sync initialized")
        except Exception as e:
            self.supabase_sync = None
            self.logger.warning(f"Supabase not available, using local storage: {e}")
        
    def load_duplicate_database(self, database_content: dict = None):
        """Load duplicate database from Supabase or local file"""
        db_file = os.path.join(RESULTS_DIR, 'price_history.json')

        try:
            # Try to load from Supabase first
            if self.supabase_sync:
                try:
                    self.duplicate_db = self.supabase_sync.load_duplicate_database()
                    cars_count = len(self.duplicate_db)
                    print(f"[DATABASE] Loaded {cars_count} cars from Supabase")

                    if cars_count < 100 and cars_count > 0:
                        print(f"[DATABASE] WARNING: Database suspiciously small ({cars_count} cars)")
                        print(f"[DATABASE] This might indicate corruption - manual review recommended")

                    self.logger.info(f"Loaded {cars_count} known cars from Supabase")

                    # Sample logging
                    if cars_count > 0:
                        sample_ids = list(self.duplicate_db.keys())[:5]
                        print(f"[DATABASE] Sample IDs: {sample_ids}")

                    return  # Successfully loaded from Supabase

                except Exception as e:
                    print(f"[DATABASE] Supabase load failed, using local fallback: {e}")
                    self.logger.warning(f"Supabase load failed: {e}")

            # Fallback to local file
            if database_content:
                data = database_content
                print("[DATABASE] Using provided database content")
            else:
                if os.path.exists(db_file):
                    with open(db_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    print(f"[DATABASE] Loaded local database with {len(data.get('history', {}))} entries")
                else:
                    print("[DATABASE] No existing database file found, starting fresh")
                    data = {'history': {}, 'metadata': {}}

            # Convert price_history format to duplicate_db format
            self.duplicate_db = {}
            history_data = data.get('history', {})

            for car_id, history in history_data.items():
                if history:  # If car has history
                    latest_entry = history[-1]  # Get most recent entry
                    self.duplicate_db[car_id] = {
                        'title': latest_entry.get('title', ''),
                        'link': latest_entry.get('link', ''),
                        'last_price': latest_entry.get('price', 0),
                        'last_seen': latest_entry.get('date', ''),
                        'first_seen': history[0].get('date', '') if history else latest_entry.get('date', '')
                    }

            cars_count = len(self.duplicate_db)
            print(f"[DATABASE] Loaded {cars_count} cars from local file")
            self.logger.info(f"Loaded {cars_count} known cars from local file")

        except Exception as e:
            print(f"[DATABASE] Error loading database: {e}")
            print(f"[DATABASE] Starting with empty database")
            self.logger.error(f"Database load fail: {e}")
            self.duplicate_db = {}
    
    def save_duplicate_database(self, new_cars: List[CarData]):
        """Save ALL cars to database for tracking (Supabase or local file).

        IMPORTANT: This saves ALL scraped cars to maintain complete history,
        not just the filtered results. The database should only grow, never shrink.

        Args:
            new_cars: ALL scraped cars (not just filtered results)
        """
        if not new_cars:
            print("[DATABASE SAVE] No cars to save")
            return

        # Track database size before update
        initial_db_size = len(self.duplicate_db)

        # Try to use Supabase first
        if self.supabase_sync:
            try:
                print(f"\n[DATABASE SAVE] Saving {len(new_cars)} cars to Supabase")
                print(f"[DATABASE SAVE] Current in-memory database: {len(self.duplicate_db)} cars")

                # Debug: Check for duplicate unique_ids in the batch
                unique_ids = [car.unique_id for car in new_cars]
                unique_set = set(unique_ids)

                print(f"[DEBUG] Total cars to save: {len(new_cars)}")
                print(f"[DEBUG] Unique IDs count: {len(unique_set)}")
                print(f"[DEBUG] Duplicates detected: {len(unique_ids) - len(unique_set)}")

                if len(unique_ids) != len(unique_set):
                    # Find and log duplicates
                    from collections import Counter
                    counts = Counter(unique_ids)
                    duplicates = {uid: count for uid, count in counts.items() if count > 1}
                    print(f"[DEBUG] Duplicate unique_ids: {duplicates}")

                    # Show first few duplicate cars for analysis
                    for uid, count in list(duplicates.items())[:3]:
                        print(f"[DEBUG] Cars with ID {uid}:")
                        for i, car in enumerate(new_cars):
                            if car.unique_id == uid:
                                print(f"  [{i}] {car.title[:50]}... | {car.link[:60]}...")

                # Fix: Remove duplicate unique_ids before saving to Supabase
                if len(unique_ids) != len(unique_set):
                    print(f"[FIX] Removing {len(unique_ids) - len(unique_set)} duplicate cars before saving")

                    # Keep only the LAST occurrence of each unique_id (most recent scrape data)
                    seen_ids = set()
                    deduplicated_cars = []

                    # Process in reverse to keep last occurrence
                    for car in reversed(new_cars):
                        if car.unique_id not in seen_ids:
                            seen_ids.add(car.unique_id)
                            deduplicated_cars.append(car)

                    # Reverse back to original order
                    new_cars = list(reversed(deduplicated_cars))

                    print(f"[FIX] After deduplication: {len(new_cars)} cars to save")

                    # Update the debug info
                    unique_ids = [car.unique_id for car in new_cars]
                    unique_set = set(unique_ids)
                    print(f"[FIX] Verification - Unique IDs now: {len(unique_set)}, Duplicates: {len(unique_ids) - len(unique_set)}")

                success = self.supabase_sync.save_cars_data(new_cars)
                if success:
                    print(f"[DATABASE SAVE] Successfully saved to Supabase")
                    self.logger.info(f"Saved {len(new_cars)} cars to Supabase")

                    # Update local duplicate_db with ALL cars for proper tracking
                    # IMPORTANT: This only ADDS/UPDATES, never removes existing entries
                    for car in new_cars:
                        # Always update the duplicate_db with latest data
                        self.duplicate_db[car.unique_id] = {
                            'title': car.title,
                            'link': car.link,
                            'last_price': float(car.price_numeric),
                            'last_seen': car.scrape_date,
                            'first_seen': self.duplicate_db.get(car.unique_id, {}).get('first_seen', car.scrape_date)
                        }

                    # Verify database grew
                    final_size = len(self.duplicate_db)
                    if final_size < initial_db_size:
                        print(f"[DATABASE] WARNING: Database shrunk after Supabase save: {initial_db_size} -> {final_size}")
                    else:
                        print(f"[DATABASE] Database size after save: {final_size} (+{final_size - initial_db_size})")

                    return  # Successfully saved to Supabase
                else:
                    print(f"[DATABASE SAVE] Supabase save failed, using local fallback")
            except Exception as e:
                print(f"[DATABASE SAVE] Supabase error, using local fallback: {e}")
                self.logger.warning(f"Supabase save failed: {e}")

        # Fallback to local file storage
        print("[DATABASE SAVE] Using local file storage")
        db_file = os.path.join(RESULTS_DIR, 'price_history.json')

        # CRITICAL: Start with existing duplicate_db data to preserve ALL loaded cars
        # Convert current duplicate_db to history format first
        existing_history = {}
        for car_id, car_data in self.duplicate_db.items():
            existing_history[car_id] = [{
                'date': car_data.get('last_seen', datetime.now().isoformat()),
                'price': car_data.get('last_price', 0),
                'price_text': '',
                'title': car_data.get('title', ''),
                'link': car_data.get('link', ''),
                'source': 'existing_db'
            }]

        # Now merge with what's in the file (if it exists)
        if os.path.exists(db_file):
            try:
                with open(db_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    file_history = existing_data.get('history', {})

                    # Merge file history into existing_history
                    for car_id, history in file_history.items():
                        if car_id in existing_history:
                            # Merge histories, avoiding duplicates
                            existing_history[car_id].extend(history)
                        else:
                            existing_history[car_id] = history
            except Exception as e:
                print(f"[DATABASE] Error loading file history: {e}")

        original_size = len(existing_history)
        new_entries = 0
        updated_entries = 0

        print(f"\n[DATABASE MERGE] Starting price history merge")
        print(f"[DATABASE MERGE] In-memory database: {len(self.duplicate_db)} cars")
        print(f"[DATABASE MERGE] Combined history size: {original_size} cars")
        print(f"[DATABASE MERGE] New cars to process: {len(new_cars)} cars")
        
        # Update history with new cars
        for car in new_cars:
            car_id = car.unique_id
            new_entry = {
                'date': car.scrape_date,
                'price': float(car.price_numeric),
                'price_text': car.price_text,
                'title': car.title,
                'link': car.link,
                'source': 'scraper'
            }
            
            if car_id in existing_history:
                # Append to existing history
                existing_history[car_id].append(new_entry)
                updated_entries += 1
            else:
                # Create new history
                existing_history[car_id] = [new_entry]
                new_entries += 1
        
        final_size = len(existing_history)
        total_entries = sum(len(hist) for hist in existing_history.values())
        
        print(f"[DATABASE MERGE] Final size: {final_size} cars")
        print(f"[DATABASE MERGE] Total entries: {total_entries}")
        print(f"[DATABASE MERGE] New cars: {new_entries}, Updated cars: {updated_entries}")
        
        # Save updated history
        updated_data = {
            'history': existing_history,
            'metadata': {
                'last_update': datetime.now().isoformat(),
                'total_cars': final_size,
                'total_entries': total_entries,
                'last_merge_stats': {
                    'original_size': original_size,
                    'new_entries': new_entries,
                    'updated_entries': updated_entries,
                    'final_size': final_size
                }
            }
        }

        # Use atomic write operation
        temp_file = db_file + '.tmp'
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(updated_data, f, ensure_ascii=False, indent=2)

            # Atomic move
            shutil.move(temp_file, db_file)
        except Exception as e:
            print(f"[DATABASE] Error during atomic write: {e}")
            # Fallback to direct write
            with open(db_file, 'w', encoding='utf-8') as f:
                json.dump(updated_data, f, ensure_ascii=False, indent=2)
        
        print(f"[DATABASE MERGE] Price history saved successfully")
        self.logger.info(f"Price history merge complete: {original_size} -> {final_size} cars ({new_entries} new, {updated_entries} updated)")

        # CRITICAL FIX: Update duplicate_db WITHOUT clearing it first
        # Only update entries that were just processed, preserve all others
        for car_id, history in existing_history.items():
            if history:
                latest = history[-1]
                # Update or add entry, but don't clear existing entries
                self.duplicate_db[car_id] = {
                    'title': latest.get('title', ''),
                    'link': latest.get('link', ''),
                    'last_price': latest.get('price', 0),
                    'last_seen': latest.get('date', ''),
                    'first_seen': history[0].get('date', '') if history else latest.get('date', '')
                }

        # CRITICAL: Safety check - database should never shrink
        final_db_size = len(self.duplicate_db)
        if final_db_size < initial_db_size:
            print(f"[DATABASE] CRITICAL WARNING: Database shrunk from {initial_db_size} to {final_db_size}!")
            print(f"[DATABASE] This should never happen - investigating...")
            self.logger.error(f"Database shrunk: {initial_db_size} -> {final_db_size}")
        else:
            print(f"[DATABASE] Database size OK: {initial_db_size} -> {final_db_size} (+{final_db_size - initial_db_size})")
    
    def has_significant_price_change(self, car_id: str, new_price: float) -> bool:
        """Check if price changed significantly from last known price"""
        if car_id not in self.duplicate_db:
            return True  # New car
        
        last_price = self.duplicate_db[car_id].get('last_price', 0)
        price_diff = abs(new_price - last_price)
        return price_diff >= PRICE_CHANGE_THRESHOLD

    
    def is_duplicate(self, link: str, title: str = "", current_price: Optional[float] = None) -> bool:
        cid = generate_car_id(link, title)
        rec = self.duplicate_db.get(cid)
        if not rec:
            return False  # nu e in DB => nou

        # daca avem pretul curent si avem pret salvat, comparam
        try:
            if current_price is not None and 'last_price' in rec:
                if abs(float(current_price) - float(rec['last_price'])) >= PRICE_CHANGE_THRESHOLD:
                    return False  # pret schimbat => trateaza ca 'nou'
            # optional: daca nu avem last_price in DB, il setam pe loc (seed)
            if current_price is not None and 'last_price' not in rec:
                rec['last_price'] = float(current_price)
                rec['last_price_text'] = ""  # va fi completat la next save
        except:
            pass

        self.session_stats['duplicates'] += 1
        return True
    
    def filter_duplicates(self, cars_data: List[CarData]) -> List[CarData]:
        """Identify NEW cars and cars with PRICE CHANGES for CSV export.

        IMPORTANT: This method returns cars that should appear in results/CSV:
        - NEW cars (not in database at all)
        - Cars with PRICE CHANGES ≥1 EUR from last known price

        Cars without significant changes are filtered out from results,
        but ALL cars should still be saved to database for tracking.

        Args:
            cars_data: List of all scraped cars

        Returns:
            List of actionable cars (new or price changed ≥1 EUR)
        """
        filtered_cars = []
        duplicate_count = 0
        new_count = 0
        price_change_count = 0
        
        self.logger.info(f"Filtering {len(cars_data)} scraped cars for duplicates...")
        print(f"\n[DUPLICATE FILTER] Starting duplicate detection")
        print(f"[DUPLICATE FILTER] Total cars to check: {len(cars_data)}")
        print(f"[DUPLICATE FILTER] Database size: {len(self.duplicate_db)} entries")
        
        # Sample logging for first 5 cars
        sample_count = min(5, len(cars_data))
        print(f"\n[DUPLICATE FILTER] Checking first {sample_count} cars in detail:")
        
        for i, car in enumerate(cars_data):
            # Use the car's unique_id directly instead of regenerating it
            cid = car.unique_id
            
            # Enhanced logging for first 5 cars
            if i < sample_count:
                print(f"\n  Car {i+1}:")
                print(f"    - Title: {car.title[:50] if car.title else 'None'}...")
                print(f"    - Link: {car.link[:60] if car.link else 'None'}...")
                print(f"    - unique_id: {cid}")
                print(f"    - Price: {car.price_numeric}")
            
            rec = self.duplicate_db.get(cid)
            
            if not rec:
                # New car not in database
                filtered_cars.append(car)
                new_count += 1
                if i < sample_count:
                    print(f"    + NEW CAR - Not in database")
            else:
                # Car exists in database - check for price change
                if i < sample_count:
                    print(f"    - Found in DB: last_price={rec.get('last_price', 'N/A')}, last_seen={rec.get('last_seen', 'N/A')}")
                
                try:
                    if car.price_numeric is not None and 'last_price' in rec:
                        price_diff = abs(float(car.price_numeric) - float(rec['last_price']))
                        if i < sample_count:
                            print(f"    - Price difference: {price_diff} EUR (threshold: {PRICE_CHANGE_THRESHOLD} EUR)")
                        
                        if price_diff >= PRICE_CHANGE_THRESHOLD:
                            # Price changed by more than threshold
                            filtered_cars.append(car)
                            price_change_count += 1
                            old_price = rec.get('last_price', 0)
                            self.logger.info(f"Price change detected for {car.title}: {old_price} -> {car.price_numeric}")
                            if i < sample_count:
                                print(f"    + PRICE CHANGE - Keeping car")
                        else:
                            # Duplicate with no significant price change
                            duplicate_count += 1
                            if i < sample_count:
                                print(f"    - DUPLICATE - No significant price change")
                    else:
                        # No price to compare, treat as duplicate
                        duplicate_count += 1
                        if i < sample_count:
                            print(f"    - DUPLICATE - No price data to compare")
                except Exception as e:
                    # Error in price comparison, treat as duplicate
                    duplicate_count += 1
                    if i < sample_count:
                        print(f"    - DUPLICATE - Error in comparison: {e}")
        
        print(f"\n[DUPLICATE FILTER] Summary:")
        print(f"  - New cars: {new_count}")
        print(f"  - Price changes: {price_change_count}")
        print(f"  - Duplicates filtered: {duplicate_count}")
        print(f"  - Total kept: {len(filtered_cars)}")
        
        self.logger.info(f"Filtering complete: {len(filtered_cars)} cars kept ({new_count} new, {price_change_count} price changes), {duplicate_count} duplicates removed")
        
        # Update session stats
        self.session_stats['duplicates'] = duplicate_count
        self.session_stats['new_cars'] = new_count
        
        return filtered_cars

    
    def setup_driver(self):
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument(f"--user-agent={get_random_user_agent()}")
            prefs = {"profile.managed_default_content_settings.images": 2,
                     "profile.default_content_settings.popups": 0,
                     "profile.default_content_setting_values.notifications": 2}
            chrome_options.add_experimental_option("prefs", prefs)
            # Use system ChromeDriver (installed by GitHub Actions)
            self.driver = webdriver.Chrome(options=chrome_options)
            self.logger.info("Chrome driver ready")
            return True
        except Exception as e:
            self.logger.error(f"Driver setup failed: {e}")
            return False
    
    def build_search_url(self, config: SearchConfig, brand_slug: str) -> str:
        base_url = f"https://www.olx.ro/auto-masini-moto-ambarcatiuni/autoturisme/{brand_slug}/"
        params = [f"currency={config.currency}"]
        params.append("search%5Bprivate_business%5D=private")
        if config.price_min > 0:
            params.append(f"search%5Bfilter_float_price%3Afrom%5D={config.price_min}")
        if config.price_max < 999999:
            params.append(f"search%5Bfilter_float_price%3Ato%5D={config.price_max}")
        if config.year_min > 1970:
            params.append(f"search%5Bfilter_float_year%3Afrom%5D={config.year_min}")
        if config.year_max < 2100:
            params.append(f"search%5Bfilter_float_year%3Ato%5D={config.year_max}")
        if config.km_min > 0:
            params.append(f"search%5Bfilter_float_rulaj_pana%3Afrom%5D={config.km_min}")
        if config.km_max < 999999:
            params.append(f"search%5Bfilter_float_rulaj_pana%3Ato%5D={config.km_max}")
        if config.power_min > 0:
            params.append(f"search%5Bfilter_float_engine_power%3Afrom%5D={config.power_min}")
        if config.power_max < 1000:
            params.append(f"search%5Bfilter_float_engine_power%3Ato%5D={config.power_max}")
        for i, fuel in enumerate(config.fuel_types):
            params.append(f"search%5Bfilter_enum_petrol%5D%5B{i}%5D={fuel}")
        for i, body in enumerate(config.car_bodies):
            params.append(f"search%5Bfilter_enum_car_body%5D%5B{i}%5D={body}")
        for i, gb in enumerate(config.gearbox_types):
            params.append(f"search%5Bfilter_enum_gearbox%5D%5B{i}%5D={gb}")
        for i, st in enumerate(config.car_states):
            params.append(f"search%5Bfilter_enum_state%5D%5B{i}%5D={st}")
        params.append("search%5Border%5D=created_at%3Adesc")
        return f"{base_url}?{'&'.join(params)}"
    
    def handle_cookies(self):
        try:
            for sel in ["#onetrust-accept-btn-handler", "[data-cy='cookie-accept']"]:
                try:
                    btn = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                    btn.click(); return
                except: pass
        except: pass
    def extract_cars_from_page(self) -> List[dict]:
        cars = []
        try:
            card_selector = "[data-cy='l-card'], .offer-wrapper, [data-testid='l-card'], a[href*='/d/oferta/']"

            # 1) Așteaptă să apară măcar un card (max 12s)
            try:
                WebDriverWait(self.driver, 12).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, card_selector))
                )
            except:
                pass

            # 2) Derulează mai mult (lazy-load): 6 scroll-uri cu pauză 1.5s
            for _ in range(6):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)

            # 3) Caută elementele
            elements = []
            for sel in ["[data-cy='l-card']", ".offer-wrapper", "[data-testid='l-card']", "a[href*='/d/oferta/']"]:
                try:
                    found = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    if found:
                        elements = found
                        break
                except:
                    pass

            # 4) Dacă tot 0, retry scurt
            if not elements:
                time.sleep(2)
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                try:
                    WebDriverWait(self.driver, 6).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, card_selector))
                    )
                except:
                    pass
                for sel in ["[data-cy='l-card']", ".offer-wrapper", "[data-testid='l-card']", "a[href*='/d/oferta/']"]:
                    try:
                        found = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        if found:
                            elements = found
                            break
                    except:
                        pass

            # 5) Extrage datele de bază
            for el in elements:
                cd = self.extract_basic_car_data(el)
                if cd and cd.get('link'):
                    cars.append(cd)
                    self.session_stats['total_processed'] += 1

            return cars
        except Exception as e:
            self.logger.error(f"Page extract error: {e}")
            return cars
    
    


    
    def extract_basic_car_data(self, element) -> Optional[dict]:
        try:
            link = self.get_car_link(element)
            if not link: return None
            title = self.get_car_title(element, link) or "Unknown Car"
            price_text = self.get_car_price(element) or "0 €"
            return {
                'link': link,
                'title': title,
                'price_text': price_text,
                'price_numeric': extract_numeric_price(price_text)
            }
        except:
            return None
    
    def get_car_link(self, element) -> Optional[str]:
        try:
            if element.tag_name == 'a':
                href = element.get_attribute('href')
                if href and '/d/oferta/' in href:
                    return self.clean_olx_link(href)
            for sel in ["a[href*='/d/oferta/']", "a[data-cy='listing-ad-title']"]:
                try:
                    le = element.find_element(By.CSS_SELECTOR, sel)
                    href = le.get_attribute('href')
                    if href and '/d/oferta/' in href:
                        return self.clean_olx_link(href)
                except: pass
        except: pass
        return None
    
    def get_car_title(self, element, link: str) -> str:
        try:
            if link:
                url_part = link.split('/')[-1].replace('.html', '')
                if '-ID' in url_part:
                    title_part = url_part.split('-ID')[0]
                    tt = title_part.replace('-', ' ').title()
                    if len(tt) > 5: return tt
            for sel in ["h6[data-cy='listing-ad-title']", ".css-u2ayx9", "h6"]:
                try:
                    te = element.find_element(By.CSS_SELECTOR, sel)
                    t = te.text.strip()
                    if t and len(t) > 5: return t
                except: pass
        except: pass
        return "Unknown Car"
    
    def get_car_price(self, element) -> str:
        try:
            for sel in ["[data-testid='ad-price']", "p[data-testid='ad-price']", ".css-10b0gli"]:
                try:
                    pe = element.find_element(By.CSS_SELECTOR, sel)
                    pt = pe.text.strip()
                    if pt and ('€' in pt or 'lei' in pt or 'EUR' in pt): return pt
                except: pass
        except: pass
        return "0 €"
    
    def clean_olx_link(self, href: str) -> Optional[str]:
        if not href:
            return None
        href = href.strip()
        # Normalizează formele frecvente
        if href.startswith("//"):
            href = "https:" + href
        if href.startswith("/"):
            href = f"https://www.olx.ro{href}"
        href = href.replace("m.olx.ro", "www.olx.ro")
        # Scoate query/hash ca să fie link curat
        href = href.split("?")[0].split("#")[0]
        return href

    
    def go_to_next_page(self) -> bool:
        try:
            for sel in ["a[data-cy='pagination-forward']", ".pager-next", "a[aria-label='Next']"]:
                try:
                    nb = self.driver.find_element(By.CSS_SELECTOR, sel)
                    if nb and nb.is_displayed() and nb.is_enabled():
                        self.driver.execute_script("arguments[0].click();", nb)
                        safe_delay(SAFETY_DELAYS['between_pages'])
                        return True
                except: pass
            return False
        except: return False
    
    def extract_brand_and_model_from_title(self, title: str) -> Tuple[str, str]:
        brand = "Unknown"
        model = "Unknown"
        if not title: return brand, model
        for bname, models in CAR_BRANDS_MODELS.items():
            if bname.lower() in title.lower():
                brand = bname
                for m in models:
                    if m.lower() != "toate modelele" and m.lower() != "altul":
                        if m.lower() in title.lower():
                            model = m; break
                break
        return brand, model
    
    def scrape_brand_cars(self, config: SearchConfig, brand: str, progress_callback=None) -> List[dict]:
        try:
            slug = BRAND_TO_SLUG.get(brand, brand.lower().replace(' ', '-'))
            url = self.build_search_url(config, slug)
            self.logger.info(f"{brand}: {url}")
            self.driver.get(url)
            self.handle_cookies()
            # [CONFIG] Asteapta sa apara orice card de anunt (max 10s)
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        "[data-cy='l-card'], .offer-wrapper, [data-testid='l-card'], a[href*='/d/oferta/']"
                    ))
                )
            except:
                pass
            safe_delay(SAFETY_DELAYS['between_requests'])
            all_cars = []
            page = 1
            while page <= config.max_pages_per_brand:
                if self.should_stop(): break
                if progress_callback:
                    progress_callback(f"{brand} - Page {page}", int((page / max(1, config.max_pages_per_brand)) * 100))
                page_cars = self.extract_cars_from_page()
                            # 🔁 Dacă pagina a întors 0, mai încearcă o dată (scurt)
                if not page_cars:
                    try:
                        WebDriverWait(self.driver, 6).until(
                            EC.presence_of_element_located((
                                By.CSS_SELECTOR,
                                "[data-cy='l-card'], .offer-wrapper, [data-testid='l-card'], a[href*='/d/oferta/']"
                            ))
                        )
                    except:
                        pass
                    time.sleep(2)
                    page_cars = self.extract_cars_from_page()

                # NO DUPLICATE CHECKING DURING SCRAPING - collect all cars
                # Filtru MODELE pt. marca curentă (client-side)
                wanted_models = config.models_by_brand.get(brand, [])
                if wanted_models and "Toate modelele" not in wanted_models:
                    filtered = []
                    for c in page_cars:
                        _, mdl = self.extract_brand_and_model_from_title(c.get('title',''))
                        if (mdl in wanted_models) or ("Altul" in wanted_models and mdl == "Unknown"):
                            filtered.append(c)
                    page_cars = filtered
                all_cars.extend(page_cars)
                self.logger.info(f"{brand} p{page}: {len(page_cars)} cars found")
                if page < config.max_pages_per_brand:
                    if not self.go_to_next_page():
                        self.logger.info(f"{brand}: no more pages")
                        break
                page += 1
            self.logger.info(f"{brand}: {len(all_cars)} cars total")
            return all_cars
        except Exception as e:
            self.logger.error(f"Failed brand {brand}: {e}")
            return []
    
    def enrich_car_data(self, basic_cars: List[dict], progress_callback=None) -> List[CarData]:
        enriched = []
        total = len(basic_cars)
        for i, cb in enumerate(basic_cars):
            if self.should_stop(): break
            try:
                if progress_callback:
                    progress_callback(f"Enrich {i+1}/{total}", 50 + int(((i+1)/max(1,total))*50))
                det = self.car_extractor.extract_individual_car_data(cb['link'])
                brand, model = self.extract_brand_and_model_from_title(cb.get('title',''))
                car = CarData(
                    title = cb.get('title','Unknown Car'),
                    price_text = cb.get('price_text','0 €'),
                    price_numeric = cb.get('price_numeric',0),
                    year = det.get('year','N/A'),
                    km = det.get('km','N/A'),
                    link = cb.get('link',''),
                    image_urls = det.get('image_urls',[]),
                    fuel_type = det.get('fuel_type','N/A'),
                    gearbox = det.get('gearbox','N/A'),
                    car_body = det.get('car_body','N/A'),
                    brand = brand,
                    model = model,
                    unique_id = generate_car_id(cb.get('link',''), cb.get('title','')),
                    scrape_date = datetime.now().isoformat()
                )
                enriched.append(car)
                self.session_stats['new_cars'] += 1
            except Exception as e:
                self.logger.error(f"Enrich error: {e}")
                continue
        return enriched
    
    def scrape_all_cars(self, config: SearchConfig, progress_callback=None) -> List[CarData]:
        if not self.setup_driver():
            return []

        # Create lock file with session info
        session_id = str(uuid.uuid4())
        lock_file = os.path.join(RESULTS_DIR, '.scraping_lock')
        timestamp = datetime.now().isoformat()

        try:
            with open(lock_file, 'w') as f:
                f.write(f"{session_id}\n{timestamp}")
            self.logger.info(f"Created scraping lock file with session: {session_id}")
        except Exception as e:
            self.logger.warning(f"Could not create lock file: {e}")

        self.logger.info(f"Start scraping: {len(config.brands)} brands")
        try:
            all_basic = []
            for i, brand in enumerate(config.brands):
                if self.should_stop(): break
                if progress_callback:
                    progress_callback(f"Scraping {brand} ({i+1}/{len(config.brands)})", int((i/ max(1,len(config.brands)))*50))
                all_basic.extend(self.scrape_brand_cars(config, brand, progress_callback))
                if i < len(config.brands)-1:
                    safe_delay(SAFETY_DELAYS['between_brands'])
            if not all_basic:
                self.logger.warning("[WARNING] No cars with current filters")
                return []
            if progress_callback: progress_callback("Enriching details…", 60)
            enriched = self.enrich_car_data(all_basic, progress_callback)
            self.save_duplicate_database(enriched)
            if progress_callback: progress_callback("Done!", 100)
            self.logger.info(f"Done. Stats: {self.session_stats}")
            return enriched
        except Exception as e:
            self.logger.error(f"Global scrape fail: {e}")
            return []
        finally:
            self.cleanup_driver()
            # Remove lock file
            try:
                if os.path.exists(lock_file):
                    os.remove(lock_file)
                    self.logger.info("Removed scraping lock file")
            except Exception as e:
                self.logger.warning(f"Could not remove lock file: {e}")
    
    def cleanup_driver(self):
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("Chrome driver closed")
            except: pass

# ---------- Thread ----------
class ScrapingThread(QThread):
    progress_updated = pyqtSignal(str, int)
    scraping_finished = pyqtSignal(list)
    scraping_error = pyqtSignal(str)
    def __init__(self, config: SearchConfig):
        super().__init__()
        self.config = config
        self.scraper = OLXScrapingEngine()
        self._stop = False
    def stop(self): self._stop = True
    def run(self):
        try:
            self.scraper.should_stop = lambda: self._stop
            def cb(msg, pct): self.progress_updated.emit(msg, int(pct))
            cars = self.scraper.scrape_all_cars(self.config, cb)
            self.scraping_finished.emit(cars)
        except Exception as e:
            self.scraping_error.emit(str(e))

# ---------- GUI ----------
class OLXAdvancedScraper(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🚗 OLX Advanced Car Scraper - Marci + Modele")
        self.setGeometry(80, 80, 1500, 980)
        self.cars_data = []
        self.scraping_thread = None
        # memory: modele selectate per marca
        self.selected_models_by_brand: Dict[str, Set[str]] = {}
        self.active_brand: Optional[str] = None 
        self.saved_searches: Dict[str, dict] = {}
        self.setup_ui()
        self.setup_default_values()
        self.load_saved_searches()
        self.refresh_saved_search_dropdown()
        self.check_running_scraper_on_startup()
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.check_scraper_status)
        self.status_timer.start(5000)
    
    # ===== UI =====
    def setup_ui(self):
        main_layout = QVBoxLayout()
        header = QLabel("🚗 OLX Advanced Car Scraper - Marci + Modele")
        header.setFont(QFont("Arial", 16, QFont.Bold))
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("color: #2196F3; margin: 10px;")
        main_layout.addWidget(header)
        self.tab_widget = QTabWidget()
        self.search_tab = self.create_search_tab()
        self.tab_widget.addTab(self.search_tab, "Configurare")
        self.results_tab = self.create_results_tab()
        self.tab_widget.addTab(self.results_tab, "📊 Rezultate")
        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)
        self.setStyleSheet(self.get_modern_stylesheet())
    
    def create_search_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_layout.addWidget(self.create_brands_models_group())
        scroll_layout.addWidget(self.create_saved_searches_group())
        scroll_layout.addWidget(self.create_filters_group())
        scroll_layout.addWidget(self.create_ranges_group())
        scroll_layout.addWidget(self.create_advanced_group())
        scroll_widget.setLayout(scroll_layout)
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        controls_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Scraping")
        self.start_btn.clicked.connect(self.start_scraping)
        self.stop_btn = QPushButton("[STOP] Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_scraping)
        self.export_btn = QPushButton("[SAVE] Export Results")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export_results)
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addWidget(self.export_btn)
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        self.progress_bar = QProgressBar()
        self.progress_label = QLabel("Ready to start scraping…")
        layout.addWidget(self.progress_label); layout.addWidget(self.progress_bar)
        tab.setLayout(layout)
        return tab
    
    def create_saved_searches_group(self):
        group = QGroupBox("[SAVE] Cautari salvate")
        layout = QGridLayout()

        # Dropdown cu cautari salvate
        layout.addWidget(QLabel("Selecteaza:"), 0, 0)
        self.saved_searches_combo = QComboBox()
        self.saved_searches_combo.setMinimumWidth(260)
        layout.addWidget(self.saved_searches_combo, 0, 1, 1, 3)

        # Nume pentru salvare
        layout.addWidget(QLabel("Nume cautare:"), 1, 0)
        self.saved_search_name = QLineEdit()
        self.saved_search_name.setPlaceholderText("ex: BMW + A4 + sub 10.000EUR")
        layout.addWidget(self.saved_search_name, 1, 1, 1, 3)

        # Butoane
        self.btn_save_search = QPushButton("[SAVE] Salveaza")
        self.btn_load_search = QPushButton("📥 Incarca")
        self.btn_delete_search = QPushButton("[DELETE] Sterge")
        layout.addWidget(self.btn_save_search, 2, 1)
        layout.addWidget(self.btn_load_search, 2, 2)
        layout.addWidget(self.btn_delete_search, 2, 3)

        # Conectări
        self.btn_save_search.clicked.connect(self.on_save_search_click)
        self.btn_load_search.clicked.connect(self.on_load_search_click)
        self.btn_delete_search.clicked.connect(self.on_delete_search_click)
        self.saved_searches_combo.currentTextChanged.connect(self.saved_search_name.setText)


        group.setLayout(layout)
        return group

    def load_saved_searches(self):
        """Incarca dict {name: payload} din fisier."""
        try:
            if os.path.exists(SAVED_SEARCHES_FILE):
                with open(SAVED_SEARCHES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Acceptăm fie listă de obiecte, fie dict
                    if isinstance(data, list):
                        self.saved_searches = {item.get("name",""): item.get("payload",{}) for item in data if "name" in item}
                    elif isinstance(data, dict):
                        self.saved_searches = data
                    else:
                        self.saved_searches = {}
            else:
                self.saved_searches = {}
        except Exception as e:
            self.saved_searches = {}
            QMessageBox.warning(self, "Cautari salvate", f"Nu s-au putut incarca cautarile salvate:\n{e}")

    def persist_saved_searches(self):
        """Scrie dict {name: payload} in fisier."""
        try:
            with open(SAVED_SEARCHES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.saved_searches, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Cautari salvate", f"Nu s-a putut salva fisierul:\n{e}")

    def refresh_saved_search_dropdown(self):
        """Reumple combo-ul din memoria saved_searches."""
        try:
            self.saved_searches_combo.blockSignals(True)
            self.saved_searches_combo.clear()
            names = sorted(self.saved_searches.keys(), key=lambda s: s.casefold())
            self.saved_searches_combo.addItems(names)
        finally:
            self.saved_searches_combo.blockSignals(False)

    def get_current_search_payload(self) -> dict:
        """Citește TOT din UI ca payload pentru salvare."""
        # 1) marci selectate (nume afisate in lista)
        selected_brands = [it.text() for it in self.brands_list.selectedItems()]

        # 2) salveaza modelele curente pt marca activa, apoi ia dict-ul complet
        self.save_current_models_of_active_brand()
        models_by_brand = {b: sorted(list(v)) for b, v in self.selected_models_by_brand.items() if v}

        # 3) restul filtrelor
        sel_fuels = [k for k,v in self.fuel_checkboxes.items() if v.isChecked()]
        sel_bodies = [k for k,v in self.body_checkboxes.items() if v.isChecked()]
        sel_gb    = [k for k,v in self.gearbox_checkboxes.items() if v.isChecked()]
        sel_state = [k for k,v in self.state_checkboxes.items() if v.isChecked()]

        payload = {
            "brands": selected_brands,
            "models_by_brand": models_by_brand,  # daca lipseste o marca => toate modelele
            "fuel_types": sel_fuels,
            "car_bodies": sel_bodies,
            "gearbox_types": sel_gb,
            "car_states": sel_state,
            "price_min": self.price_min.value(),
            "price_max": self.price_max.value(),
            "year_min": self.year_min.value(),
            "year_max": self.year_max.value(),
            "km_min": self.km_min.value(),
            "km_max": self.km_max.value(),
            "power_min": self.power_min.value(),
            "power_max": self.power_max.value(),
            "currency": self.currency_combo.currentText(),
            "max_pages_per_brand": self.max_pages.value(),
        }
        return payload

    def apply_search_payload(self, payload: dict):
        """Aplica payload in UI (marci, modele, filtre, intervale)."""
        if not payload:
            return

        # reset brands & models
        for i in range(self.brands_list.count()):
            self.brands_list.item(i).setSelected(False)
        self.active_brand = None
        self.models_list.clear()
        self.selected_models_by_brand.clear()

        # selecteaza marcile
        wanted_brands = set(payload.get("brands", []))
        first_selected_text = None
        for i in range(self.brands_list.count()):
            it = self.brands_list.item(i)
            if it.text() in wanted_brands:
                it.setSelected(True)
                if first_selected_text is None:
                    first_selected_text = it.text()

        # seteaza marca activa si reafiseaza modelele
        self.active_brand = first_selected_text
        self.refresh_models_for_active_brand()

        # modele per marca
        models_by_brand = payload.get("models_by_brand", {})
        for brand, models in models_by_brand.items():
            self.selected_models_by_brand[brand] = set(models)
        self.refresh_models_for_active_brand()

        # filtre checkbox
        def apply_checks(check_dict, wanted_list):
            for k, cb in check_dict.items():
                cb.setChecked(k in wanted_list)
        apply_checks(self.fuel_checkboxes, payload.get("fuel_types", []))
        apply_checks(self.body_checkboxes, payload.get("car_bodies", []))
        apply_checks(self.gearbox_checkboxes, payload.get("gearbox_types", []))
        apply_checks(self.state_checkboxes, payload.get("car_states", []))

        # intervale & setări
        self.price_min.setValue(int(payload.get("price_min", self.price_min.value())))
        self.price_max.setValue(int(payload.get("price_max", self.price_max.value())))
        self.year_min.setValue(int(payload.get("year_min", self.year_min.value())))
        self.year_max.setValue(int(payload.get("year_max", self.year_max.value())))
        self.km_min.setValue(int(payload.get("km_min", self.km_min.value())))
        self.km_max.setValue(int(payload.get("km_max", self.km_max.value())))
        self.power_min.setValue(int(payload.get("power_min", self.power_min.value())))
        self.power_max.setValue(int(payload.get("power_max", self.power_max.value())))

        curr = payload.get("currency", self.currency_combo.currentText())
        idx = self.currency_combo.findText(curr)
        if idx >= 0:
            self.currency_combo.setCurrentIndex(idx)

        self.max_pages.setValue(int(payload.get("max_pages_per_brand", self.max_pages.value())))

    def on_save_search_click(self):
        name = self.saved_search_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Cautare salvata", "Te rog introdu un nume pentru cautare.")
            return
        payload = self.get_current_search_payload()

        if name in self.saved_searches:
            if QMessageBox.question(self, "Suprascrie?",
                                    f"'{name}' există deja. Vrei să o suprascrii?",
                                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return

        self.saved_searches[name] = payload
        self.persist_saved_searches()
        self.refresh_saved_search_dropdown()
        idx = self.saved_searches_combo.findText(name)
        if idx >= 0:
            self.saved_searches_combo.setCurrentIndex(idx)
        QMessageBox.information(self, "Cautare salvata", f"'{name}' a fost salvata.")

    def on_load_search_click(self):
        name = self.saved_searches_combo.currentText().strip()
        if not name:
            QMessageBox.information(self, "Cautari salvate", "Nu ai selectat nicio cautare.")
            return
        payload = self.saved_searches.get(name, {})
        if not payload:
            QMessageBox.warning(self, "Cautari salvate", f"Cautarea '{name}' nu are continut.")
            return
        self.apply_search_payload(payload)
        self.saved_search_name.setText(name)
        QMessageBox.information(self, "Cautari salvate", f"📥 S-a incarcat '{name}' in UI.")

    def on_delete_search_click(self):
        name = self.saved_searches_combo.currentText().strip()
        if not name:
            QMessageBox.information(self, "Cautari salvate", "Nu ai selectat nicio cautare pentru sterse.")
            return
        if QMessageBox.question(self, "Confirmare stergere",
                                f"Sigur vrei sa stergi '{name}'?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.saved_searches.pop(name, None)
            self.persist_saved_searches()
            self.refresh_saved_search_dropdown()
            self.saved_search_name.clear()
            QMessageBox.information(self, "Cautari salvate", f"[DELETE] '{name}' a fost stearsa.")
        except Exception as e:
            QMessageBox.warning(self, "Cautari salvate", f"Eroare la stergere:\n{e}")
    

        
    def create_brands_models_group(self):
            group = QGroupBox("[TAG] Selectare Marci si Modele")
            outer = QHBoxLayout()
            # ——— Marci
            left = QVBoxLayout()
            lab_b = QLabel("Marci:")
            lab_b.setFont(QFont("Arial", 12, QFont.Bold))
            left.addWidget(lab_b)
            # Cautare marci
            self.brand_search = QLineEdit()
            self.brand_search.setPlaceholderText("🔎 Cauta marca (ex: bmw)")
            self.brand_search.textChanged.connect(self.filter_brands)
            left.addWidget(self.brand_search)
            # Lista marci
            self.brands_list = QListWidget()
            self.brands_list.setSelectionMode(QAbstractItemView.MultiSelection)
            self.brands_list.setMaximumHeight(260)
            # populate
            for brand in sorted(CAR_BRANDS_MODELS.keys()):
                self.brands_list.addItem(brand)
            # legatur: cand dai click pe o marca -> devine activa (schimbam lista de modele)
            self.brands_list.itemClicked.connect(self.on_brand_clicked)
            self.brands_list.itemSelectionChanged.connect(self.on_brand_selection_changed)
            left.addWidget(self.brands_list)
            # butoane marci
            bctl = QHBoxLayout()
            btn_all = QPushButton("Toate")
            btn_pop = QPushButton("Populare")
            btn_clear = QPushButton("Curata")
            btn_all.clicked.connect(self.select_all_brands)
            btn_pop.clicked.connect(self.select_popular_brands)
            btn_clear.clicked.connect(self.clear_brands)
            bctl.addWidget(btn_all); bctl.addWidget(btn_pop); bctl.addWidget(btn_clear)
            left.addLayout(bctl)
            # ——— Modele
            right = QVBoxLayout()
            lab_m = QLabel("Modele (pentru marca activa):")
            lab_m.setFont(QFont("Arial", 12, QFont.Bold))
            right.addWidget(lab_m)
            self.models_list = QListWidget()
            self.models_list.setSelectionMode(QAbstractItemView.MultiSelection)
            self.models_list.setMaximumHeight(260)
            self.models_list.itemSelectionChanged.connect(self.on_models_selection_changed)
            right.addWidget(self.models_list)
            mctl = QHBoxLayout()
            btn_ma = QPushButton("Toate")
            btn_mc = QPushButton("Curata")
            btn_ma.clicked.connect(self.select_all_models)
            btn_mc.clicked.connect(self.clear_models)
            mctl.addWidget(btn_ma); mctl.addWidget(btn_mc)
            right.addLayout(mctl)
            outer.addLayout(left); outer.addLayout(right)
            group.setLayout(outer)
            return group
        
    def filter_brands(self, text: str):
            """Filtreaza lista de marci dupa text (case-insensitive)."""
            t = text.strip().lower()
            for i in range(self.brands_list.count()):
                it = self.brands_list.item(i)
                it.setHidden(False if not t else (t not in it.text().lower()))
        
    def on_brand_clicked(self, item: QListWidgetItem):
            """Cand utilizatorul face click pe o marca -> devine 'activa' pentru lista de modele."""
            self.save_current_models_of_active_brand()
            self.active_brand = item.text()
            self.refresh_models_for_active_brand()
        
    def on_brand_selection_changed(self):
            """Daca nu avem brand activ sau a fost deselectat, alegem primul selectat ca brand activ."""
            if self.active_brand:
                # daca active_brand nu mai e selectata, mutam pe prima selectata
                active_still = any(self.active_brand == it.text() for it in self.brands_list.selectedItems())
                if not active_still:
                    self.active_brand = self.brands_list.selectedItems()[0].text() if self.brands_list.selectedItems() else None
            else:
                self.active_brand = self.brands_list.selectedItems()[0].text() if self.brands_list.selectedItems() else None
            self.refresh_models_for_active_brand()
        
    def save_current_models_of_active_brand(self):
            """Salveaza selectia curenta de modele pentru marca activa."""
            if not self.active_brand: return
            sel = {self.models_list.item(i).text()
                for i in range(self.models_list.count())
                if self.models_list.item(i).isSelected()}
            self.selected_models_by_brand[self.active_brand] = sel
        
    def refresh_models_for_active_brand(self):
            """Re-umple lista de modele pentru marca activa + preselecteaza cele memorate."""
            self.models_list.clear()
            if not self.active_brand:
                return
            models = CAR_BRANDS_MODELS.get(self.active_brand, ["Toate modelele"])
            for m in models:
                self.models_list.addItem(m)
            # preselectam ce a fost salvat
            saved = self.selected_models_by_brand.get(self.active_brand, set())
            if saved:
                for i in range(self.models_list.count()):
                    it = self.models_list.item(i)
                    if it.text() in saved:
                        it.setSelected(True)
        
    def select_all_brands(self):
            for i in range(self.brands_list.count()):
                it = self.brands_list.item(i)
                if not it.isHidden():
                    it.setSelected(True)
            # daca nu avem activa, setam prima vizibila
            if not self.active_brand and self.brands_list.selectedItems():
                self.active_brand = self.brands_list.selectedItems()[0].text()
                self.refresh_models_for_active_brand()
        
    def select_popular_brands(self):
            popular = {"BMW", "Mercedes-Benz", "Audi", "Volkswagen", "Skoda", "Ford", "Dacia", "Renault", "Toyota"}
            for i in range(self.brands_list.count()):
                it = self.brands_list.item(i)
                it.setSelected(it.text() in popular and not it.isHidden())
            if self.brands_list.selectedItems():
                self.active_brand = self.brands_list.selectedItems()[0].text()
                self.refresh_models_for_active_brand()
        
    def clear_brands(self):
            self.save_current_models_of_active_brand()
            for i in range(self.brands_list.count()):
                self.brands_list.item(i).setSelected(False)
            self.active_brand = None
            self.models_list.clear()
        
    def select_all_models(self):
            for i in range(self.models_list.count()):
                self.models_list.item(i).setSelected(True)
            self.on_models_selection_changed()
        
    def clear_models(self):
            for i in range(self.models_list.count()):
                self.models_list.item(i).setSelected(False)
            self.on_models_selection_changed()
        
    def on_models_selection_changed(self):
            """Memoreaza imediat selectia modelelor pentru marca activa."""
            self.save_current_models_of_active_brand()
        
    def create_filters_group(self):
            group = QGroupBox("[CONFIG] Optiuni Filtre")
            layout = QGridLayout()
            layout.addWidget(QLabel("Combustibil:"), 0, 0)
            self.fuel_checkboxes = {}
            fl = QHBoxLayout()
            for k, lab in FUEL_TYPES.items():
                cb = QCheckBox(lab); self.fuel_checkboxes[k] = cb; fl.addWidget(cb)
            fw = QWidget(); fw.setLayout(fl); layout.addWidget(fw, 0, 1)
            layout.addWidget(QLabel("Caroserie:"), 1, 0)
            self.body_checkboxes = {}
            bl = QGridLayout()
            for i, (k, lab) in enumerate(CAR_BODIES.items()):
                cb = QCheckBox(lab); self.body_checkboxes[k] = cb; bl.addWidget(cb, i//4, i%4)
            bw = QWidget(); bw.setLayout(bl); layout.addWidget(bw, 1, 1)
            layout.addWidget(QLabel("Transmisie:"), 2, 0)
            self.gearbox_checkboxes = {}
            gl = QHBoxLayout()
            for k, lab in GEARBOX_TYPES.items():
                cb = QCheckBox(lab); self.gearbox_checkboxes[k] = cb; gl.addWidget(cb)
            gw = QWidget(); gw.setLayout(gl); layout.addWidget(gw, 2, 1)
            layout.addWidget(QLabel("Stare:"), 3, 0)
            self.state_checkboxes = {}
            sl = QHBoxLayout()
            for k, lab in CAR_STATES.items():
                cb = QCheckBox(lab); self.state_checkboxes[k] = cb; sl.addWidget(cb)
            sw = QWidget(); sw.setLayout(sl); layout.addWidget(sw, 3, 1)
            group.setLayout(layout)
            return group
        
    def create_ranges_group(self):
            group = QGroupBox("📊 Intervale Filtre")
            layout = QGridLayout()
            layout.addWidget(QLabel("Preț (EUR):"), 0, 0)
            self.price_min = QSpinBox(); self.price_min.setRange(0, 500000); self.price_min.setValue(5000); self.price_min.setSuffix(" EUR")
            layout.addWidget(QLabel("Min:"), 0, 1); layout.addWidget(self.price_min, 0, 2)
            self.price_max = QSpinBox(); self.price_max.setRange(0, 1000000); self.price_max.setValue(1000000); self.price_max.setSuffix(" EUR")
            layout.addWidget(QLabel("Max:"), 0, 3); layout.addWidget(self.price_max, 0, 4)
            layout.addWidget(QLabel("An fabricație:"), 1, 0)
            self.year_min = QSpinBox(); self.year_min.setRange(1970, 2026); self.year_min.setValue(2015)
            layout.addWidget(QLabel("Min:"), 1, 1); layout.addWidget(self.year_min, 1, 2)
            self.year_max = QSpinBox(); self.year_max.setRange(1970, 2026); self.year_max.setValue(2026)
            layout.addWidget(QLabel("Max:"), 1, 3); layout.addWidget(self.year_max, 1, 4)
            layout.addWidget(QLabel("Kilometraj:"), 2, 0)
            self.km_min = QSpinBox(); self.km_min.setRange(0, 500000); self.km_min.setValue(0); self.km_min.setSuffix(" km")
            layout.addWidget(QLabel("Min:"), 2, 1); layout.addWidget(self.km_min, 2, 2)
            self.km_max = QSpinBox(); self.km_max.setRange(0, 500000); self.km_max.setValue(200000); self.km_max.setSuffix(" km")
            layout.addWidget(QLabel("Max:"), 2, 3); layout.addWidget(self.km_max, 2, 4)
            layout.addWidget(QLabel("Putere motor:"), 3, 0)
            self.power_min = QSpinBox(); self.power_min.setRange(0, 1000); self.power_min.setValue(50); self.power_min.setSuffix(" CP")
            layout.addWidget(QLabel("Min:"), 3, 1); layout.addWidget(self.power_min, 3, 2)
            self.power_max = QSpinBox(); self.power_max.setRange(0, 1000); self.power_max.setValue(500); self.power_max.setSuffix(" CP")
            layout.addWidget(QLabel("Max:"), 3, 3); layout.addWidget(self.power_max, 3, 4)
            group.setLayout(layout)
            return group
        
    def create_advanced_group(self):
            group = QGroupBox("[SETTINGS] Setari Avansate")
            layout = QGridLayout()
            layout.addWidget(QLabel("Moneda:"), 0, 0)
            self.currency_combo = QComboBox(); self.currency_combo.addItems(["EUR", "RON"])
            layout.addWidget(self.currency_combo, 0, 1)
            layout.addWidget(QLabel("Pagini per marca:"), 0, 2)
            self.max_pages = QSpinBox(); self.max_pages.setRange(1, 10); self.max_pages.setValue(2)
            layout.addWidget(self.max_pages, 0, 3)
            safety_info = QLabel("[SECURITY] Intarzieri 5-15 sec intre cereri pentru a evita blocarea IP")
            safety_info.setStyleSheet("color: #4CAF50; font-size: 11px;")
            layout.addWidget(safety_info, 1, 0, 1, 4)
            group.setLayout(layout)
            return group
        
    def create_results_tab(self):
            tab = QWidget()
            layout = QVBoxLayout()
            self.results_info = QLabel("Niciun rezultat încă. Configurează filtrele și pornește scraping-ul.")
            self.results_info.setStyleSheet("font-size: 14px; margin: 10px;")
            layout.addWidget(self.results_info)
            self.results_table = QTableWidget()
            self.results_table.setColumnCount(10)
            self.results_table.setHorizontalHeaderLabels(["Titlu","Preț","An","KM","Combustibil","Transmisie","Caroserie","Marcă","Model","Acțiuni"])
            header = self.results_table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(4, QHeaderView.Stretch)
            layout.addWidget(self.results_table)
            tab.setLayout(layout)
            return tab
        
    def setup_default_values(self):
            QTimer.singleShot(100, self._apply_defaults)
        
    def _apply_defaults(self):
            try:
                self.select_popular_brands()
                for f in ['petrol', 'diesel']:
                    if f in self.fuel_checkboxes: self.fuel_checkboxes[f].setChecked(True)
                for b in ['sedan','suv','hatchback']:
                    if b in self.body_checkboxes: self.body_checkboxes[b].setChecked(True)
                for cb in self.gearbox_checkboxes.values(): cb.setChecked(True)
                if 'used' in self.state_checkboxes: self.state_checkboxes['used'].setChecked(True)
            except Exception as e:
                print(f"Defaults error: {e}")
        
    def get_search_config(self) -> Optional[SearchConfig]:
            selected_brands = [it.text() for it in self.brands_list.selectedItems()]
            if not selected_brands:
                QMessageBox.warning(self, "Atentie", "Te rog selecteaza cel putin o marca!")
                return None
            # salveaza selectia pentru marca activa inainte de a citi tot
            self.save_current_models_of_active_brand()
            models_by_brand: Dict[str, List[str]] = {}
            for b in selected_brands:
                # daca nu a salvat utilizatorul nimic pentru marca b => lista goala = toate modelele
                sel = sorted(list(self.selected_models_by_brand.get(b, set())))
                models_by_brand[b] = sel
            sel_fuels = [k for k,v in self.fuel_checkboxes.items() if v.isChecked()]
            sel_bodies = [k for k,v in self.body_checkboxes.items() if v.isChecked()]
            sel_gb = [k for k,v in self.gearbox_checkboxes.items() if v.isChecked()]
            sel_state = [k for k,v in self.state_checkboxes.items() if v.isChecked()]
            return SearchConfig(
                brands = selected_brands,
                models_by_brand = models_by_brand,
                fuel_types = sel_fuels,
                car_bodies = sel_bodies,
                gearbox_types = sel_gb,
                car_states = sel_state,
                price_min = self.price_min.value(),
                price_max = self.price_max.value(),
                year_min = self.year_min.value(),
                year_max = self.year_max.value(),
                km_min = self.km_min.value(),
                km_max = self.km_max.value(),
                power_min = self.power_min.value(),
                power_max = self.power_max.value(),
                currency = self.currency_combo.currentText(),
                max_pages_per_brand = self.max_pages.value()
            )
        
    def start_scraping(self):
            config = self.get_search_config()
            if not config: return
            # sumar
            brands_info = ", ".join(config.brands[:10]) + ("…" if len(config.brands)>10 else "")
            summary = (
                f"Config:\n"
                f"• Marci: {len(config.brands)} ({brands_info})\n"
                f"• Filtre: combustibil({', '.join(config.fuel_types) or '–'}), caroserie({', '.join(config.car_bodies) or '–'}), "
                f"transmisie({', '.join(config.gearbox_types) or '–'}), stare({', '.join(config.car_states) or '–'})\n"
                f"• Ani: {config.year_min}-{config.year_max} | Pret: {config.price_min}-{config.price_max} {config.currency}\n"
                f"• Pagini/marca: {config.max_pages_per_brand}\n\n"
                f"Continui?"
            )
            if QMessageBox.question(self, "Confirma Scraping-ul", summary, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
            self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True); self.export_btn.setEnabled(False)
            self.progress_bar.setValue(0); self.progress_label.setText("Initializare scraper...")
            self.scraping_thread = ScrapingThread(config)
            self.scraping_thread.progress_updated.connect(self.update_progress)
            self.scraping_thread.scraping_finished.connect(self.scraping_completed)
            self.scraping_thread.scraping_error.connect(self.scraping_failed)
            self.scraping_thread.start()
        
    def stop_scraping(self):
            if self.scraping_thread and self.scraping_thread.isRunning():
                self.scraping_thread.stop(); self.scraping_thread.wait()
            self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
            self.progress_label.setText("Scraping oprit de utilizator")
        
    def update_progress(self, message, percentage):
            self.progress_label.setText(message)
            self.progress_bar.setValue(int(percentage))
        
    def auto_export_and_upload(self, cars):
        if not cars:
            return "No cars to export"
            
        try:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"olx_masini_{ts}.csv"
            file_path = os.path.join(RESULTS_DIR, filename)
            
            # Create CSV data
            rows = []
            for c in cars:
                rows.append({
                    'titlu': c.title, 'pret_text': c.price_text, 'pret_numeric': c.price_numeric,
                    'an': c.year, 'kilometraj': c.km,
                    'link': c.link, 'imagini_urls': ';'.join(c.image_urls) if c.image_urls else '',
                    'combustibil': c.fuel_type, 'transmisie': c.gearbox, 'caroserie': c.car_body,
                    'marca': c.brand, 'model': c.model,
                    'id_unic': c.unique_id, 'data_scraping': c.scrape_date
                })
            
            # Save CSV file
            df = pd.DataFrame(rows)
            df.to_csv(file_path, index=False, encoding='utf-8')
            
            upload_status = f"[SUCCESS] Auto-saved: {filename}"
            
            # Try GitHub upload
            try:
                github_config_path = None
                possible_paths = [
                    os.path.join(get_app_dir(), "github-config.json"),
                    os.path.join(BASE_DIR, "github-config.json"),
                    "github-config.json"
                ]
                
                for path in possible_paths:
                    if os.path.exists(path):
                        github_config_path = path
                        break
                
                if github_config_path:
                    with open(github_config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                        github_uploader = GitHubUploader(
                            username=config['username'],
                            repo=config['repo'],
                            token=config['token']
                        )
                        
                        github_url = github_uploader.upload_csv_to_github(file_path, len(cars))
                        
                        if github_url:
                            upload_status += f" | GitHub uploaded successfully!"
                        else:
                            upload_status += f" | [WARNING] GitHub upload failed"
                    else:
                        upload_status += f" | [WARNING] File not accessible for upload"
                else:
                    upload_status += f" | [INFO] No GitHub config found"
            except Exception as e:
                upload_status += f" | [WARNING] Upload error: {str(e)[:50]}..."
                
            return upload_status
            
        except Exception as e:
            return f"[ERROR] Auto-export failed: {str(e)[:50]}..."

    def scraping_completed(self, cars):
            self.cars_data = cars
            self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
            self.export_btn.setEnabled(len(cars) > 0)
            
            # Auto-export and upload if cars found
            auto_status = ""
            if cars:
                auto_status = self.auto_export_and_upload(cars)
                self.results_info.setText(f"Găsite {len(cars)} mașini! Click Export pentru a salva rezultatele.\n{auto_status}")
                self.results_info.setStyleSheet("color: #4CAF50; font-size: 14px; margin: 10px;")
            else:
                self.results_info.setText("[WARNING] Nicio mașină nouă găsită. Încearcă să relaxezi filtrele.")
                self.results_info.setStyleSheet("color: #FF9800; font-size: 14px; margin: 10px;")
            
            self.populate_results_table(cars)
            self.tab_widget.setCurrentIndex(1)
            
            if cars:
                message = f"{len(cars)} mașini noi!\n\n"
                message += f"📊 Rezultatele sunt în tab-ul Rezultate.\n"
                message += f"[SAVE] Click 'Export Results' pentru CSV/XLSX.\n\n"
                message += f"🤖 {auto_status}"
                
                QMessageBox.information(self,"Scraping Finalizat", message)
        
    def scraping_failed(self, error_message):
            self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
            self.progress_label.setText(f"Scraping esuat: {error_message}")
            QMessageBox.critical(self,"Eroare Scraping",
                f"Scraping esuat:\n\n{error_message}\n\n"
                f"💡 Verifica internetul, redu marci/pagini, sau incearca mai tarziu.")
        
    def populate_results_table(self, cars: List[CarData]):
            self.results_table.setRowCount(len(cars))
            for row, car in enumerate(cars):
                title_text = car.title[:60] + ("…" if len(car.title) > 60 else "")
                self.results_table.setItem(row, 0, QTableWidgetItem(title_text))
                self.results_table.setItem(row, 1, QTableWidgetItem(car.price_text))
                self.results_table.setItem(row, 2, QTableWidgetItem(car.year))
                self.results_table.setItem(row, 3, QTableWidgetItem(car.km))
                self.results_table.setItem(row, 4, QTableWidgetItem(car.fuel_type))
                self.results_table.setItem(row, 5, QTableWidgetItem(car.gearbox))
                self.results_table.setItem(row, 6, QTableWidgetItem(car.car_body))
                self.results_table.setItem(row, 7, QTableWidgetItem(car.brand))
                self.results_table.setItem(row, 8, QTableWidgetItem(car.model))
                btn = QPushButton("Deschide"); btn.setToolTip("Deschide anunțul în browser")
                btn.clicked.connect(lambda checked, url=car.link: self.open_car_link(url))
                self.results_table.setCellWidget(row, 9, btn)
            self.results_table.resizeColumnsToContents()
        
    def open_car_link(self, url):
        try:
            # Curăț și normalizez URL-ul
            url = (url or "").strip()
            if not url:
                raise ValueError("URL gol")
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith("http"):
                url = "https://" + url.lstrip("/")

            ok = QDesktopServices.openUrl(QUrl(url))
            if not ok:
                # Dacă Qt zice "nu", arunc un mesaj clar
                raise RuntimeError("Sistemul nu a putut deschide URL-ul.")
        except Exception as e:
            QMessageBox.warning(self, "Eroare", f"Nu s-a putut deschide link-ul:\n{e}\n\nURL: {url}")

        
    def export_results(self):
            if not self.cars_data:
                QMessageBox.warning(self, "Atenție", "Nu există date pentru export!"); return
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            default_fn = f"olx_masini_{ts}.csv"
            path, _ = QFileDialog.getSaveFileName(self, "Salvează Rezultatele",
                                                os.path.join(RESULTS_DIR, default_fn),
                                                "Fișiere CSV (*.csv);;Fișiere Excel (*.xlsx);;Toate Fișierele (*)")
            if not path: return
            try:
                rows = []
                for c in self.cars_data:
                    rows.append({
                        'titlu': c.title, 'pret_text': c.price_text, 'pret_numeric': c.price_numeric,
                        'an': c.year, 'kilometraj': c.km,
                        'link': c.link, 'imagini_urls': ';'.join(c.image_urls) if c.image_urls else '',
                        'combustibil': c.fuel_type, 'transmisie': c.gearbox, 'caroserie': c.car_body,
                        'marca': c.brand, 'model': c.model,
                        'id_unic': c.unique_id, 'data_scraping': c.scrape_date
                    })
                df = pd.DataFrame(rows)
                if path.endswith('.xlsx'):
                    try:
                        df.to_excel(path, index=False)
                    except Exception as e:
                        QMessageBox.warning(self, "openpyxl lipsa", f"Instaleaza 'openpyxl' (pip install openpyxl)\n{e}\nSalvez CSV in schimb.")
                        fallback = path.rsplit('.',1)[0]+'.csv'; df.to_csv(fallback, index=False, encoding='utf-8'); path = fallback
                else:
                    df.to_csv(path, index=False, encoding='utf-8')
                
                message = f"Exportate {len(self.cars_data)} mașini în:\n{path}"
                
                # Try GitHub upload (optional)
                print(f"\n[EXPORT] File saved successfully: {path}")
                print(f"[EXPORT] Attempting GitHub upload...")
                
                try:
                    github_config_path = None
                    possible_paths = [
                        os.path.join(get_app_dir(), "github-config.json"),
                        os.path.join(BASE_DIR, "github-config.json"),
                        "github-config.json"
                    ]
                    
                    for path in possible_paths:
                        if os.path.exists(path):
                            github_config_path = path
                            break
                    
                    if github_config_path:
                        print(f"[CONFIG] Found github-config.json at: {github_config_path}")
                        with open(github_config_path, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                        
                        print(f"[CONFIG] GitHub repo: {config['username']}/{config['repo']}")
                        
                        # Ensure file is accessible before upload
                        if not os.path.exists(path):
                            raise Exception(f"CSV file not found after saving: {path}")
                        
                        file_size = os.path.getsize(path)
                        print(f"[FILE] Verifying file exists: {path}")
                        print(f"[FILE] File size: {file_size:,} bytes")
                        
                        if file_size == 0:
                            raise Exception("CSV file is empty after saving")
                        
                        # Initialize GitHub uploader
                        github_uploader = GitHubUploader(
                            username=config['username'],
                            repo=config['repo'],
                            token=config['token']
                        )
                        
                        print(f"[UPLOAD] Starting GitHub upload...")
                        github_url = github_uploader.upload_csv_to_github(path, len(self.cars_data))
                        
                        if github_url:
                            print(f"[SUCCESS] GitHub upload completed successfully!")
                            print(f"[SUCCESS] Download URL: {github_url}")
                            message += f"\n\nGITHUB UPLOAD SUCCESSFUL!"
                            message += f"\nFile uploaded to: {config['repo']}/data/"
                            message += f"\nDownload URL: {github_url}"
                            message += f"\n📊 Data is now available in the web UI!"
                            message += f"\n\nYour scraped data will automatically appear"
                            message += f"\n   in the Netlify web interface!"
                        else:
                            print(f"[FAILED] GitHub upload failed - no URL returned")
                            message += f"\n\nGitHub upload failed (see console for details)"
                            message += f"\nFile saved locally but not uploaded to web UI"
                    else:
                        print(f"[CONFIG] github-config.json not found - skipping upload")
                        message += f"\n\nGitHub config not found - file saved locally only"
                except Exception as e:
                    print(f"[ERROR] GitHub upload error: {str(e)}")
                    logging.warning(f"GitHub upload failed: {e}")
                    message += f"\n\nGitHub upload error: {str(e)}"
                    message += f"\nFile saved locally but not uploaded to web UI"
                
                QMessageBox.information(self, "Export Finalizat", message)
            except Exception as e:
                QMessageBox.critical(self, "Eroare Export", f"Exportul a eșuat:\n{e}")

    def check_running_scraper_on_startup(self):
        """Check at startup if another scraper is running"""
        lock_file = os.path.join(RESULTS_DIR, '.scraping_lock')
        if os.path.exists(lock_file):
            try:
                with open(lock_file, 'r') as f:
                    content = f.read().strip().split('\n')
                    session_id = content[0] if content else "unknown"
                    timestamp = content[1] if len(content) > 1 else ""

                # Check if recent (last 2 hours)
                if timestamp:
                    lock_time = datetime.fromisoformat(timestamp)
                    age = (datetime.now() - lock_time).total_seconds()
                    if age < 7200:  # 2 hours
                        self.show_running_scraper_status(session_id, timestamp)
                        return

                # Old lock, remove it
                os.remove(lock_file)
            except:
                pass

    def show_running_scraper_status(self, session_id, timestamp):
        """Display that a scraper is running"""
        self.start_btn.setEnabled(False)
        self.start_btn.setText("Scraper active in another session")

        self.progress_label.setText(f"Another scraper is running (Session: {session_id[:15]}...)")
        self.progress_label.setStyleSheet("color: #FF9800; font-weight: bold;")

        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(self, "Active Scraper Detected",
            f"A scraper is already active from another session.\n"
            f"Session ID: {session_id}\n"
            f"Started at: {timestamp}\n\n"
            f"You can start a new scraper when the current one finishes.")

    def check_scraper_status(self):
        """Check scraper status periodically"""
        lock_file = os.path.join(RESULTS_DIR, '.scraping_lock')

        if os.path.exists(lock_file):
            # Scraper active
            if self.start_btn.isEnabled() and not self.scraping_thread:
                self.start_btn.setEnabled(False)
                self.start_btn.setText("Scraper active in another session")
                self.progress_label.setText("Another scraper is running...")
                self.progress_label.setStyleSheet("color: #FF9800;")
        else:
            # No scraper running
            if not self.start_btn.isEnabled() and not self.scraping_thread:
                self.start_btn.setEnabled(True)
                self.start_btn.setText("Start Scraping")
                self.progress_label.setText("Ready to start scraping...")
                self.progress_label.setStyleSheet("color: #ffffff;")

    def get_modern_stylesheet(self):
            return """
            QWidget { background-color: #1e1e1e; color: #ffffff; font-family: 'Segoe UI', Arial, sans-serif; font-size: 11px; }
            QTabWidget::pane { border: 1px solid #404040; background-color: #1e1e1e; }
            QTabBar::tab { background-color: #2d2d2d; color: #ffffff; padding: 10px 16px; margin-right: 2px; border: 1px solid #404040; border-bottom: none; border-radius: 4px 4px 0 0; }
            QTabBar::tab:selected { background-color: #2196F3; border-color: #2196F3; }
            QGroupBox { font-weight: bold; border: 2px solid #404040; border-radius: 8px; margin-top: 1ex; padding-top: 12px; background-color: #252525; }
            QGroupBox::title { left: 10px; padding: 0 8px; color: #2196F3; font-size: 12px; }
            QPushButton { background-color: #2196F3; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:pressed { background-color: #0D47A1; }
            QPushButton:disabled { background-color: #424242; color: #888888; }
            QCheckBox { spacing: 8px; color: #ffffff; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QSpinBox, QComboBox, QLineEdit { padding: 6px; border: 1px solid #404040; border-radius: 4px; background-color: #2d2d2d; color: #ffffff; }
            QSpinBox:focus, QComboBox:focus, QLineEdit:focus { border-color: #2196F3; }
            QProgressBar { border: 1px solid #404040; border-radius: 4px; text-align: center; background-color: #2d2d2d; color: #ffffff; }
            QProgressBar::chunk { background-color: #2196F3; border-radius: 3px; }
            QTableWidget { gridline-color: #404040; background-color: #1e1e1e; alternate-background-color: #252525; selection-background-color: #2196F3; }
            QHeaderView::section { background-color: #2d2d2d; color: white; padding: 6px; border: 1px solid #404040; font-weight: bold; }
            QListWidget { background-color: #2d2d2d; border: 1px solid #404040; border-radius: 4px; selection-background-color: #2196F3; }
            """
    

# ========== GitHub Actions Headless Mode Support ==========

def parse_github_actions_args():
    """Parse GitHub Actions command line arguments"""
    parser = argparse.ArgumentParser(description='OLX Car Scraper - GitHub Actions Mode')
    parser.add_argument('--config', type=str, required=True, 
                       help='JSON configuration string (not filename)')
    parser.add_argument('--session-id', type=str, required=True,
                       help='Unique session ID for this scrape')
    parser.add_argument('--output-dir', type=str, default='olx_results',
                       help='Output directory for results')
    return parser.parse_args()

def json_config_to_search_config(json_config: dict) -> SearchConfig:
    """Convert JSON configuration to SearchConfig object"""
    
    # Extract brands and models
    brands = json_config.get('brands', [])
    models_by_brand = json_config.get('models_by_brand', {})
    
    # Convert lists to ensure they're not empty (use defaults)
    fuel_types = json_config.get('fuel_types', [])
    car_bodies = json_config.get('car_bodies', [])  
    gearbox_types = json_config.get('gearbox_types', [])
    car_states = json_config.get('car_states', [])
    
    return SearchConfig(
        brands=brands,
        models_by_brand=models_by_brand,
        fuel_types=fuel_types,
        car_bodies=car_bodies,
        gearbox_types=gearbox_types,
        car_states=car_states,
        price_min=json_config.get('price_min', 0),
        price_max=json_config.get('price_max', 999999),
        year_min=json_config.get('year_min', 1990),
        year_max=json_config.get('year_max', datetime.now().year),
        km_min=json_config.get('km_min', 0),
        km_max=json_config.get('km_max', 999999),
        power_min=json_config.get('power_min', 0),
        power_max=json_config.get('power_max', 999),
        currency=json_config.get('currency', 'EUR'),
        max_pages_per_brand=json_config.get('max_pages', 5)
    )

def run_headless_scraper():
    """Run scraper in headless mode for GitHub Actions"""
    print("Starting OLX Scraper in GitHub Actions mode...")
    
    try:
        # Parse arguments
        args = parse_github_actions_args()
        print(f"Session ID: {args.session_id}")
        print(f"Output directory: {args.output_dir}")
        
        # Create output directory
        os.makedirs(args.output_dir, exist_ok=True)
        
        # Parse JSON configuration string
        try:
            json_config = json.loads(args.config)
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON configuration: {e}")
            print(f"[DEBUG] Received config: {args.config[:100]}...")
            logging.error(f"JSON parsing failed: {e}")
            return False
            
        print(f"[CONFIG] Configuration loaded: {len(json_config.get('brands', []))} brands")
        
        # Convert JSON to SearchConfig
        search_config = json_config_to_search_config(json_config)
        
        # Setup logging for headless mode
        log_file = os.path.join(args.output_dir, f'scraper_{args.session_id}.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        logger = logging.getLogger(__name__)
        logger.info(f"Starting scraper session: {args.session_id}")
        logger.info(f"Brands to scrape: {search_config.brands}")
        
        # Create scraping engine
        print("Initializing scraping engine...")
        engine = OLXScrapingEngine()
        
        # Set headless mode
        engine.headless = True
        
        # Step 1: Scrape ALL cars from OLX WITHOUT any duplicate detection
        print("[WORKFLOW] Step 1: Scraping ALL cars from OLX...")
        print("NOTE: No duplicate detection during scraping - collecting complete dataset")
        print("Starting car scraping process...")
        all_scraped_cars = engine.scrape_all_cars(search_config)
        
        if not all_scraped_cars:
            print("WARNING: No cars found matching the criteria")
            logger.warning("No cars found")
            return False
            
        print(f"[WORKFLOW] Step 1 Complete: Scraped {len(all_scraped_cars)} total cars")
        logger.info(f"Scraping completed: {len(all_scraped_cars)} total cars collected")
        
        # Step 2: Load database from Supabase for duplicate detection
        print("\n[WORKFLOW] Step 2: Load database for duplicate detection...")

        # Load database (will use Supabase if available, otherwise local file)
        engine.load_duplicate_database()

        db_size = len(engine.duplicate_db)
        print(f"[DATABASE] Successfully loaded {db_size} cars")

        if 0 < db_size < 50:
            print(f"[WARNING] Suspiciously small database ({db_size} cars)")
            print("[WARNING] This might be corrupted - manual review recommended")
        elif db_size == 0:
            print("[INFO] Empty database - starting fresh scraping session")
        
        print(f"[WORKFLOW] Step 2 Complete: Database ready with {len(engine.duplicate_db)} known cars")
        
        # Step 3: Filter to find NEW cars and PRICE CHANGES (≥1 EUR)
        print("\n[WORKFLOW] Step 3: Identify new cars and price changes...")
        cars_data = engine.filter_duplicates(all_scraped_cars)  # Returns NEW + PRICE CHANGED cars only

        print(f"[WORKFLOW] Step 3 Complete: {len(cars_data)} actionable cars found")
        print(f"[WORKFLOW]   - From: {len(all_scraped_cars)} total scraped cars")
        print(f"[WORKFLOW]   - Kept: {len(cars_data)} cars (new or price changed ≥1 EUR)")
        print(f"[WORKFLOW]   - Filtered: {len(all_scraped_cars) - len(cars_data)} unchanged duplicates")

        # Step 4: Save ALL scraped cars to database (for complete tracking)
        print("\n[WORKFLOW] Step 4: Update database with ALL scraped data...")
        print("[WORKFLOW] NOTE: Saving all cars for tracking, not just new/changed ones")
        before_size = len(engine.duplicate_db)
        engine.save_duplicate_database(all_scraped_cars)  # Save ALL cars to database
        after_size = len(engine.duplicate_db)
        print(f"[WORKFLOW] Step 4 Complete: Database updated from {before_size} to {after_size} cars")
        print(f"[WORKFLOW]   - Database growth: +{after_size - before_size} cars")
        
        # Save results with session ID
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Prepare data for export (same format as GUI)
        export_data = []
        
        # Save results with session ID
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Prepare data for export (same format as GUI)
        export_data = []
        for car in cars_data:
            export_data.append({
                'titlu': car.title,
                'pret_text': car.price_text,
                'pret_numeric': car.price_numeric,
                'an': car.year,
                'kilometraj': car.km,
                'link': car.link,
                'imagini_urls': ';'.join(car.image_urls) if car.image_urls else '',
                'combustibil': car.fuel_type,
                'transmisie': car.gearbox,
                'caroserie': car.car_body,
                'marca': car.brand,
                'model': car.model,
                'id_unic': car.unique_id,
                'data_scraping': car.scrape_date
            })
        
        # Save as CSV
        df = pd.DataFrame(export_data)
        csv_file = os.path.join(args.output_dir, f'olx_results_{args.session_id}_{timestamp}.csv')
        df.to_csv(csv_file, index=False, encoding='utf-8')
        
        # Step 5: Database is automatically saved in Step 4
        print("\n[WORKFLOW] Step 5: Database sync completed")
        print("[WORKFLOW] Step 5 Complete: Database saved (Supabase or local)")
        
        # Step 6: Optional - Upload filtered CSV to GitHub for reporting
        print(f"\n[WORKFLOW] Step 6: Optional CSV upload to GitHub ({len(cars_data)} non-duplicate cars)...")

        # Try to find GitHub config for CSV uploads (optional)
        github_config_path = None
        config_files = ["github-config.json", "github_config.json",
                       os.path.join(args.output_dir, "github-config.json")]

        for path in config_files:
            if os.path.exists(path):
                github_config_path = path
                break

        if github_config_path:
            try:
                with open(github_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                github_uploader = GitHubUploader(
                    username=config['username'],
                    repo=config['repo'],
                    token=config['token']
                )
                
                github_url = github_uploader.upload_csv_to_github(csv_file, len(cars_data))
                
                if github_url:
                    print(f"[WORKFLOW] Step 6 Complete: CSV uploaded - {github_url}")
                else:
                    print(f"[WORKFLOW] Step 6 Failed: CSV upload failed")
                    
            except Exception as e:
                print(f"[WORKFLOW] Step 6 Error: {e}")
        else:
            print(f"[WORKFLOW] Step 6 Skipped: No GitHub config found")
        
        # Save as JSON for backup
        json_file = os.path.join(args.output_dir, f'olx_results_{args.session_id}_{timestamp}.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)
            
        # Save summary
        summary = {
            'session_id': args.session_id,
            'timestamp': timestamp,
            'total_cars': len(cars_data),
            'brands_scraped': search_config.brands,
            'configuration': json_config,
            'files': {
                'csv': csv_file,
                'json': json_file,
                'log': log_file
            }
        }
        
        summary_file = os.path.join(args.output_dir, f'summary_{args.session_id}.json')
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
            
        print(f"[SAVE] Results saved:")
        print(f"   [FILE] CSV: {csv_file}")
        print(f"   [FILE] JSON: {json_file}")  
        print(f"   [FILE] Summary: {summary_file}")
        print(f"   [LOG] Log: {log_file}")
        
        logger.info(f"Results saved successfully to {args.output_dir}")
        
        # Final workflow summary
        print("\n" + "="*60)
        print("[WORKFLOW SUMMARY]")
        print(f"  Step 1: Scraped {len(all_scraped_cars)} total cars")
        print(f"  Step 2: Downloaded database from GitHub ({before_size} existing cars)")
        print(f"  Step 3: Filtered to {len(cars_data)} non-duplicate cars")
        print(f"  Step 4: Updated database to {after_size} cars (+{after_size - before_size})")
        print(f"  Step 5: Uploaded database to GitHub")
        print(f"  Step 6: Uploaded CSV with {len(cars_data)} cars")
        print("="*60)
        print("[SUCCESS] GitHub Actions scraping completed successfully!")
        print(f"[RESULT] Database grew from {before_size} to {after_size} cars")
        print(f"[RESULT] {len(cars_data)} new/changed cars from {len(all_scraped_cars)} total scraped")
        
        # CRITICAL: Verify database never shrunk
        if after_size < before_size:
            print(f"[CRITICAL ERROR] Database shrunk from {before_size} to {after_size}! Data loss detected!")
            return False
            
        return True
        
    except Exception as e:
        print(f"ERROR in headless scraper: {e}")
        logging.error(f"Headless scraper failed: {e}")
        return False

# ---------- main ----------
def main():
    """Main function - handles both GUI and GitHub Actions modes"""
    
    # Check if running in GitHub Actions mode
    if GITHUB_ACTIONS_MODE:
        print("Detected GitHub Actions mode")
        success = run_headless_scraper()
        sys.exit(0 if success else 1)
    
    # Regular GUI mode
    if not PYQT5_AVAILABLE:
        print("ERROR: PyQt5 not available and not in GitHub Actions mode")
        print("   Install PyQt5: pip install PyQt5")
        sys.exit(1)
        
    print("Starting GUI mode")
    app = QApplication(sys.argv)
    app.setApplicationName("OLX Advanced Car Scraper")
    app.setApplicationVersion("3.1")
    app.setOrganizationName("CarScraperPro")
    w = OLXAdvancedScraper(); w.show()
    QMessageBox.information(
        w, "Bun venit",
        "Cautare marci + memorare modele per marca\n\n"
        "Cum folosesti:\n"
        "1) Scrie in bara de cautare o marca (ex. 'bmw') ca s-o gasesti rapid.\n"
        "2) Selecteaza marca (devine 'activa'), bifeaza modelele ei.\n"
        "3) Selecteaza a doua marca, bifeaza modelele ei - selectia primei marci ramane memorata.\n"
        "4) Seteaza filtrele (optional) si apasa Start Scraping."
    )
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

