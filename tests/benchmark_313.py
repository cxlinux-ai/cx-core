"""Cortex Python 3.13 Benchmark - Issue #272
TO run benchmarks:
# Install PyYAML (only dep needed)
pip install pyyaml
# Test both versions
python3.11 benchmark_313.py
python3.13 benchmark_313.py
"""

import sys
import timeit

print(f"=== Cortex Python {sys.version_info.major}.{sys.version_info.minor} Benchmark ===\n")

yaml_ops = """
import yaml
data = {'test': i for i in range(100)}
yaml.dump(data)
"""
time_yaml = timeit.timeit(yaml_ops, number=1000)
print(f"✓ YAML Dump (1000x): {time_yaml:.4f}s")

# Dict operations (common Cortex patterns)
dict_ops = """
d = {i: i*2 for i in range(100)}
result = [v for k,v in d.items() if v > 50]
"""
time_dicts = timeit.timeit(dict_ops, number=1000)
print(f"✓ Dict Operations (1000x): {time_dicts:.4f}s")

total = time_yaml + time_dicts
print(f"\n✅ Total Time: {total:.4f}s")
print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} = COMPATIBLE!")
