"""
Unit tests for graph export functionality.

Tests that the export buttons are present and the JavaScript export functions
are properly implemented.
"""

import json
from pathlib import Path

import pytest


class TestGraphExportUI:
    """Test that export UI elements are present and properly configured."""
    
    def test_export_buttons_exist_in_html(self):
        """Test that export buttons exist in the HTML."""
        html_path = Path("ui/graph.html")
        content = html_path.read_text()
        
        # Check for export buttons
        assert 'id="exportJson"' in content, "HTML should have JSON export button"
        assert 'id="exportPng"' in content, "HTML should have PNG export button"
        
        # Check button text
        assert "Export JSON" in content, "JSON export button should have correct label"
        assert "Export PNG" in content, "PNG export button should have correct label"
    
    def test_export_buttons_container_exists(self):
        """Test that export buttons container exists."""
        html_path = Path("ui/graph.html")
        content = html_path.read_text()
        
        assert 'id="exportButtons"' in content, "HTML should have export buttons container"
        assert 'class="export-buttons"' in content, "Export buttons should have proper styling class"
    
    def test_export_buttons_initially_hidden(self):
        """Test that export buttons are initially hidden until graph loads."""
        html_path = Path("ui/graph.html")
        content = html_path.read_text()
        
        # Find the exportButtons element and check if it has display:none
        assert 'id="exportButtons"' in content
        # The element should have style="display:none;" initially
        assert 'style="display:none;"' in content or 'style="display:none"' in content


class TestGraphExportJavaScript:
    """Test that export JavaScript functions are properly implemented."""
    
    def test_json_export_function_exists(self):
        """Test that JSON export function is implemented."""
        js_path = Path("ui/graph-viz.js")
        content = js_path.read_text()
        
        # Check for JSON export event listener
        assert 'el("exportJson").addEventListener' in content or \
               'getElementById("exportJson").addEventListener' in content, \
               "JavaScript should have JSON export event listener"
        
        # Check for JSON export implementation
        assert "JSON.stringify" in content, "JSON export should stringify data"
        assert "application/json" in content, "JSON export should use correct MIME type"
        assert ".json" in content, "JSON export should use .json file extension"
    
    def test_png_export_function_exists(self):
        """Test that PNG export function is implemented."""
        js_path = Path("ui/graph-viz.js")
        content = js_path.read_text()
        
        # Check for PNG export event listener
        assert 'el("exportPng").addEventListener' in content or \
               'getElementById("exportPng").addEventListener' in content, \
               "JavaScript should have PNG export event listener"
        
        # Check for PNG export implementation
        assert "canvas" in content, "PNG export should use canvas"
        assert "toBlob" in content, "PNG export should use canvas.toBlob"
        assert ".png" in content, "PNG export should use .png file extension"
    
    def test_export_uses_blob_and_download(self):
        """Test that export functions use Blob and download mechanism."""
        js_path = Path("ui/graph-viz.js")
        content = js_path.read_text()
        
        # Check for Blob creation
        assert "Blob" in content, "Export should create Blob objects"
        
        # Check for URL.createObjectURL
        assert "URL.createObjectURL" in content, "Export should create object URLs"
        
        # Check for download attribute
        assert "download" in content, "Export should set download attribute"
        
        # Check for URL cleanup
        assert "URL.revokeObjectURL" in content, "Export should clean up object URLs"
    
    def test_export_filename_includes_repo_name(self):
        """Test that export filenames include repository name."""
        js_path = Path("ui/graph-viz.js")
        content = js_path.read_text()
        
        # Check that filename includes repo name
        assert "currentGraphData.repo" in content, "Export filename should include repo name"
        assert 'replace("/", "_")' in content or "replace('/', '_')" in content, \
               "Export should sanitize repo name for filename"
    
    def test_export_guards_against_missing_data(self):
        """Test that export functions check for data availability."""
        js_path = Path("ui/graph-viz.js")
        content = js_path.read_text()
        
        # JSON export should check for currentGraphData
        assert "if (!currentGraphData)" in content or "if(!currentGraphData)" in content, \
               "JSON export should check if graph data exists"
        
        # PNG export should check for network
        assert "if (!network)" in content or "if(!network)" in content, \
               "PNG export should check if network exists"


class TestGraphExportStyling:
    """Test that export buttons have proper styling."""
    
    def test_export_button_styles_defined(self):
        """Test that export button styles are defined in CSS."""
        html_path = Path("ui/graph.html")
        content = html_path.read_text()
        
        # Check for export button styles
        assert ".export-btn" in content or ".export-buttons" in content, \
               "CSS should define export button styles"
    
    def test_export_buttons_have_hover_effects(self):
        """Test that export buttons have hover effects defined."""
        html_path = Path("ui/graph.html")
        content = html_path.read_text()
        
        # Check for hover styles
        assert ".export-btn:hover" in content, "Export buttons should have hover effects"


class TestGraphExportIntegration:
    """Integration tests for export functionality."""
    
    def test_export_buttons_shown_after_graph_load(self):
        """Test that export buttons are shown after graph loads."""
        js_path = Path("ui/graph-viz.js")
        content = js_path.read_text()
        
        # Check that renderGraph function shows export buttons
        assert 'el("exportButtons")' in content or 'getElementById("exportButtons")' in content, \
               "JavaScript should reference export buttons"
        
        # Check that display is set to flex or block
        assert 'style.display = "flex"' in content or 'style.display = "block"' in content, \
               "Export buttons should be shown after graph loads"
    
    def test_json_export_includes_complete_graph_data(self):
        """Test that JSON export includes complete graph data."""
        js_path = Path("ui/graph-viz.js")
        content = js_path.read_text()
        
        # JSON export should export currentGraphData which includes everything
        json_export_section = content[content.find('el("exportJson")'):content.find('el("exportJson")') + 500]
        
        assert "currentGraphData" in json_export_section, \
               "JSON export should export complete graph data"
        assert "JSON.stringify" in json_export_section, \
               "JSON export should stringify the data"
    
    def test_png_export_uses_canvas_element(self):
        """Test that PNG export uses the canvas element from vis.js."""
        js_path = Path("ui/graph-viz.js")
        content = js_path.read_text()
        
        # PNG export should query for canvas element
        png_export_section = content[content.find('el("exportPng")'):content.find('el("exportPng")') + 500]
        
        assert "canvas" in png_export_section, \
               "PNG export should reference canvas element"
        assert "querySelector" in png_export_section or "querySelectorAll" in png_export_section, \
               "PNG export should query for canvas element"


class TestGraphExportDocumentation:
    """Test that export functionality is documented."""
    
    def test_export_mentioned_in_demo_script(self):
        """Test that export is mentioned in demo script."""
        demo_path = Path("demo_graph_visualization.py")
        if demo_path.exists():
            content = demo_path.read_text()
            assert "export" in content.lower() or "Export" in content, \
                   "Demo script should mention export functionality"
    
    def test_export_mentioned_in_readme(self):
        """Test that export is mentioned in UI README if it exists."""
        readme_path = Path("ui/README.md")
        if readme_path.exists():
            content = readme_path.read_text()
            assert "export" in content.lower() or "Export" in content, \
                   "UI README should mention export functionality"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
