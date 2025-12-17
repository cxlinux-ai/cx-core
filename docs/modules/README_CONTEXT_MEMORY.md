# AI Context Memory System

## Overview

The **AI Context Memory System** is a sophisticated learning and pattern recognition engine for Cortex Linux. It provides persistent memory that enables the AI to learn from user interactions, remember preferences, detect patterns, and generate intelligent suggestions.

## Features

### 🧠 Core Capabilities

- **Persistent Memory Storage**: Records all user interactions with full context
- **Pattern Recognition**: Automatically detects recurring behaviors and workflows
- **Intelligent Suggestions**: Generates optimization recommendations based on history
- **Preference Management**: Stores and retrieves user preferences
- **Privacy-Preserving**: Anonymized pattern matching protects sensitive data
- **Export/Import**: Full data portability with JSON export

### 📊 Memory Categories

The system tracks interactions across multiple categories:

- **Package**: Package installations and management
- **Command**: Shell command executions
- **Pattern**: Detected behavioral patterns
- **Preference**: User settings and preferences
- **Error**: Error occurrences and resolutions

## Installation

```bash
# Copy the module to your Cortex Linux installation
cp context_memory.py /opt/cortex/lib/

# Or install as a Python package
pip install -e .
```

## Usage

### Basic Usage

```python
from context_memory import ContextMemory, MemoryEntry

# Initialize the memory system
memory = ContextMemory()

# Record an interaction
entry = MemoryEntry(
    category="package",
    context="User wants to install Docker for containerization",
    action="apt install docker-ce docker-compose",
    result="Successfully installed Docker 24.0.5",
    success=True,
    metadata={"packages": ["docker-ce", "docker-compose"], "version": "24.0.5"}
)

entry_id = memory.record_interaction(entry)
print(f"Recorded interaction #{entry_id}")
```

### Pattern Detection

```python
# Get detected patterns (minimum 70% confidence)
patterns = memory.get_patterns(min_confidence=0.7)

for pattern in patterns:
    print(f"Pattern: {pattern.description}")
    print(f"  Frequency: {pattern.frequency}")
    print(f"  Confidence: {pattern.confidence:.0%}")
    print(f"  Actions: {', '.join(pattern.actions)}")
```

### Intelligent Suggestions

```python
# Generate suggestions based on memory and patterns
suggestions = memory.generate_suggestions()

for suggestion in suggestions:
    print(f"[{suggestion.suggestion_type}] {suggestion.title}")
    print(f"  {suggestion.description}")
    print(f"  Confidence: {suggestion.confidence:.0%}")
```

### Preference Management

```python
# Store preferences
memory.set_preference("default_editor", "vim")
memory.set_preference("auto_update", True)
memory.set_preference("theme", {"name": "dark", "accent": "#007acc"})

# Retrieve preferences
editor = memory.get_preference("default_editor")
update = memory.get_preference("auto_update")
theme = memory.get_preference("theme")

# Get preference with default
shell = memory.get_preference("default_shell", default="/bin/bash")
```

### Finding Similar Interactions

```python
# Search for similar past interactions
similar = memory.get_similar_interactions(
    context="Docker installation problems",
    limit=5
)

for entry in similar:
    print(f"{entry.timestamp}: {entry.action}")
    print(f"  Result: {entry.result}")
    print(f"  Success: {entry.success}")
```

### Statistics and Analytics

```python
# Get memory system statistics
stats = memory.get_statistics()

print(f"Total Entries: {stats['total_entries']}")
print(f"Success Rate: {stats['success_rate']:.1f}%")
print(f"Total Patterns: {stats['total_patterns']}")
print(f"Active Suggestions: {stats['active_suggestions']}")
print(f"Recent Activity (7 days): {stats['recent_activity']}")

# Category breakdown
print("\nBy Category:")
for category, count in stats['by_category'].items():
    print(f"  {category}: {count}")
```

### Export Memory Data

```python
# Export all memory data to JSON
memory.export_memory(
    output_path="/backup/cortex_memory_export.json",
    include_dismissed=False  # Exclude dismissed suggestions
)
```

## Data Model

### MemoryEntry

Represents a single user interaction:

```python
@dataclass
class MemoryEntry:
    id: Optional[int] = None
    timestamp: str = ""              # ISO format datetime
    category: str = ""               # package, command, pattern, etc.
    context: str = ""                # What the user was trying to do
    action: str = ""                 # What action was taken
    result: str = ""                 # Outcome of the action
    success: bool = True             # Whether it succeeded
    confidence: float = 1.0          # Confidence in the result (0-1)
    frequency: int = 1               # How many times this occurred
    metadata: Dict[str, Any] = None  # Additional structured data
```

