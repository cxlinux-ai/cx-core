#!/bin/bash
# ============================================================================
# WaterRightsX - Complete System Deployment for Jesse
# ============================================================================
# One-command script to build Jesse's water rights movement matching platform
#
# What this builds:
# 1. Import 160,000 Utah water rights with owner contact info
# 2. Scrape all 97 basin policies for movement rules
# 3. Build movement matching engine
# 4. Generate lead lists for target locations
#
# Usage: bash deploy_jesse_system.sh
#
# Author: Michael J. Morgan - WaterRightsX
# ============================================================================

set -e  # Exit on any error

echo "🌊 WaterRightsX - Complete System Deployment"
echo "============================================"
echo ""
echo "Building Jesse's Water Rights Movement Platform:"
echo "   ✓ 160,000 Utah water rights database"
echo "   ✓ Basin policy scraper (97 basins)"
echo "   ✓ Movement matching engine"
echo "   ✓ Lead generation system"
echo ""
echo "⏱️  Expected time: 15-20 minutes"
echo "💾 Expected size: ~600MB download"
echo ""

read -p "Continue with full deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "❌ Deployment cancelled"
    exit 1
fi

echo ""
echo "============================================================================"
echo "PHASE 1: Installing Dependencies"
echo "============================================================================"
echo ""

pip install --break-system-packages \
    geopandas \
    psycopg2-binary \
    requests \
    beautifulsoup4 \
    pyproj \
    shapely \
    fiona \
    --quiet

echo "✅ Dependencies installed"

echo ""
echo "============================================================================"
echo "PHASE 2: Database Schema Setup"
echo "============================================================================"
echo ""

# Create enhanced water rights schema
if [ -n "$DATABASE_URL" ]; then
    psql "$DATABASE_URL" << 'EOF'
-- Add new columns for Jesse's requirements
ALTER TABLE water_rights ADD COLUMN IF NOT EXISTS owner_address TEXT;
ALTER TABLE water_rights ADD COLUMN IF NOT EXISTS owner_city TEXT;
ALTER TABLE water_rights ADD COLUMN IF NOT EXISTS owner_zip TEXT;
ALTER TABLE water_rights ADD COLUMN IF NOT EXISTS is_non_use BOOLEAN DEFAULT FALSE;
ALTER TABLE water_rights ADD COLUMN IF NOT EXISTS can_be_moved BOOLEAN DEFAULT TRUE;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_non_use ON water_rights(is_non_use);
CREATE INDEX IF NOT EXISTS idx_basin ON water_rights(basin);
CREATE INDEX IF NOT EXISTS idx_volume ON water_rights(annual_volume_af);

-- Create basin policies tables (will be populated by scraper)
CREATE TABLE IF NOT EXISTS basin_policies (
    id SERIAL PRIMARY KEY,
    area_number VARCHAR(10) UNIQUE NOT NULL,
    area_name TEXT NOT NULL,
    url TEXT NOT NULL,
    full_text TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS movement_rules (
    id SERIAL PRIMARY KEY,
    area_number VARCHAR(10) REFERENCES basin_policies(area_number),
    rule_type VARCHAR(50),
    rule_text TEXT NOT NULL,
    is_restriction BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_area_number ON basin_policies(area_number);
CREATE INDEX IF NOT EXISTS idx_movement_area ON movement_rules(area_number);

EOF
    
    echo "✅ Database schema updated"
else
    echo "⚠️  DATABASE_URL not set - skipping schema updates"
fi

echo ""
echo "============================================================================"
echo "PHASE 3: Import 160,000 Water Rights"
echo "============================================================================"
echo ""

python3 import_utah_water_rights.py

echo ""
echo "============================================================================"
echo "PHASE 4: Scrape Basin Policies"
echo "============================================================================"
echo ""

python3 scrape_basin_policies.py

echo ""
echo "============================================================================"
echo "PHASE 5: Test Movement Matching Engine"
echo "============================================================================"
echo ""

python3 movement_matching_engine.py

echo ""
echo "============================================================================"
echo "✅ DEPLOYMENT COMPLETE!"
echo "============================================================================"
echo ""
echo "📊 System Summary:"
if [ -n "$DATABASE_URL" ]; then
    echo ""
    echo "Water Rights Database:"
    psql "$DATABASE_URL" -c "SELECT COUNT(*) as total_water_rights FROM water_rights;"
    
    echo ""
    echo "Non-Use Rights (Best Leads):"
    psql "$DATABASE_URL" -c "SELECT COUNT(*) as non_use_count FROM water_rights WHERE is_non_use = TRUE;"
    
    echo ""
    echo "Basin Policies Scraped:"
    psql "$DATABASE_URL" -c "SELECT COUNT(*) as total_basins FROM basin_policies;"
    
    echo ""
    echo "Movement Rules Extracted:"
    psql "$DATABASE_URL" -c "SELECT COUNT(*) as total_rules FROM movement_rules;"
fi

echo ""
echo "============================================================================"
echo "🎯 JESSE'S USE CASES - READY TO GO:"
echo "============================================================================"
echo ""
echo "1. FIND WATER FOR PARK CITY:"
echo "   python3 -c \""
echo "   from movement_matching_engine import MovementMatchingEngine"
echo "   engine = MovementMatchingEngine()"
echo "   leads = engine.find_moveable_rights(40.6461, -111.4980, max_distance_miles=10)"
echo "   print(f'Found {len(leads)} moveable water rights for Park City')"
echo "   \""
echo ""
echo "2. FIND WATER FOR LITTLE COTTONWOOD CANYON:"
echo "   python3 -c \""
echo "   from movement_matching_engine import MovementMatchingEngine"
echo "   engine = MovementMatchingEngine()"
echo "   leads = engine.find_moveable_rights(40.5732, -111.7813, max_distance_miles=5)"
echo "   print(f'Found {len(leads)} moveable water rights for Little Cottonwood')"
echo "   \""
echo ""
echo "3. GENERATE LEAD LIST (Non-Use Priority):"
echo "   - Check park_city_lead_list.json"
echo "   - Contains owner contact information"
echo "   - Sorted by arbitrage opportunity"
echo "   - Non-use rights highlighted (best leads)"
echo ""
echo "============================================================================"
echo "📞 NEXT STEPS FOR JESSE:"
echo "============================================================================"
echo ""
echo "✓ Database has 160,000 water rights with owner info"
echo "✓ Basin policies scraped and parsed"
echo "✓ Movement matching engine operational"
echo "✓ Lead generation system ready"
echo ""
echo "To use the platform:"
echo "1. Identify target parcel (coordinates)"
echo "2. Run movement matching engine"
echo "3. Get filtered list of moveable rights"
echo "4. Contact owners (prioritize non-use status)"
echo "5. Negotiate purchase/lease"
echo "6. File change application with State Engineer"
echo ""
echo "For web interface, restart your application to see:"
echo "• Interactive map with all 160K water rights"
echo "• Movement analyzer tool"
echo "• Lead generator with owner contact info"
echo "• Basin policy viewer"
echo ""
echo "============================================================================"
