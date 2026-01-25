"""
File Classifier for StoragePilot
=================================
AI-powered file classification using semantic analysis.
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict


@dataclass
class FileClassification:
    """Classification result for a file."""
    path: str
    filename: str
    extension: str
    category: str
    subcategory: str
    confidence: float
    suggested_destination: str
    action: str  # move, delete, keep, review
    reason: str
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None


class FileClassifier:
    """AI-powered file classifier."""
    
    # Extension to category mapping
    CATEGORY_MAP = {
        # Documents
        ".pdf": ("documents", "general"),
        ".doc": ("documents", "word"),
        ".docx": ("documents", "word"),
        ".txt": ("documents", "text"),
        ".md": ("documents", "markdown"),
        ".rtf": ("documents", "text"),
        ".odt": ("documents", "text"),
        ".xls": ("documents", "spreadsheet"),
        ".xlsx": ("documents", "spreadsheet"),
        ".csv": ("data", "tabular"),
        ".ppt": ("documents", "presentation"),
        ".pptx": ("documents", "presentation"),
        
        # Images
        ".jpg": ("images", "photo"),
        ".jpeg": ("images", "photo"),
        ".png": ("images", "graphic"),
        ".gif": ("images", "animated"),
        ".webp": ("images", "web"),
        ".svg": ("images", "vector"),
        ".bmp": ("images", "bitmap"),
        ".ico": ("images", "icon"),
        ".heic": ("images", "photo"),
        ".raw": ("images", "raw"),
        
        # Videos
        ".mp4": ("videos", "general"),
        ".mov": ("videos", "general"),
        ".avi": ("videos", "general"),
        ".mkv": ("videos", "general"),
        ".wmv": ("videos", "general"),
        ".webm": ("videos", "web"),
        
        # Audio
        ".mp3": ("audio", "music"),
        ".wav": ("audio", "raw"),
        ".flac": ("audio", "lossless"),
        ".aac": ("audio", "music"),
        ".ogg": ("audio", "music"),
        ".m4a": ("audio", "music"),
        
        # Code
        ".py": ("code", "python"),
        ".js": ("code", "javascript"),
        ".ts": ("code", "typescript"),
        ".jsx": ("code", "react"),
        ".tsx": ("code", "react"),
        ".java": ("code", "java"),
        ".go": ("code", "golang"),
        ".rs": ("code", "rust"),
        ".cpp": ("code", "cpp"),
        ".c": ("code", "c"),
        ".h": ("code", "header"),
        ".cs": ("code", "csharp"),
        ".rb": ("code", "ruby"),
        ".php": ("code", "php"),
        ".swift": ("code", "swift"),
        ".kt": ("code", "kotlin"),
        ".sh": ("code", "shell"),
        ".bash": ("code", "shell"),
        ".zsh": ("code", "shell"),
        ".sql": ("code", "sql"),
        ".html": ("code", "web"),
        ".css": ("code", "web"),
        ".scss": ("code", "web"),
        ".less": ("code", "web"),
        
        # Data
        ".json": ("data", "json"),
        ".xml": ("data", "xml"),
        ".yaml": ("data", "yaml"),
        ".yml": ("data", "yaml"),
        ".toml": ("data", "config"),
        ".ini": ("data", "config"),
        ".env": ("data", "config"),
        ".db": ("data", "database"),
        ".sqlite": ("data", "database"),
        ".sqlite3": ("data", "database"),
        
        # ML Models
        ".h5": ("models", "keras"),
        ".pt": ("models", "pytorch"),
        ".pth": ("models", "pytorch"),
        ".onnx": ("models", "onnx"),
        ".pkl": ("models", "pickle"),
        ".joblib": ("models", "sklearn"),
        ".safetensors": ("models", "safetensors"),
        ".ckpt": ("models", "checkpoint"),
        
        # Archives
        ".zip": ("archives", "zip"),
        ".tar": ("archives", "tar"),
        ".gz": ("archives", "gzip"),
        ".tar.gz": ("archives", "targz"),
        ".tgz": ("archives", "targz"),
        ".rar": ("archives", "rar"),
        ".7z": ("archives", "7zip"),
        ".bz2": ("archives", "bzip2"),
        
        # Installers
        ".dmg": ("installers", "macos"),
        ".pkg": ("installers", "macos"),
        ".exe": ("installers", "windows"),
        ".msi": ("installers", "windows"),
        ".deb": ("installers", "linux"),
        ".rpm": ("installers", "linux"),
        ".appimage": ("installers", "linux"),
        
        # System
        ".log": ("system", "logs"),
        ".tmp": ("system", "temp"),
        ".bak": ("system", "backup"),
        ".swp": ("system", "swap"),
        ".DS_Store": ("system", "macos"),
    }
    
    # Keywords for document subcategorization
    DOCUMENT_KEYWORDS = {
        "invoice": ("finance", "invoices"),
        "receipt": ("finance", "receipts"),
        "bill": ("finance", "bills"),
        "payment": ("finance", "payments"),
        "tax": ("finance", "tax"),
        "w2": ("finance", "tax"),
        "1099": ("finance", "tax"),
        "contract": ("legal", "contracts"),
        "agreement": ("legal", "agreements"),
        "nda": ("legal", "nda"),
        "terms": ("legal", "terms"),
        "resume": ("career", "resumes"),
        "cv": ("career", "resumes"),
        "cover_letter": ("career", "cover_letters"),
        "meeting": ("work", "meetings"),
        "notes": ("work", "notes"),
        "presentation": ("work", "presentations"),
        "report": ("work", "reports"),
        "proposal": ("work", "proposals"),
        "screenshot": ("images", "screenshots"),
        "screen_shot": ("images", "screenshots"),
        "capture": ("images", "screenshots"),
    }
    
    # Patterns for screenshots
    SCREENSHOT_PATTERNS = [
        r"Screenshot.*",
        r"Screen Shot.*",
        r"Capture.*",
        r"Schermata.*",  # Italian
        r"Captura.*",  # Spanish
        r"Bildschirmfoto.*",  # German
    ]
    
    # Patterns for photos
    PHOTO_PATTERNS = [
        r"IMG_\d+",
        r"DSC_\d+",
        r"DCIM.*",
        r"Photo_\d+",
        r"PXL_\d+",  # Pixel phones
        r"\d{8}_\d{6}",  # Date-time format
    ]
    
    # Patterns for version files
    VERSION_PATTERNS = [
        r"(.+)_v(\d+)",
        r"(.+)_version(\d+)",
        r"(.+)_final",
        r"(.+)_FINAL",
        r"(.+)_copy",
        r"(.+)_Copy",
        r"(.+)\s*\((\d+)\)",  # file (1), file (2)
        r"(.+)_(\d{8})",  # file_20240115
    ]
    
    def __init__(self, base_destinations: Optional[Dict[str, str]] = None):
        """Initialize classifier with destination paths."""
        self.base_destinations = base_destinations or {
            "documents": "~/Documents/Sorted",
            "images": "~/Pictures/Sorted",
            "videos": "~/Videos/Sorted",
            "audio": "~/Music/Sorted",
            "code": "~/workspace/code_downloads",
            "data": "~/workspace/data",
            "models": "~/workspace/models",
            "archives": "~/Downloads/Archives",
            "installers": "~/.Trash",
            "system": "~/.Trash",
        }
        
        # Cache for duplicate detection
        self.seen_hashes: Dict[str, str] = {}
        self.seen_filenames: Dict[str, List[str]] = defaultdict(list)
    
    def classify_file(self, file_path: str, file_hash: Optional[str] = None) -> FileClassification:
        """Classify a single file."""
        path = Path(file_path)
        filename = path.name
        extension = path.suffix.lower()
        
        # Handle special extensions
        if filename.endswith('.tar.gz'):
            extension = '.tar.gz'
        elif filename.endswith('.tar.bz2'):
            extension = '.tar.bz2'
        
        # Get base category from extension
        category, subcategory = self.CATEGORY_MAP.get(extension, ("unknown", "unknown"))
        confidence = 0.9 if category != "unknown" else 0.3
        
        # Check for screenshots
        if self._matches_patterns(filename, self.SCREENSHOT_PATTERNS):
            category = "images"
            subcategory = "screenshots"
            confidence = 0.95
        
        # Check for photos
        elif self._matches_patterns(filename, self.PHOTO_PATTERNS):
            category = "images"
            subcategory = "photos"
            confidence = 0.95
        
        # Semantic analysis for documents
        elif category == "documents":
            detected = self._analyze_document_name(filename)
            if detected:
                category, subcategory = detected
                confidence = 0.85
        
        # Check for duplicates
        is_duplicate = False
        duplicate_of = None
        
        if file_hash:
            if file_hash in self.seen_hashes:
                is_duplicate = True
                duplicate_of = self.seen_hashes[file_hash]
            else:
                self.seen_hashes[file_hash] = file_path
        
        # Check for version duplicates
        version_match = self._check_version_pattern(filename)
        if version_match:
            base_name = version_match[0]
            if base_name in self.seen_filenames:
                is_duplicate = True
                duplicate_of = f"Version of: {self.seen_filenames[base_name][0]}"
            self.seen_filenames[base_name].append(file_path)
        
        # Determine action
        action = self._determine_action(category, subcategory, is_duplicate)
        
        # Build destination path
        suggested_destination = self._build_destination(
            category, subcategory, filename
        )
        
        # Build reason
        reason = self._build_reason(category, subcategory, is_duplicate, duplicate_of)
        
        return FileClassification(
            path=file_path,
            filename=filename,
            extension=extension,
            category=category,
            subcategory=subcategory,
            confidence=confidence,
            suggested_destination=suggested_destination,
            action=action,
            reason=reason,
            is_duplicate=is_duplicate,
            duplicate_of=duplicate_of
        )
    
    def _matches_patterns(self, text: str, patterns: List[str]) -> bool:
        """Check if text matches any of the patterns."""
        for pattern in patterns:
            if re.match(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _analyze_document_name(self, filename: str) -> Optional[Tuple[str, str]]:
        """Analyze document filename for semantic classification."""
        filename_lower = filename.lower()
        
        for keyword, (cat, subcat) in self.DOCUMENT_KEYWORDS.items():
            if keyword in filename_lower:
                return (cat if cat != "images" else "documents", subcat)
        
        return None
    
    def _check_version_pattern(self, filename: str) -> Optional[Tuple[str, str]]:
        """Check if filename matches version pattern."""
        base_name = Path(filename).stem
        
        for pattern in self.VERSION_PATTERNS:
            match = re.match(pattern, base_name, re.IGNORECASE)
            if match:
                return match.groups()
        
        return None
    
    def _determine_action(self, category: str, subcategory: str, is_duplicate: bool) -> str:
        """Determine what action to take for the file."""
        if is_duplicate:
            return "review"  # Duplicates need review
        
        if category == "installers":
            return "delete"  # Installers can be re-downloaded
        
        if category == "system":
            return "delete"  # System files like .DS_Store can be deleted
        
        if category == "unknown":
            return "review"  # Unknown files need review
        
        return "move"  # Default action is to move to organized location
    
    def _build_destination(self, category: str, subcategory: str, filename: str) -> str:
        """Build the destination path for a file."""
        base = self.base_destinations.get(category, "~/Downloads/Sorted/Other")
        
        # Add subcategory folder
        if subcategory and subcategory != "general":
            dest = os.path.join(base, subcategory.capitalize())
        else:
            dest = base
        
        # Add date subfolder for photos
        if subcategory == "photos":
            now = datetime.now()
            dest = os.path.join(dest, str(now.year), f"{now.month:02d}")
        
        return os.path.join(dest, filename)
    
    def _build_reason(
        self,
        category: str,
        subcategory: str,
        is_duplicate: bool,
        duplicate_of: Optional[str]
    ) -> str:
        """Build explanation for the classification."""
        reasons = []
        
        if is_duplicate:
            reasons.append(f"Duplicate detected: {duplicate_of}")
        
        reasons.append(f"Classified as {category}/{subcategory}")
        
        if category == "installers":
            reasons.append("Installers can be re-downloaded when needed")
        
        return "; ".join(reasons)
    
    def classify_directory(self, directory_path: str) -> List[FileClassification]:
        """Classify all files in a directory."""
        directory = Path(directory_path).expanduser()
        classifications = []
        
        for file_path in directory.iterdir():
            if file_path.is_file() and not file_path.name.startswith('.'):
                try:
                    classification = self.classify_file(str(file_path))
                    classifications.append(classification)
                except Exception as e:
                    print(f"Error classifying {file_path}: {e}")
        
        return classifications
    
    def generate_organization_plan(
        self,
        classifications: List[FileClassification]
    ) -> Dict[str, List[Dict]]:
        """Generate an organization plan from classifications."""
        plan = {
            "move": [],
            "delete": [],
            "review": [],
            "keep": []
        }
        
        for c in classifications:
            entry = {
                "source": c.path,
                "destination": c.suggested_destination,
                "category": c.category,
                "subcategory": c.subcategory,
                "reason": c.reason,
                "confidence": c.confidence
            }
            
            if c.is_duplicate:
                entry["duplicate_of"] = c.duplicate_of
            
            plan[c.action].append(entry)
        
        return plan


# CrewAI Tool wrapper
from crewai.tools import tool


@tool("classify_files")
def classify_files(directory_path: str) -> str:
    """
    Classify all files in a directory and suggest organization.
    
    Args:
        directory_path: Path to the directory to classify (e.g., ~/Downloads)
    
    Returns:
        JSON string with classification results and organization plan
    """
    classifier = FileClassifier()
    classifications = classifier.classify_directory(directory_path)
    plan = classifier.generate_organization_plan(classifications)
    
    result = {
        "total_files": len(classifications),
        "by_action": {
            "move": len(plan["move"]),
            "delete": len(plan["delete"]),
            "review": len(plan["review"]),
            "keep": len(plan["keep"])
        },
        "plan": plan
    }
    
    return json.dumps(result, indent=2)


@tool("classify_single_file")
def classify_single_file(file_path: str) -> str:
    """
    Classify a single file and suggest action.
    
    Args:
        file_path: Path to the file to classify
    
    Returns:
        JSON string with classification result
    """
    classifier = FileClassifier()
    classification = classifier.classify_file(file_path)
    
    return json.dumps({
        "path": classification.path,
        "filename": classification.filename,
        "category": classification.category,
        "subcategory": classification.subcategory,
        "confidence": classification.confidence,
        "action": classification.action,
        "destination": classification.suggested_destination,
        "reason": classification.reason,
        "is_duplicate": classification.is_duplicate,
        "duplicate_of": classification.duplicate_of
    }, indent=2)


@tool("detect_duplicates")
def detect_duplicates(directory_path: str) -> str:
    """
    Detect duplicate files in a directory.
    
    Args:
        directory_path: Path to the directory to scan for duplicates
    
    Returns:
        JSON string with duplicate file groups
    """
    from collections import defaultdict
    import hashlib
    
    directory = Path(directory_path).expanduser()
    hash_groups = defaultdict(list)
    
    for file_path in directory.iterdir():
        if file_path.is_file() and not file_path.name.startswith('.'):
            try:
                # Calculate hash
                hasher = hashlib.md5()
                with open(file_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(65536), b''):
                        hasher.update(chunk)
                file_hash = hasher.hexdigest()
                
                hash_groups[file_hash].append({
                    "path": str(file_path),
                    "name": file_path.name,
                    "size": file_path.stat().st_size
                })
            except Exception:
                pass
    
    # Filter to only groups with duplicates
    duplicates = {k: v for k, v in hash_groups.items() if len(v) > 1}
    
    return json.dumps({
        "total_duplicate_groups": len(duplicates),
        "groups": list(duplicates.values())
    }, indent=2)