### Pattern

Represents a detected behavioral pattern:

```python
@dataclass
class Pattern:
    pattern_id: str                  # Unique identifier
    pattern_type: str                # installation, configuration, workflow
    description: str                 # Human-readable description
    frequency: int                   # How many times seen
    last_seen: str                   # Last occurrence timestamp
    confidence: float                # Pattern confidence (0-1)
    actions: List[str]               # Actions in the pattern
    context: Dict[str, Any]          # Additional context
```

### Suggestion

Represents an AI-generated suggestion:

```python
@dataclass
class Suggestion:
    suggestion_id: str               # Unique identifier
    suggestion_type: str             # optimization, alternative, warning
    title: str                       # Short title
    description: str                 # Detailed description
    confidence: float                # Confidence in suggestion (0-1)
    based_on: List[str]              # Memory entry IDs it's based on
    created_at: str                  # Creation timestamp
```

## Database Schema

The system uses SQLite with the following tables:

### memory_entries
Stores all user interactions with full context.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Unique entry ID |
| timestamp | TEXT | When the interaction occurred |
| category | TEXT | Category (package, command, etc.) |
| context | TEXT | What the user was trying to do |
| action | TEXT | What action was taken |
| result | TEXT | Outcome of the action |
| success | BOOLEAN | Whether it succeeded |
| confidence | REAL | Confidence in the result |
| frequency | INTEGER | Occurrence count |
| metadata | TEXT (JSON) | Additional structured data |

### patterns
Stores detected behavioral patterns.

| Column | Type | Description |
|--------|------|-------------|
| pattern_id | TEXT PRIMARY KEY | Unique pattern identifier |
| pattern_type | TEXT | Type of pattern |
| description | TEXT | Human-readable description |
| frequency | INTEGER | How many times seen |
| last_seen | TEXT | Last occurrence |
| confidence | REAL | Pattern confidence |
| actions | TEXT (JSON) | Actions in pattern |
| context | TEXT (JSON) | Pattern context |

### suggestions
Stores AI-generated suggestions.

| Column | Type | Description |
|--------|------|-------------|
| suggestion_id | TEXT PRIMARY KEY | Unique suggestion ID |
| suggestion_type | TEXT | Type of suggestion |
| title | TEXT | Short title |
| description | TEXT | Detailed description |
| confidence | REAL | Confidence score |
| based_on | TEXT (JSON) | Source memory entry IDs |
| created_at | TEXT | Creation timestamp |
| dismissed | BOOLEAN | Whether user dismissed it |

### preferences
Stores user preferences.

| Column | Type | Description |
|--------|------|-------------|
| key | TEXT PRIMARY KEY | Preference key |
| value | TEXT (JSON) | Preference value |
| category | TEXT | Preference category |
| updated_at | TEXT | Last update timestamp |

## Suggestion Types

### Optimization Suggestions
Generated when the system detects repeated actions that could be automated or optimized.

**Example:**
```
Title: Frequent Installation: docker-ce
Description: You've installed docker-ce 5 times recently. 
             Consider adding it to your default setup script.
Confidence: 100%
```

### Alternative Suggestions
Generated when an action fails and the system knows successful alternatives.

**Example:**
```
Title: Alternative to: pip install broken-package
Description: Based on your history, try: pip install working-package
Confidence: 70%
```

### Proactive Suggestions
Generated when high-confidence patterns indicate automation opportunities.

**Example:**
```
Title: Automate: Recurring pattern: configure nginx ssl
Description: You frequently do this (8 times). Would you like to automate it?
Confidence: 80%
```

## Configuration

### Database Location

Default: `~/.cortex/context_memory.db`

Change by passing a custom path:

```python
memory = ContextMemory(db_path="/custom/path/memory.db")
```

### Pattern Detection Thresholds

Patterns are detected when:
- **Minimum frequency**: 3 occurrences within 30 days
- **Confidence calculation**: `min(1.0, frequency / 10.0)`
- **Retrieval threshold**: Default 0.5 (50% confidence)

### Suggestion Generation

Suggestions are generated based on:
- **Optimization**: 3+ identical actions within 7 days
- **Alternatives**: Failed actions with successful similar actions
- **Proactive**: Patterns with 80%+ confidence and 5+ frequency

## Privacy & Security

### Data Anonymization
- Pattern matching uses keywords, not full text
- No personally identifiable information (PII) stored by default
- Metadata is user-controlled

### Local Storage
- All data stored locally in SQLite
- No external transmission
- User has full control over data

### Data Export
- Complete data portability via JSON export
- User can audit all stored information
- Easy deletion of specific entries or categories

