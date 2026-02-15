#!/bin/bash

# Quick Start Script for Dinner Backend with Local CSV Import

set -e  # Exit on error

echo "🍽️  Dinner Backend - Quick Setup"
echo "================================"
echo ""

# Check if CSV files exist
if [ ! -f "lunch_bbq_data.csv" ]; then
    echo "❌ Error: lunch_bbq_data.csv not found in project root"
    exit 1
fi

if [ ! -f "other_data.csv" ]; then
    echo "❌ Error: other_data.csv not found in project root"
    exit 1
fi

echo "✅ CSV files found"
echo ""

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "🐍 Activating virtual environment..."
    source .venv/bin/activate
fi

# Run migrations
echo "📦 Running database migrations..."
python manage.py migrate

# Import event data
echo "📥 Importing event data from CSV files..."
python manage.py import_event_data

# Show statistics
echo ""
echo "📊 Import Statistics:"
python manage.py shell -c "
from main.models import User
print(f'  Total users: {User.objects.count()}')
print(f'  Friday Lunch: {User.objects.filter(has_friday_lunch=True).count()}')
print(f'  Saturday Lunch: {User.objects.filter(has_saturday_lunch=True).count()}')
print(f'  BBQ registrations: {User.objects.filter(has_bbq=True).count()}')
"

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the server:"
echo "  python manage.py runserver"
echo ""
echo "To access admin dashboard:"
echo "  http://localhost:8000/administrator/"
echo ""
