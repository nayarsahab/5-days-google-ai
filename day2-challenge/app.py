import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Cache file/storage for release notes to avoid constant fetching
RELEASE_NOTES_CACHE = []

def parse_xml_feed(xml_content):
    """Parses the BigQuery Atom XML feed and splits it into structured updates."""
    try:
        # Register namespaces to parse Atom correctly
        root = ET.fromstring(xml_content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        entries = []
        
        for entry in root.findall('atom:entry', ns):
            title_el = entry.find('atom:title', ns)
            updated_el = entry.find('atom:updated', ns)
            link_el = entry.find('atom:link', ns)
            content_el = entry.find('atom:content', ns)
            
            date = title_el.text.strip() if title_el is not None else "Unknown Date"
            updated = updated_el.text.strip() if updated_el is not None else ""
            
            link = ""
            if link_el is not None:
                link = link_el.attrib.get('href', '')
            
            html_content = content_el.text if content_el is not None else ""
            
            # Parse the HTML content to break it down into category blocks (e.g., Feature, Change, Issue, Announcement)
            soup = BeautifulSoup(html_content, 'html.parser')
            
            updates = []
            current_type = "General"
            current_elements = []
            
            # Helper to finalize an update block
            def add_update(category, elements):
                if not elements:
                    return
                # Reconstruct HTML block
                html_block = "".join(str(el) for el in elements).strip()
                # Clean up text
                text_block = BeautifulSoup(html_block, 'html.parser').get_text().strip()
                # Normalize spaces
                text_block = re.sub(r'\s+', ' ', text_block)
                updates.append({
                    'type': category,
                    'html': html_block,
                    'text': text_block
                })

            for child in soup.children:
                # If we hit an h3 tag, it marks the beginning of a new category of updates
                if child.name == 'h3':
                    add_update(current_type, current_elements)
                    current_type = child.get_text().strip()
                    current_elements = []
                elif child.name is not None:
                    current_elements.append(child)
            
            # Add the last category block
            add_update(current_type, current_elements)
            
            # If no structured blocks were found, fallback to the entire content
            if not updates and html_content.strip():
                text_content = soup.get_text().strip()
                text_content = re.sub(r'\s+', ' ', text_content)
                updates.append({
                    'type': 'General',
                    'html': html_content,
                    'text': text_content
                })
            
            entries.append({
                'date': date,
                'updated': updated,
                'link': link,
                'updates': updates
            })
            
        return entries
    except Exception as e:
        print(f"Error parsing XML feed: {e}")
        raise e

def fetch_latest_release_notes():
    """Fetches the latest BigQuery release notes XML feed from Google Cloud Feeds."""
    global RELEASE_NOTES_CACHE
    url = "https://docs.cloud.google.com/feeds/bigquery-release-notes.xml"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code == 200:
        RELEASE_NOTES_CACHE = parse_xml_feed(response.content)
        return True
    else:
        raise Exception(f"HTTP Error {response.status_code} fetching feed")

@app.route('/')
def index():
    """Serves the frontend page."""
    return render_template('index.html')

@app.route('/api/release-notes', methods=['GET'])
def get_release_notes():
    """API endpoint to get release notes from the cache."""
    global RELEASE_NOTES_CACHE
    # Fetch if cache is empty
    if not RELEASE_NOTES_CACHE:
        try:
            fetch_latest_release_notes()
        except Exception as e:
            return jsonify({'error': str(e)}), 500
            
    return jsonify(RELEASE_NOTES_CACHE)

@app.route('/api/refresh', methods=['POST'])
def refresh_release_notes():
    """API endpoint to force refresh the release notes from source."""
    try:
        fetch_latest_release_notes()
        return jsonify({'status': 'success', 'message': 'Release notes refreshed successfully.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Initialize cache on startup
    try:
        print("Pre-fetching release notes on startup...")
        fetch_latest_release_notes()
    except Exception as e:
        print(f"Warning: Could not pre-fetch release notes on startup: {e}")
        
    app.run(debug=True, port=5000)