## Performance Considerations

### Database Size
- Typical usage: ~1-10 MB per year
- Automatic indexing on frequently queried columns
- Periodic cleanup recommended for large datasets

### Query Optimization
- Indexes on: category, timestamp, pattern_type, suggestion_type
- Limit queries use pagination
- Recent activity queries optimized with date filters

### Memory Footprint
- Minimal RAM usage (~5-10 MB)
- SQLite connection pooling
- Lazy loading of large result sets

## Integration with Cortex Linux

### LLM Integration
```python
from cortex.llm import CortexLLM
from context_memory import ContextMemory

llm = CortexLLM()
memory = ContextMemory()

# Get context for AI decision-making
context = memory.get_similar_interactions("install cuda", limit=5)
patterns = memory.get_patterns(pattern_type="package")

# Use in prompt
prompt = f"""
Previous similar installations: {context}
Detected patterns: {patterns}

User wants to: install cuda drivers
What should I recommend?
"""

response = llm.generate(prompt)
```

### Package Manager Wrapper
```python
from cortex.package_manager import PackageManager
from context_memory import ContextMemory, MemoryEntry

pm = PackageManager()
memory = ContextMemory()

def install_package(package_name):
    # Record the attempt
    entry = MemoryEntry(
        category="package",
        context=f"User requested: {package_name}",
        action=f"apt install {package_name}",
        success=False  # Will update later
    )
    
    # Attempt installation
    result = pm.install(package_name)
    
    # Update memory
    entry.success = result.success
    entry.result = result.message
    entry.metadata = result.metadata
    
    memory.record_interaction(entry)
    
    # Check for suggestions
    if not result.success:
        suggestions = memory.generate_suggestions(context=package_name)
        for suggestion in suggestions:
            if suggestion.suggestion_type == "alternative":
                print(f"💡 Suggestion: {suggestion.description}")
    
    return result
```

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
python test_context_memory.py

# Run with verbose output
python test_context_memory.py -v

# Run specific test class
python -m unittest test_context_memory.TestContextMemory

# Run specific test
python -m unittest test_context_memory.TestContextMemory.test_record_interaction
```

### Test Coverage

The test suite includes:

- ✅ Database initialization and schema
- ✅ Memory entry recording and retrieval
- ✅ Pattern detection and confidence calculation
- ✅ Suggestion generation (all types)
- ✅ Preference management
- ✅ Statistics calculation
- ✅ Data export functionality
- ✅ Integration workflows

**Expected coverage**: >85%

## Troubleshooting

### Database Locked Error

**Problem**: `sqlite3.OperationalError: database is locked`

**Solution**: Ensure no other processes are accessing the database. Use a context manager:

```python
# Instead of multiple connections
conn1 = sqlite3.connect(db_path)
conn2 = sqlite3.connect(db_path)  # May cause locking

# Use single connection or context manager
with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    # Do work
```

### Pattern Not Detected

**Problem**: Patterns not appearing despite repeated actions

**Solution**: Check minimum thresholds:
- At least 3 occurrences within 30 days
- Use lower confidence threshold: `get_patterns(min_confidence=0.3)`

### Slow Query Performance

**Problem**: Queries taking too long

**Solution**:
1. Check database size: `ls -lh ~/.cortex/context_memory.db`
2. Rebuild indexes: `REINDEX`
3. Use date filters for large datasets
4. Consider archiving old entries

## Future Enhancements

- [ ] Machine learning-based pattern recognition
- [ ] Cross-user anonymized pattern sharing
- [ ] Natural language query interface
- [ ] Automatic workflow script generation
- [ ] Integration with system monitoring
- [ ] Predictive failure detection
- [ ] Smart caching of frequent queries
- [ ] Multi-user support with privacy isolation

## Contributing

Contributions welcome! Areas for improvement:

1. **Pattern Recognition**: Better algorithms for pattern detection
2. **Suggestion Quality**: More sophisticated suggestion generation
3. **Performance**: Query optimization for large datasets
4. **Privacy**: Enhanced anonymization techniques
5. **Integration**: Hooks for other Cortex modules

## License

Part of Cortex Linux - AI-Native Operating System

## Support

- **Issues**: https://github.com/cortexlinux/cortex/issues
- **Discussions**: https://github.com/cortexlinux/cortex/discussions
- **Discord**: https://discord.gg/uCqHvxjU83
- **Email**: mike@cortexlinux.com

---

**Issue #24** - AI Context Memory System  
**Bounty**: $200 upon merge  
**Skills**: Python, SQLite, Machine Learning, Pattern Recognition
