#!/usr/bin/env python3
"""
Demo script for testing the graph visualization.

This script starts the API server and provides instructions for viewing
the graph visualization in a browser.
"""

import os
import sys
import webbrowser
from pathlib import Path


def main():
    print("=" * 70)
    print("Supply Chain Graph Visualization Demo")
    print("=" * 70)
    print()
    
    # Check if API server is already running
    print("📋 Pre-flight checks:")
    print()
    
    # Check if visualization files exist
    html_path = Path("ui/graph.html")
    js_path = Path("ui/graph-viz.js")
    
    if not html_path.exists():
        print("❌ Error: ui/graph.html not found")
        print("   Please run this script from the project root directory")
        sys.exit(1)
    
    if not js_path.exists():
        print("❌ Error: ui/graph-viz.js not found")
        print("   Please run this script from the project root directory")
        sys.exit(1)
    
    print("✅ Visualization files found")
    print()
    
    # Instructions
    print("📖 Instructions:")
    print()
    print("1. Start the API server in a separate terminal:")
    print("   cd api")
    print("   uvicorn app:app --reload")
    print()
    print("2. Open the visualization in your browser:")
    print(f"   file://{html_path.absolute()}")
    print()
    print("3. Try these example repositories:")
    print("   • numpy/numpy")
    print("   • psf/requests")
    print("   • pallets/flask")
    print()
    print("4. Use the controls to:")
    print("   • Filter by node type")
    print("   • Adjust confidence threshold")
    print("   • Search for specific nodes")
    print("   • Click nodes to see details")
    print("   • Export graph as JSON or PNG")
    print()
    
    # Offer to open browser
    response = input("Would you like to open the visualization in your browser? (y/n): ")
    if response.lower() in ['y', 'yes']:
        url = f"file://{html_path.absolute()}"
        print(f"\n🌐 Opening {url}")
        webbrowser.open(url)
        print()
        print("✅ Browser opened!")
        print()
        print("⚠️  Remember to start the API server if you haven't already:")
        print("   cd api && uvicorn app:app --reload")
    else:
        print("\n👍 You can manually open the file:")
        print(f"   {html_path.absolute()}")
    
    print()
    print("=" * 70)
    print("Happy visualizing! 📊")
    print("=" * 70)


if __name__ == "__main__":
    main()
