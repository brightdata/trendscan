"""
TrendScan Utilities

Shared utility functions for logging, file operations, and data processing.
"""

import json
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler

from config import LoggingConfig


def setup_logging(config: LoggingConfig) -> logging.Logger:
    """Set up logging with console and optional file handlers."""
    log_dir = Path(config.log_directory)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.level.upper()))
    
    root_logger.handlers.clear()  # Avoid duplicate handlers
    
    formatter = logging.Formatter(config.format)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.level.upper()))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if enabled)
    if config.enable_file_logging:
        log_file = log_dir / f"TrendScan_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=config.max_file_size_mb * 1024 * 1024,
            backupCount=config.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    logger = logging.getLogger("TrendScan")
    logger.info("Logging system initialized")
    
    return logger


def sanitize_filename(filename: str) -> str:
    """Clean filename by removing invalid characters and normalizing format."""
    # Remove invalid file system characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Normalize whitespace
    sanitized = re.sub(r'\s+', '_', sanitized)
    
    sanitized = sanitized.strip(' .')
    sanitized = sanitized.lower()
    
    if not sanitized:
        sanitized = "unknown"
    
    # Limit length to prevent file system issues
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    
    return sanitized


def create_output_structure(company_name: str, base_directory: str, 
                          include_timestamp: bool = True) -> Path:
    """Create organized output directory structure for a company."""
    safe_company_name = sanitize_filename(company_name)
    
    base_path = Path(base_directory)
    base_path.mkdir(parents=True, exist_ok=True)
    
    # Add timestamp to avoid directory conflicts
    if include_timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        company_dir = base_path / f"{safe_company_name}_{timestamp}"
    else:
        company_dir = base_path / safe_company_name
    
    company_dir.mkdir(parents=True, exist_ok=True)
    
    return company_dir


def format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def format_file_size(size_bytes: int) -> str:
    """Format bytes into human-readable file size string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        kb = size_bytes / 1024
        return f"{kb:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        mb = size_bytes / (1024 * 1024)
        return f"{mb:.1f} MB"
    else:
        gb = size_bytes / (1024 * 1024 * 1024)
        return f"{gb:.1f} GB"


def get_file_info(file_path: str) -> Dict[str, Any]:
    """Get comprehensive file information including size, dates, and metadata."""
    try:
        path = Path(file_path)
        if not path.exists():
            return {"exists": False}
        
        stat = path.stat()
        
        return {
            "exists": True,
            "name": path.name,
            "size_bytes": stat.st_size,
            "size_formatted": format_file_size(stat.st_size),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "extension": path.suffix.lower(),
            "is_directory": path.is_dir(),
            "absolute_path": str(path.absolute())
        }
    except Exception as e:
        return {
            "exists": False,
            "error": str(e)
        }


def validate_json_file(file_path: str) -> Dict[str, Any]:
    """Validate JSON file format and return parsing information."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = f.read()
        
        # Parse and validate JSON structure
        parsed_data = json.loads(data)
        
        return {
            "valid": True,
            "size_chars": len(data),
            "type": type(parsed_data).__name__,
            "items_count": len(parsed_data) if isinstance(parsed_data, (list, dict)) else None
        }
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "error": f"JSON decode error: {e}",
            "error_type": "json"
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "error_type": "file"
        }


if __name__ == "__main__":
    # Test the utility functions
    print("Testing TrendScan utilities...")
    
    test_names = [
        "OpenAI Inc.",
        "Anthropic/Claude",
        "Microsoft <Azure>",
        "Google (Alphabet)",
        "Très Spécial Café"
    ]
    
    print("\nFilename sanitization:")
    for name in test_names:
        sanitized = sanitize_filename(name)
        print(f"  {name} -> {sanitized}")
    
    print("\nDuration formatting:")
    for seconds in [5.5, 75.3, 3661.2, 86401.5]:
        formatted = format_duration(seconds)
        print(f"  {seconds}s -> {formatted}")
    
    print("\nFile size formatting:")
    for size in [512, 1536, 1048576, 1073741824]:
        formatted = format_file_size(size)
        print(f"  {size} bytes -> {formatted}")
    
    print("\nUtilities test completed!")