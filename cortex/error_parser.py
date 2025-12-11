#!/usr/bin/env python3
"""
Error Message Parser
Analyzes installation errors and suggests fixes
"""

import re
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of installation errors"""
    DEPENDENCY_MISSING = "dependency_missing"
    PACKAGE_NOT_FOUND = "package_not_found"
    PERMISSION_DENIED = "permission_denied"
    DISK_SPACE = "disk_space"
    NETWORK_ERROR = "network_error"
    CONFLICT = "conflict"
    BROKEN_PACKAGE = "broken_package"
    GPG_KEY_ERROR = "gpg_key_error"
    REPOSITORY_ERROR = "repository_error"
    LOCK_ERROR = "lock_error"
    VERSION_CONFLICT = "version_conflict"
    CONFIGURATION_ERROR = "configuration_error"
    UNKNOWN = "unknown"


@dataclass
class ErrorMatch:
    """Matched error pattern"""
    category: ErrorCategory
    pattern: str
    confidence: float  # 0.0 to 1.0
    extracted_data: Dict[str, str]


@dataclass
class ErrorAnalysis:
    """Complete error analysis"""
    original_error: str
    matches: List[ErrorMatch]
    primary_category: ErrorCategory
    severity: str  # critical, high, medium, low
    is_fixable: bool
    suggested_fixes: List[str]
    automatic_fix_available: bool
    automatic_fix_command: Optional[str]


class ErrorParser:
    """Parses and analyzes installation error messages"""
    
    # Error patterns with regex and fix suggestions
    ERROR_PATTERNS = [
        # Dependency errors
        {
            'pattern': r'depends: (.+?) but it is not (going to be installed|installable)',
            'category': ErrorCategory.DEPENDENCY_MISSING,
            'confidence': 0.95,
            'fixes': [
                'Install the missing dependency: sudo apt-get install {package}',
                'Try with --fix-broken: sudo apt-get install -f',
                'Update package lists: sudo apt-get update'
            ],
            'auto_fix': 'sudo apt-get install -y {package}'
        },
        {
            'pattern': r'([a-z0-9\-]+) : Depends: (.+?) but',
            'category': ErrorCategory.DEPENDENCY_MISSING,
            'confidence': 0.9,
            'fixes': [
                'Install missing dependency: sudo apt-get install {dependency}',
                'Fix broken dependencies: sudo apt-get install -f'
            ],
            'auto_fix': 'sudo apt-get install -y {dependency}'
        },
        
        # Package not found
        {
            'pattern': r'Unable to locate package (.+?)(?:\s|$)',
            'category': ErrorCategory.PACKAGE_NOT_FOUND,
            'confidence': 0.95,
            'fixes': [
                'Update package lists: sudo apt-get update',
                'Check package name spelling',
                'Package may need a PPA: search for "{package} ubuntu ppa"',
                'Try searching: apt-cache search {package}'
            ],
            'auto_fix': 'sudo apt-get update'
        },
        {
            'pattern': r'E: Package \'(.+?)\' has no installation candidate',
            'category': ErrorCategory.PACKAGE_NOT_FOUND,
            'confidence': 0.95,
            'fixes': [
                'Enable universe repository: sudo add-apt-repository universe',
                'Update package lists: sudo apt-get update',
                'Package may require additional repository'
            ],
            'auto_fix': 'sudo add-apt-repository universe && sudo apt-get update'
        },
        
        # Permission errors
        {
            'pattern': r'Permission denied|Could not open lock file|Are you root',
            'category': ErrorCategory.PERMISSION_DENIED,
            'confidence': 0.9,
            'fixes': [
                'Run with sudo: sudo apt-get install {package}',
                'Check file permissions',
                'Ensure you have administrator access'
            ],
            'auto_fix': None  # Cannot auto-fix permission issues
        },
        
        # Disk space
        {
            'pattern': r'No space left on device|Insufficient space|not enough (free )?space',
            'category': ErrorCategory.DISK_SPACE,
            'confidence': 0.95,
            'fixes': [
                'Clean package cache: sudo apt-get clean',
                'Remove unused packages: sudo apt-get autoremove',
                'Check disk space: df -h',
                'Free up disk space before retrying'
            ],
            'auto_fix': 'sudo apt-get clean && sudo apt-get autoremove -y'
        },
        
        # Network errors
        {
            'pattern': r'Failed to fetch|Could not resolve|Connection (timed out|failed)|Network is unreachable',
            'category': ErrorCategory.NETWORK_ERROR,
            'confidence': 0.9,
            'fixes': [
                'Check internet connection',
                'Try again in a few moments',
                'Change DNS servers if persistent',
                'Check if repository is accessible: ping archive.ubuntu.com'
            ],
            'auto_fix': None  # Cannot auto-fix network
        },
        {
            'pattern': r'temporary failure resolving',
            'category': ErrorCategory.NETWORK_ERROR,
            'confidence': 0.85,
            'fixes': [
                'Check DNS configuration: cat /etc/resolv.conf',
                'Restart networking: sudo systemctl restart networking',
                'Try using Google DNS: 8.8.8.8'
            ],
            'auto_fix': None
        },
        
        # Conflicts
        {
            'pattern': r'Conflicts: (.+?)(?:\s|$)',
            'category': ErrorCategory.CONFLICT,
            'confidence': 0.9,
            'fixes': [
                'Remove conflicting package: sudo apt-get remove {conflicting_package}',
                'Choose alternative package',
                'Resolve conflict manually before proceeding'
            ],
            'auto_fix': None  # Requires user decision
        },
        {
            'pattern': r'([a-z0-9\-]+) conflicts with ([a-z0-9\-]+)',
            'category': ErrorCategory.CONFLICT,
            'confidence': 0.85,
            'fixes': [
                'Remove one of the conflicting packages',
                'Cannot install both {package1} and {package2}'
            ],
            'auto_fix': None
        },
        
        # Broken packages
        {
            'pattern': r'you have held broken packages|Some packages could not be installed',
            'category': ErrorCategory.BROKEN_PACKAGE,
            'confidence': 0.9,
            'fixes': [
                'Fix broken packages: sudo apt-get install -f',
                'Try: sudo dpkg --configure -a',
                'Clean and retry: sudo apt-get clean && sudo apt-get update'
            ],
            'auto_fix': 'sudo apt-get install -f -y'
        },
        {
            'pattern': r'dpkg was interrupted',
            'category': ErrorCategory.BROKEN_PACKAGE,
            'confidence': 0.95,
            'fixes': [
                'Reconfigure packages: sudo dpkg --configure -a',
                'Then retry installation'
            ],
            'auto_fix': 'sudo dpkg --configure -a'
        },
        
        # GPG/Key errors
        {
            'pattern': r'NO_PUBKEY ([A-F0-9]+)|GPG error|public key is not available',
            'category': ErrorCategory.GPG_KEY_ERROR,
            'confidence': 0.9,
            'fixes': [
                'Import missing key: sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys {key_id}',
                'Update package lists after importing key'
            ],
            'auto_fix': 'sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys {key_id}'
        },
        
        # Repository errors
        {
            'pattern': r'Release file .* is not valid|does not have a Release file',
            'category': ErrorCategory.REPOSITORY_ERROR,
            'confidence': 0.85,
            'fixes': [
                'Remove problematic repository',
                'Update package lists: sudo apt-get update',
                'Check repository configuration in /etc/apt/sources.list'
            ],
            'auto_fix': None
        },
        
        # Lock errors
        {
            'pattern': r'Could not get lock /var/lib/(dpkg|apt)/lock|Unable to acquire the dpkg frontend lock',
            'category': ErrorCategory.LOCK_ERROR,
            'confidence': 0.95,
            'fixes': [
                'Wait for other package manager to finish',
                'Kill stuck process: sudo killall apt apt-get',
                'Remove lock file: sudo rm /var/lib/apt/lists/lock',
                'Then retry: sudo dpkg --configure -a'
            ],
            'auto_fix': 'sudo killall apt apt-get; sudo rm /var/lib/apt/lists/lock /var/lib/dpkg/lock /var/lib/dpkg/lock-frontend; sudo dpkg --configure -a'
        },
        
        # Version conflicts
        {
            'pattern': r'version \'(.+?)\' .* but \'(.+?)\' is to be installed',
            'category': ErrorCategory.VERSION_CONFLICT,
            'confidence': 0.85,
            'fixes': [
                'Specify exact version: sudo apt-get install {package}={version}',
                'Try upgrading all packages: sudo apt-get upgrade',
                'Check for held packages: apt-mark showhold'
            ],
            'auto_fix': None
        },
        
        # Configuration errors
        {
            'pattern': r'configuration file|debconf',
            'category': ErrorCategory.CONFIGURATION_ERROR,
            'confidence': 0.7,
            'fixes': [
                'Reconfigure package: sudo dpkg-reconfigure {package}',
                'Use non-interactive mode: DEBIAN_FRONTEND=noninteractive',
                'Check configuration in /etc/'
            ],
            'auto_fix': None
        }
    ]
    
    def __init__(self):
        self.compiled_patterns = []
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for performance"""
        for pattern_def in self.ERROR_PATTERNS:
            self.compiled_patterns.append({
                'regex': re.compile(pattern_def['pattern'], re.IGNORECASE),
                'category': pattern_def['category'],
                'confidence': pattern_def['confidence'],
                'fixes': pattern_def['fixes'],
                'auto_fix': pattern_def.get('auto_fix')
            })
    
    def parse_error(self, error_message: str) -> ErrorAnalysis:
        """
        Parse error message and provide analysis
        
        Args:
            error_message: Raw error output from installation
            
        Returns:
            ErrorAnalysis with categorization and fix suggestions
        """
        matches = []
        
        # Try to match against all patterns
        for pattern_def in self.compiled_patterns:
            regex_match = pattern_def['regex'].search(error_message)
            
            if regex_match:
                # Extract data from regex groups
                extracted_data = {}
                groups = regex_match.groups() if regex_match else ()
                if groups:
                    for i, group in enumerate(groups):
                        if group is not None:
                            extracted_data[f'group_{i}'] = group
                    
                    # Try to identify specific data types
                    first_group = groups[0] if len(groups) > 0 and groups[0] is not None else None
                    fixes_text = " ".join(pattern_def['fixes']).lower()
                    if first_group:
                        if 'package' in fixes_text:
                            extracted_data.setdefault('package', first_group)
                        if 'dependency' in fixes_text:
                            extracted_data.setdefault('dependency', first_group)
                    
                    # Pattern-specific extractions
                    try:
                        pattern_text = pattern_def['regex'].pattern
                    except AttributeError:
                        pattern_text = ""
                    
                    if pattern_text == r'([a-z0-9\-]+) : Depends: (.+?) but' and len(groups) >= 2:
                        extracted_data['package'] = groups[0]
                        extracted_data['dependency'] = groups[1]
                    if pattern_text == r'([a-z0-9\-]+) conflicts with ([a-z0-9\-]+)' and len(groups) >= 2:
                        extracted_data['package1'] = groups[0]
                        extracted_data['package2'] = groups[1]
                    
                    if pattern_def['category'] == ErrorCategory.GPG_KEY_ERROR:
                        # Prefer explicit capture if available
                        if first_group:
                            extracted_data['key_id'] = first_group
                        else:
                            # Fallback: search the entire error_message for a likely key id
                            key_match = re.search(r'NO_PUBKEY\s+([A-F0-9]{8,40})|recv-keys\s+([A-F0-9]{8,40})|([A-F0-9]{8,16})', error_message, re.IGNORECASE)
                            if key_match:
                                for g in key_match.groups():
                                    if g:
                                        extracted_data['key_id'] = g
                                        break
                
                match = ErrorMatch(
                    category=pattern_def['category'],
                    pattern=pattern_def['regex'].pattern,
                    confidence=pattern_def['confidence'],
                    extracted_data=extracted_data
                )
                matches.append(match)
        
        # Determine primary category (highest confidence match)
        if matches:
            primary_match = max(matches, key=lambda m: m.confidence)
            primary_category = primary_match.category
        else:
            primary_category = ErrorCategory.UNKNOWN
        
        # Determine severity
        severity = self._calculate_severity(primary_category)
        
        # Check if fixable
        is_fixable = self._is_fixable(primary_category)
        
        # Generate fix suggestions
        suggested_fixes = self._generate_fixes(matches, error_message)
        
        # Check for automatic fix
        auto_fix_available, auto_fix_cmd = self._get_automatic_fix(matches)
        
        analysis = ErrorAnalysis(
            original_error=error_message,
            matches=matches,
            primary_category=primary_category,
            severity=severity,
            is_fixable=is_fixable,
            suggested_fixes=suggested_fixes,
            automatic_fix_available=auto_fix_available,
            automatic_fix_command=auto_fix_cmd
        )
        
        return analysis
    
    def _calculate_severity(self, category: ErrorCategory) -> str:
        """Calculate error severity"""
        critical_categories = [
            ErrorCategory.DISK_SPACE,
            ErrorCategory.BROKEN_PACKAGE,
            ErrorCategory.PERMISSION_DENIED
        ]
        
        high_categories = [
            ErrorCategory.DEPENDENCY_MISSING,
            ErrorCategory.CONFLICT,
            ErrorCategory.LOCK_ERROR
        ]
        
        if category in critical_categories:
            return "critical"
        elif category in high_categories:
            return "high"
        elif category == ErrorCategory.UNKNOWN:
            return "unknown"
        else:
            return "medium"
    
    def _is_fixable(self, category: ErrorCategory) -> bool:
        """Determine if error is fixable"""
        unfixable_categories = [
            ErrorCategory.DISK_SPACE,  # Requires manual intervention
            ErrorCategory.PERMISSION_DENIED  # Requires sudo/root
        ]
        
        return category not in unfixable_categories
    
    def _generate_fixes(self, matches: List[ErrorMatch], error_message: str) -> List[str]:
        """Generate fix suggestions from matches"""
        fixes = []
        
        for match in matches:
            # Find the compiled pattern definition
            for pattern_def in self.compiled_patterns:
                if pattern_def['category'] == match.category and pattern_def['regex'].pattern == match.pattern:
                    for fix_template in pattern_def['fixes']:
                        # Replace placeholders with extracted data
                        fix = fix_template
                        for key, value in match.extracted_data.items():
                            if value is None:
                                continue
                            placeholder = f'{{{key}}}'
                            if placeholder in fix:
                                fix = fix.replace(placeholder, value)
                        
                        # Skip fixes that still have unresolved placeholders
                        if '{' in fix and '}' in fix:
                            continue
                        
                        # Add fix if not already present
                        if fix not in fixes:
                            fixes.append(fix)
                    break
        
        # Add generic fixes if no specific ones found
        if not fixes:
            fixes = [
                'Update package lists: sudo apt-get update',
                'Fix broken dependencies: sudo apt-get install -f',
                'Try with --fix-broken flag',
                'Check system logs: journalctl -xe'
            ]
        
        return fixes[:5]  # Limit to top 5 suggestions
    
    def _get_automatic_fix(self, matches: List[ErrorMatch]) -> Tuple[bool, Optional[str]]:
        """Get automatic fix command if available"""
        for match in matches:
            # Find pattern with auto_fix
            for pattern_def in self.compiled_patterns:
                if pattern_def['category'] == match.category and pattern_def['regex'].pattern == match.pattern:
                    auto_fix = pattern_def.get('auto_fix')
                    if auto_fix:
                        # Replace placeholders
                        for key, value in match.extracted_data.items():
                            if value is None:
                                continue
                            placeholder = f'{{{key}}}'
                            if placeholder in auto_fix:
                                auto_fix = auto_fix.replace(placeholder, value)
                        return (True, auto_fix)
        
        return (False, None)
    
    def print_analysis(self, analysis: ErrorAnalysis) -> None:
        """Print formatted error analysis"""
        print("\n" + "="*60)
        print("ERROR ANALYSIS")
        print("="*60)
        
        print(f"\n📋 Category: {analysis.primary_category.value}")
        print(f"⚠️  Severity: {analysis.severity.upper()}")
        print(f"🔧 Fixable: {'Yes' if analysis.is_fixable else 'No'}")
        
        if analysis.matches:
            print(f"\n✅ Matched {len(analysis.matches)} error pattern(s)")
            for i, match in enumerate(analysis.matches, 1):
                print(f"   {i}. {match.category.value} (confidence: {match.confidence:.0%})")
        
        print(f"\n💡 Suggested Fixes:")
        for i, fix in enumerate(analysis.suggested_fixes, 1):
            print(f"   {i}. {fix}")
        
        if analysis.automatic_fix_available:
            print(f"\n🤖 Automatic Fix Available:")
            print(f"   {analysis.automatic_fix_command}")
        
        print("\n" + "="*60)
    
    def export_analysis_json(self, analysis: ErrorAnalysis, filepath: str) -> None:
        """Export analysis to JSON"""
        analysis_dict = {
            'original_error': analysis.original_error,
            'primary_category': analysis.primary_category.value,
            'severity': analysis.severity,
            'is_fixable': analysis.is_fixable,
            'suggested_fixes': analysis.suggested_fixes,
            'automatic_fix_available': analysis.automatic_fix_available,
            'automatic_fix_command': analysis.automatic_fix_command,
            'matches': [
                {
                    'category': m.category.value,
                    'confidence': m.confidence,
                    'extracted_data': m.extracted_data
                }
                for m in analysis.matches
            ]
        }
        
        with open(filepath, 'w') as f:
            json.dump(analysis_dict, f, indent=2)
        
        logger.info(f"Analysis exported to {filepath}")


# CLI Interface
if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Parse installation error messages"
    )
    parser.add_argument(
        'error',
        nargs='?',
        help='Error message to parse (or pipe via stdin)'
    )
    parser.add_argument(
        '--file',
        help='Read error from file'
    )
    parser.add_argument(
        '--export',
        help='Export analysis to JSON file'
    )
    parser.add_argument(
        '--auto-fix',
        action='store_true',
        help='Show only automatic fix command'
    )
    
    args = parser.parse_args()
    
    # Get error message
    error_message = None
    if args.file:
        with open(args.file, 'r') as f:
            error_message = f.read()
    elif args.error:
        error_message = args.error
    elif not sys.stdin.isatty():
        error_message = sys.stdin.read()
    else:
        parser.print_help()
        sys.exit(1)
    
    # Parse error
    parser_obj = ErrorParser()
    analysis = parser_obj.parse_error(error_message)
    
    if args.auto_fix:
        if analysis.automatic_fix_available:
            print(analysis.automatic_fix_command)
        else:
            print("No automatic fix available")
            sys.exit(1)
    else:
        parser_obj.print_analysis(analysis)
    
    # Export if requested
    if args.export:
        parser_obj.export_analysis_json(analysis, args.export)
