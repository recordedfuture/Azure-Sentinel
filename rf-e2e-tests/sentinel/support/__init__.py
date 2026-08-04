import sys
import pathlib

# Add rf-e2e-tests root to sys.path so rf_e2e_tests is importable
_ROOT = pathlib.Path(__file__).parents[3]  # rf-e2e-tests/
sys.path.insert(0, str(_ROOT))
