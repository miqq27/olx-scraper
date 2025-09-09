#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# DEV VERSION - Created for job queue integration

"""
OLX Advanced Car Scraper - Mărci + Modele + Căutare branduri
- Dropdown mărci cu SEARCH
- Modele per marcă, cu memorarea selecției
- Multi-brand scraping + filtrare după modele selectate
- Export CSV/XLSX
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
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime

# ====== GUI ======
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
except ImportError as e:
    print(f"PyQt5 import error: {e}\n   Instalează: pip install PyQt5")
    sys.exit(1)

# ====== Selenium ======
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    from fake_useragent import UserAgent
except ImportError as e:
    print(f"Selenium import error: {e}\n   Instalează: pip install selenium webdriver-manager fake-useragent")
    sys.exit(1)

# ====== BeautifulSoup ======
try:
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"BeautifulSoup import error: {e}\n   Instalează: pip install beautifulsoup4")
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


# ---------- Mărci + Modele (INTEGRATE) ----------
# ⚠️ Dacă vrei lista ta completă exact cum ai pus-o, înlocuiește conținutul de mai jos.
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

# Mapări slug pentru OLX
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
FUEL_TYPES = {'petrol': 'Benzină','diesel': 'Diesel','lpg': 'GPL','hybrid': 'Hibrid','electric': 'Electric'}
CAR_BODIES = {'sedan':'Berlina','suv':'SUV','hatchback':'Hatchback','estate-car':'Break','coupe':'Coupe','cabriolet':'Cabrio','pickup':'Pickup','off-road-vehicle':'Off-road','minibus':'Minibus','mpv':'MPV'}
GEARBOX_TYPES = {'manual':'Manuală','automatic':'Automată'}
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

def test_github_upload():
    """Test GitHub upload functionality with a dummy CSV file"""
    print("\n[TEST] TESTING GITHUB UPLOAD FUNCTIONALITY")
    print("="*50)
    
    try:
        # Check if config file exists (try both app directory and data directory)
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
                
        if not github_config_path:
            print("[ERROR] github-config.json not found!")
            return False
            
        # Load config
        with open(github_config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print("[OK] Configuration loaded successfully")
        print(f"[INFO] Username: {config['username']}")
        print(f"[INFO] Repository: {config['repo']}")
        print(f"[INFO] Token: {config['token'][:8]}...{config['token'][-4:]}")
        
        # Create test data
        test_data = [
            {
                'titlu': 'Test Car 1',
                'pret_text': '€15,000',
                'pret_numeric': 15000,
                'an': 2020,
                'kilometraj': '50,000',
                'locatie': 'Bucharest',
                'link': 'https://test.example.com',
                'imagini_urls': 'https://img1.example.com;https://img2.example.com',
                'combustibil': 'Benzina',
                'transmisie': 'Manuala',
                'caroserie': 'Berlina',
                'marca': 'Test Brand',
                'model': 'Test Model',
                'id_unic': 'TEST001',
                'data_scraping': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            {
                'titlu': 'Test Car 2', 
                'pret_text': '€25,000',
                'pret_numeric': 25000,
                'an': 2021,
                'kilometraj': '30,000',
                'locatie': 'Cluj-Napoca',
                'link': 'https://test2.example.com',
                'imagini_urls': 'https://img3.example.com',
                'combustibil': 'Diesel',
                'transmisie': 'Automata',
                'caroserie': 'SUV',
                'marca': 'Another Brand',
                'model': 'Another Model',
                'id_unic': 'TEST002',
                'data_scraping': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        ]
        
        # Create temporary CSV file
        import tempfile
        df = pd.DataFrame(test_data)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', encoding='utf-8') as temp_file:
            df.to_csv(temp_file.name, index=False, encoding='utf-8')
            temp_csv_path = temp_file.name
            
        print(f"[INFO] Created test CSV: {temp_csv_path}")
        print(f"[INFO] Test data rows: {len(test_data)}")
        
        # Initialize GitHub uploader
        github_uploader = GitHubUploader(
            username=config['username'],
            repo=config['repo'],
            token=config['token']
        )
        
        # Perform upload
        print("\n[START] Starting test upload...")
        github_url = github_uploader.upload_csv_to_github(temp_csv_path, len(test_data))
        
        # Clean up
        try:
            os.unlink(temp_csv_path)
            print(f"[CLEANUP] Cleaned up temp file: {temp_csv_path}")
        except:
            pass
            
        if github_url:
            print(f"\n[SUCCESS] TEST SUCCESSFUL!")
            print(f"[OK] File uploaded successfully")
            print(f"[URL] {github_url}")
            print(f"[WEB] The file should now be visible in the web UI")
            return True
        else:
            print(f"\n[FAILED] TEST FAILED!")
            print(f"Upload returned None - check logs above for details")
            return False
            
    except Exception as e:
        print(f"[EXCEPTION] TEST EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False

# ---------- Modele de date ----------
@dataclass
class SearchConfig:
    brands: List[str]
    models_by_brand: Dict[str, List[str]]  # modelele selectate per marcă (gol = toate)
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
    location: str
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
        olx_id_match = re.search(r'ID([a-zA-Z0-9]+)\.html', link)
        if olx_id_match:
            return f"olx_{olx_id_match.group(1)}"
        hash_obj = hashlib.md5(f"{link}_{title}".encode('utf-8'))
        return f"hash_{hash_obj.hexdigest()[:12]}"
    except:
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
            # Locație
            for sel in ['a[data-cy="listing-ad-location"]', '.css-1f924qg']:
                el = soup.select_one(sel)
                if el:
                    data['location'] = el.get_text(strip=True); break
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
            data.setdefault('location', 'N/A')
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
        self.load_duplicate_database()
        self.should_stop = lambda: False
        
    def load_duplicate_database(self):
        db_file = os.path.join(RESULTS_DIR, 'cars_database.json')
        try:
            if os.path.exists(db_file):
                with open(db_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.duplicate_db = data.get('cars', {})
                    self.logger.info(f"📚 Loaded {len(self.duplicate_db)} known cars")
        except Exception as e:
            self.logger.error(f"DB load fail: {e}")
            self.duplicate_db = {}
    
    def save_duplicate_database(self, new_cars: List[CarData]):
        db_file = os.path.join(RESULTS_DIR, 'cars_database.json')
        try:
            for car in new_cars:
                prev = self.duplicate_db.get(car.unique_id, {})
                first_seen = prev.get('first_seen', car.scrape_date)
                self.duplicate_db[car.unique_id] = {
                    'title': car.title,
                    'link': car.link,
                    'first_seen': first_seen,
                    'last_seen': car.scrape_date,
                    'last_price': float(car.price_numeric),
                    'last_price_text': car.price_text,
                }
            with open(db_file, 'w', encoding='utf-8') as f:
                json.dump({'cars': self.duplicate_db}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"DB save fail: {e}")

    
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
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
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
            # 🔧 Asteapta sa apara orice card de anunt (max 10s)
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

                # Duplicates
                new_page = [c for c in page_cars if not self.is_duplicate(
                        c.get('link',''), c.get('title',''), c.get('price_numeric'))]

                # Filtru MODELE pt. marca curentă (client-side)
                wanted_models = config.models_by_brand.get(brand, [])
                if wanted_models and "Toate modelele" not in wanted_models:
                    filtered = []
                    for c in new_page:
                        _, mdl = self.extract_brand_and_model_from_title(c.get('title',''))
                        if (mdl in wanted_models) or ("Altul" in wanted_models and mdl == "Unknown"):
                            filtered.append(c)
                    new_page = filtered
                all_cars.extend(new_page)
                self.logger.info(f"{brand} p{page}: {len(new_page)}/{len(page_cars)} new (kept after filters)")
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
                    location = det.get('location','N/A'),
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
                self.logger.warning("⚠️ No cars with current filters")
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
    
    def cleanup_driver(self):
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("🔌 Chrome driver closed")
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
        self.setWindowTitle("🚗 OLX Advanced Car Scraper - Mărci + Modele")
        self.setGeometry(80, 80, 1500, 980)
        self.cars_data = []
        self.scraping_thread = None
        # memory: modele selectate per marcă
        self.selected_models_by_brand: Dict[str, Set[str]] = {}
        self.active_brand: Optional[str] = None 
        self.saved_searches: Dict[str, dict] = {}
        self.setup_ui()
        self.setup_default_values()
        self.load_saved_searches()
        self.refresh_saved_search_dropdown()
    
    # ===== UI =====
    def setup_ui(self):
        main_layout = QVBoxLayout()
        header = QLabel("🚗 OLX Advanced Car Scraper - Mărci + Modele")
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
        self.stop_btn = QPushButton("⏹️ Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_scraping)
        self.export_btn = QPushButton("💾 Export Results")
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
        group = QGroupBox("💾 Căutări salvate")
        layout = QGridLayout()

        # Dropdown cu căutări salvate
        layout.addWidget(QLabel("Selectează:"), 0, 0)
        self.saved_searches_combo = QComboBox()
        self.saved_searches_combo.setMinimumWidth(260)
        layout.addWidget(self.saved_searches_combo, 0, 1, 1, 3)

        # Nume pentru salvare
        layout.addWidget(QLabel("Nume căutare:"), 1, 0)
        self.saved_search_name = QLineEdit()
        self.saved_search_name.setPlaceholderText("ex: BMW + A4 + sub 10.000€")
        layout.addWidget(self.saved_search_name, 1, 1, 1, 3)

        # Butoane
        self.btn_save_search = QPushButton("💾 Salvează")
        self.btn_load_search = QPushButton("📥 Încarcă")
        self.btn_delete_search = QPushButton("🗑️ Șterge")
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
        """Încarcă dict {name: payload} din fișier."""
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
            QMessageBox.warning(self, "Căutări salvate", f"Nu s-au putut încărca căutările salvate:\n{e}")

    def persist_saved_searches(self):
        """Scrie dict {name: payload} în fișier."""
        try:
            with open(SAVED_SEARCHES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.saved_searches, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Căutări salvate", f"Nu s-a putut salva fișierul:\n{e}")

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
        # 1) mărci selectate (nume afișate în listă)
        selected_brands = [it.text() for it in self.brands_list.selectedItems()]

        # 2) salvează modelele curente pt marca activă, apoi ia dict-ul complet
        self.save_current_models_of_active_brand()
        models_by_brand = {b: sorted(list(v)) for b, v in self.selected_models_by_brand.items() if v}

        # 3) restul filtrelor
        sel_fuels = [k for k,v in self.fuel_checkboxes.items() if v.isChecked()]
        sel_bodies = [k for k,v in self.body_checkboxes.items() if v.isChecked()]
        sel_gb    = [k for k,v in self.gearbox_checkboxes.items() if v.isChecked()]
        sel_state = [k for k,v in self.state_checkboxes.items() if v.isChecked()]

        payload = {
            "brands": selected_brands,
            "models_by_brand": models_by_brand,  # dacă lipsește o marcă => toate modelele
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
        """Aplică payload în UI (mărci, modele, filtre, intervale)."""
        if not payload:
            return

        # reset brands & models
        for i in range(self.brands_list.count()):
            self.brands_list.item(i).setSelected(False)
        self.active_brand = None
        self.models_list.clear()
        self.selected_models_by_brand.clear()

        # selectează mărcile
        wanted_brands = set(payload.get("brands", []))
        first_selected_text = None
        for i in range(self.brands_list.count()):
            it = self.brands_list.item(i)
            if it.text() in wanted_brands:
                it.setSelected(True)
                if first_selected_text is None:
                    first_selected_text = it.text()

        # setează marca activă și reafișează modelele
        self.active_brand = first_selected_text
        self.refresh_models_for_active_brand()

        # modele per marcă
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
            QMessageBox.warning(self, "Căutare salvată", "Te rog introdu un nume pentru căutare.")
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
        QMessageBox.information(self, "Căutare salvată", f"'{name}' a fost salvată.")

    def on_load_search_click(self):
        name = self.saved_searches_combo.currentText().strip()
        if not name:
            QMessageBox.information(self, "Căutări salvate", "Nu ai selectat nicio căutare.")
            return
        payload = self.saved_searches.get(name, {})
        if not payload:
            QMessageBox.warning(self, "Căutări salvate", f"Căutarea '{name}' nu are conținut.")
            return
        self.apply_search_payload(payload)
        self.saved_search_name.setText(name)
        QMessageBox.information(self, "Căutări salvate", f"📥 S-a încărcat '{name}' în UI.")

    def on_delete_search_click(self):
        name = self.saved_searches_combo.currentText().strip()
        if not name:
            QMessageBox.information(self, "Căutări salvate", "Nu ai selectat nicio căutare pentru șters.")
            return
        if QMessageBox.question(self, "Confirmare ștergere",
                                f"Sigur vrei să ștergi '{name}'?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.saved_searches.pop(name, None)
            self.persist_saved_searches()
            self.refresh_saved_search_dropdown()
            self.saved_search_name.clear()
            QMessageBox.information(self, "Căutări salvate", f"🗑️ '{name}' a fost ștearsă.")
        except Exception as e:
            QMessageBox.warning(self, "Căutări salvate", f"Eroare la ștergere:\n{e}")
    

        
    def create_brands_models_group(self):
            group = QGroupBox("🏷️ Selectare Mărci și Modele")
            outer = QHBoxLayout()
            # ——— Mărci
            left = QVBoxLayout()
            lab_b = QLabel("Mărci:")
            lab_b.setFont(QFont("Arial", 12, QFont.Bold))
            left.addWidget(lab_b)
            # Căutare mărci
            self.brand_search = QLineEdit()
            self.brand_search.setPlaceholderText("🔎 Caută marcă (ex: bmw)")
            self.brand_search.textChanged.connect(self.filter_brands)
            left.addWidget(self.brand_search)
            # Listă mărci
            self.brands_list = QListWidget()
            self.brands_list.setSelectionMode(QAbstractItemView.MultiSelection)
            self.brands_list.setMaximumHeight(260)
            # populate
            for brand in sorted(CAR_BRANDS_MODELS.keys()):
                self.brands_list.addItem(brand)
            # legături: când dai click pe o marcă -> devine activă (schimbăm lista de modele)
            self.brands_list.itemClicked.connect(self.on_brand_clicked)
            self.brands_list.itemSelectionChanged.connect(self.on_brand_selection_changed)
            left.addWidget(self.brands_list)
            # butoane mărci
            bctl = QHBoxLayout()
            btn_all = QPushButton("Toate")
            btn_pop = QPushButton("Populare")
            btn_clear = QPushButton("Curăță")
            btn_all.clicked.connect(self.select_all_brands)
            btn_pop.clicked.connect(self.select_popular_brands)
            btn_clear.clicked.connect(self.clear_brands)
            bctl.addWidget(btn_all); bctl.addWidget(btn_pop); bctl.addWidget(btn_clear)
            left.addLayout(bctl)
            # ——— Modele
            right = QVBoxLayout()
            lab_m = QLabel("Modele (pentru marca activă):")
            lab_m.setFont(QFont("Arial", 12, QFont.Bold))
            right.addWidget(lab_m)
            self.models_list = QListWidget()
            self.models_list.setSelectionMode(QAbstractItemView.MultiSelection)
            self.models_list.setMaximumHeight(260)
            self.models_list.itemSelectionChanged.connect(self.on_models_selection_changed)
            right.addWidget(self.models_list)
            mctl = QHBoxLayout()
            btn_ma = QPushButton("Toate")
            btn_mc = QPushButton("Curăță")
            btn_ma.clicked.connect(self.select_all_models)
            btn_mc.clicked.connect(self.clear_models)
            mctl.addWidget(btn_ma); mctl.addWidget(btn_mc)
            right.addLayout(mctl)
            outer.addLayout(left); outer.addLayout(right)
            group.setLayout(outer)
            return group
        
    def filter_brands(self, text: str):
            """Filtrează lista de mărci după text (case-insensitive)."""
            t = text.strip().lower()
            for i in range(self.brands_list.count()):
                it = self.brands_list.item(i)
                it.setHidden(False if not t else (t not in it.text().lower()))
        
    def on_brand_clicked(self, item: QListWidgetItem):
            """Când utilizatorul face click pe o marcă -> devine 'activă' pentru lista de modele."""
            self.save_current_models_of_active_brand()
            self.active_brand = item.text()
            self.refresh_models_for_active_brand()
        
    def on_brand_selection_changed(self):
            """Dacă nu avem brand activ sau a fost deselectat, alegem primul selectat ca brand activ."""
            if self.active_brand:
                # dacă active_brand nu mai e selectată, mutăm pe prima selectată
                active_still = any(self.active_brand == it.text() for it in self.brands_list.selectedItems())
                if not active_still:
                    self.active_brand = self.brands_list.selectedItems()[0].text() if self.brands_list.selectedItems() else None
            else:
                self.active_brand = self.brands_list.selectedItems()[0].text() if self.brands_list.selectedItems() else None
            self.refresh_models_for_active_brand()
        
    def save_current_models_of_active_brand(self):
            """Salvează selecția curentă de modele pentru marca activă."""
            if not self.active_brand: return
            sel = {self.models_list.item(i).text()
                for i in range(self.models_list.count())
                if self.models_list.item(i).isSelected()}
            self.selected_models_by_brand[self.active_brand] = sel
        
    def refresh_models_for_active_brand(self):
            """Re-umple lista de modele pentru marca activă + preselectează cele memorate."""
            self.models_list.clear()
            if not self.active_brand:
                return
            models = CAR_BRANDS_MODELS.get(self.active_brand, ["Toate modelele"])
            for m in models:
                self.models_list.addItem(m)
            # preselectăm ce a fost salvat
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
            # dacă nu avem activă, setăm prima vizibilă
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
            """Memorează imediat selecția modelelor pentru marca activă."""
            self.save_current_models_of_active_brand()
        
    def create_filters_group(self):
            group = QGroupBox("⚙️ Opțiuni Filtre")
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
            group = QGroupBox("🔧 Setări Avansate")
            layout = QGridLayout()
            layout.addWidget(QLabel("Monedă:"), 0, 0)
            self.currency_combo = QComboBox(); self.currency_combo.addItems(["EUR", "RON"])
            layout.addWidget(self.currency_combo, 0, 1)
            layout.addWidget(QLabel("Pagini per marcă:"), 0, 2)
            self.max_pages = QSpinBox(); self.max_pages.setRange(1, 10); self.max_pages.setValue(2)
            layout.addWidget(self.max_pages, 0, 3)
            safety_info = QLabel("🛡️ Întârzieri 5–15 sec între cereri pentru a evita blocarea IP")
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
            self.results_table.setColumnCount(11)
            self.results_table.setHorizontalHeaderLabels(["Titlu","Preț","An","KM","Locație","Combustibil","Transmisie","Caroserie","Marcă","Model","Acțiuni"])
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
                QMessageBox.warning(self, "Atenție", "Te rog selectează cel puțin o marcă!")
                return None
            # salvează selecția pentru marca activă înainte de a citi tot
            self.save_current_models_of_active_brand()
            models_by_brand: Dict[str, List[str]] = {}
            for b in selected_brands:
                # dacă nu a salvat utilizatorul nimic pentru marca b => listă goală = toate modelele
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
                f"• Mărci: {len(config.brands)} ({brands_info})\n"
                f"• Filtre: combustibil({', '.join(config.fuel_types) or '–'}), caroserie({', '.join(config.car_bodies) or '–'}), "
                f"transmisie({', '.join(config.gearbox_types) or '–'}), stare({', '.join(config.car_states) or '–'})\n"
                f"• Ani: {config.year_min}–{config.year_max} | Preț: {config.price_min}-{config.price_max} {config.currency}\n"
                f"• Pagini/marcă: {config.max_pages_per_brand}\n\n"
                f"Continui?"
            )
            if QMessageBox.question(self, "Confirmă Scraping-ul", summary, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
            self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True); self.export_btn.setEnabled(False)
            self.progress_bar.setValue(0); self.progress_label.setText("Inițializare scraper…")
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
                    'an': c.year, 'kilometraj': c.km, 'locatie': c.location,
                    'link': c.link, 'imagini_urls': ';'.join(c.image_urls) if c.image_urls else '',
                    'combustibil': c.fuel_type, 'transmisie': c.gearbox, 'caroserie': c.car_body,
                    'marca': c.brand, 'model': c.model,
                    'id_unic': c.unique_id, 'data_scraping': c.scrape_date
                })
            
            # Save CSV file
            df = pd.DataFrame(rows)
            df.to_csv(file_path, index=False, encoding='utf-8')
            
            upload_status = f"✅ Auto-saved: {filename}"
            
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
                            upload_status += f" | 🚀 GitHub uploaded successfully!"
                        else:
                            upload_status += f" | ⚠️ GitHub upload failed"
                    else:
                        upload_status += f" | ⚠️ File not accessible for upload"
                else:
                    upload_status += f" | ℹ️ No GitHub config found"
            except Exception as e:
                upload_status += f" | ⚠️ Upload error: {str(e)[:50]}..."
                
            return upload_status
            
        except Exception as e:
            return f"❌ Auto-export failed: {str(e)[:50]}..."

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
                self.results_info.setText("⚠️ Nicio mașină nouă găsită. Încearcă să relaxezi filtrele.")
                self.results_info.setStyleSheet("color: #FF9800; font-size: 14px; margin: 10px;")
            
            self.populate_results_table(cars)
            self.tab_widget.setCurrentIndex(1)
            
            if cars:
                message = f"{len(cars)} mașini noi!\n\n"
                message += f"📊 Rezultatele sunt în tab-ul Rezultate.\n"
                message += f"💾 Click 'Export Results' pentru CSV/XLSX.\n\n"
                message += f"🤖 {auto_status}"
                
                QMessageBox.information(self,"Scraping Finalizat", message)
        
    def scraping_failed(self, error_message):
            self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
            self.progress_label.setText(f"Scraping eșuat: {error_message}")
            QMessageBox.critical(self,"Eroare Scraping",
                f"Scraping eșuat:\n\n{error_message}\n\n"
                f"💡 Verifică internetul, redu mărci/pagini, sau încearcă mai târziu.")
        
    def populate_results_table(self, cars: List[CarData]):
            self.results_table.setRowCount(len(cars))
            for row, car in enumerate(cars):
                title_text = car.title[:60] + ("…" if len(car.title) > 60 else "")
                self.results_table.setItem(row, 0, QTableWidgetItem(title_text))
                self.results_table.setItem(row, 1, QTableWidgetItem(car.price_text))
                self.results_table.setItem(row, 2, QTableWidgetItem(car.year))
                self.results_table.setItem(row, 3, QTableWidgetItem(car.km))
                self.results_table.setItem(row, 4, QTableWidgetItem(car.location))
                self.results_table.setItem(row, 5, QTableWidgetItem(car.fuel_type))
                self.results_table.setItem(row, 6, QTableWidgetItem(car.gearbox))
                self.results_table.setItem(row, 7, QTableWidgetItem(car.car_body))
                self.results_table.setItem(row, 8, QTableWidgetItem(car.brand))
                self.results_table.setItem(row, 9, QTableWidgetItem(car.model))
                btn = QPushButton("Deschide"); btn.setToolTip("Deschide anunțul în browser")
                btn.clicked.connect(lambda checked, url=car.link: self.open_car_link(url))
                self.results_table.setCellWidget(row, 10, btn)
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
                        'an': c.year, 'kilometraj': c.km, 'locatie': c.location,
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
                        QMessageBox.warning(self, "openpyxl lipsă", f"Instalează 'openpyxl' (pip install openpyxl)\n{e}\nSalvez CSV în schimb.")
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
    

# ---------- main ----------
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("OLX Advanced Car Scraper")
    app.setApplicationVersion("3.1")
    app.setOrganizationName("CarScraperPro")
    w = OLXAdvancedScraper(); w.show()
    QMessageBox.information(
        w, "🚗 Bun venit",
        "🆕 Căutare mărci + memorare modele per marcă\n\n"
        "Cum folosești:\n"
        "1) Scrie în bara de căutare o marcă (ex. „bmw”) ca s-o găsești rapid.\n"
        "2) Selectează marca (devine „activă”), bifează modelele ei.\n"
        "3) Selectează a doua marcă, bifează modelele ei – selecția primei mărci rămâne memorată.\n"
        "4) Setează filtrele (opțional) și apasă Start Scraping."
    )
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
