"""
search_listings tool: Searches the listings dataset for items matching
description, size, and max budget. Scores and ranks matches.
"""

from utils.data_loader import load_listings
from typing import Optional
import re


def extract_style_keywords(description: str) -> list[str]:
    """
    Extract key style-related words from the user's description.
    
    Args:
        description: Free-text shopping intent (e.g., "vintage graphic tee")
    
    Returns:
        List of extracted keywords (lowercase, deduplicated)
    """
    # Remove punctuation and split into words
    words = re.findall(r'\b\w+\b', description.lower())
    
    # Filter out common stop words
    stop_words = {'a', 'an', 'the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'is', 'of'}
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    
    return list(set(keywords))  # Deduplicate


def calculate_match_score(listing: dict, keywords: list[str]) -> float:
    """
    Calculate a relevance score (0.0 to 1.0) for a listing based on keyword matches.
    
    Scoring logic:
    - Title matches: 0.5 per keyword found
    - Style tags: 0.3 per tag matching a keyword
    - Description: 0.1 per keyword found
    - Category hints: 0.2 if category name is in keywords
    
    Args:
        listing: A listing dictionary
        keywords: List of search keywords
    
    Returns:
        Match score between 0.0 and 1.0
    """
    if not keywords:
        return 0.5  # Default moderate score if no keywords provided
    
    score = 0.0
    
    # Title matches (highest weight)
    title_lower = listing.get('title', '').lower()
    for keyword in keywords:
        if keyword in title_lower:
            score += 0.5
    
    # Style tags matches
    style_tags = [tag.lower() for tag in listing.get('style_tags', [])]
    for keyword in keywords:
        if keyword in style_tags:
            score += 0.3
    
    # Description matches
    desc_lower = listing.get('description', '').lower()
    for keyword in keywords:
        if keyword in desc_lower:
            score += 0.1
    
    # Category hint
    category = listing.get('category', '').lower()
    for keyword in keywords:
        if keyword == category or keyword in category:
            score += 0.2
    
    # Normalize score to 0.0-1.0 range
    # Maximum possible score: (0.5 + 0.3 + 0.1 + 0.2) * num_keywords
    max_possible = (0.5 + 0.3 + 0.1 + 0.2) * len(keywords)
    if max_possible > 0:
        normalized_score = min(score / max_possible, 1.0)
    else:
        normalized_score = 0.0
    
    return normalized_score


def matches_size(listing_size: str, requested_size: str) -> bool:
    """
    Check if listing size matches the requested size using exact or partial match.
    
    Examples:
    - "L" matches "L" exactly
    - "S/M" matches both "S" and "M"
    - "W30" matches "W30"
    
    Args:
        listing_size: Size from listing (e.g., "L", "S/M", "W30 L30")
        requested_size: Size requested by user (e.g., "L")
    
    Returns:
        True if sizes are compatible, False otherwise
    """
    if not listing_size or not requested_size:
        return True  # If either is missing, don't filter
    
    listing_size_lower = listing_size.lower()
    requested_size_lower = requested_size.lower()
    
    # Exact match
    if listing_size_lower == requested_size_lower:
        return True
    
    # Partial/substring match (e.g., "L" in "S/M/L" or in "W30 L30")
    if requested_size_lower in listing_size_lower:
        return True
    
    # Check if it's a size range that includes the requested size
    size_parts = [s.strip() for s in listing_size_lower.replace('/', ' ').split()]
    if requested_size_lower in size_parts:
        return True
    
    return False


def search_listings(description: str, size: str, max_price: float) -> dict:
    """
    Search the listings dataset for items matching description, size, and budget.
    
    Args:
        description (str): Free-text shopping intent (e.g., "vintage graphic tee")
        size (str): Requested size (e.g., "L", "S/M", "W30")
        max_price (float): Upper budget cap in USD
    
    Returns:
        Dictionary containing:
        - query_summary (dict): Original search parameters + extracted keywords
        - matches (list[dict]): Ranked listings, each with match_score
        - match_count (int): Number of matches found
    """
    # Extract style keywords from description
    keywords = extract_style_keywords(description)
    
    # Load listings dataset
    all_listings = load_listings()
    
    # Filter and score
    filtered_matches = []
    
    for listing in all_listings:
        # Filter by price
        if listing.get('price', float('inf')) > max_price:
            continue
        
        # Filter by size
        if not matches_size(listing.get('size', ''), size):
            continue
        
        # Calculate match score
        score = calculate_match_score(listing, keywords)
        
        # Include match with score
        match_dict = {
            'id': listing.get('id'),
            'title': listing.get('title'),
            'description': listing.get('description'),
            'category': listing.get('category'),
            'style_tags': listing.get('style_tags', []),
            'size': listing.get('size'),
            'condition': listing.get('condition'),
            'price': listing.get('price'),
            'colors': listing.get('colors', []),
            'brand': listing.get('brand'),
            'platform': listing.get('platform'),
            'match_score': round(score, 3),
        }
        filtered_matches.append(match_dict)
    
    # Sort by match_score descending (best matches first)
    filtered_matches.sort(key=lambda x: x['match_score'], reverse=True)
    
    # Build response
    return {
        'query_summary': {
            'description': description,
            'size': size,
            'max_price': max_price,
            'style_keywords': keywords,
        },
        'matches': filtered_matches,
        'match_count': len(filtered_matches),
    }
