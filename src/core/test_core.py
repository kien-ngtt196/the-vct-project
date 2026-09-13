import sys
import os

# Add the current directory to sys.path so we can import the compiled module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import vct_core
    print("SUCCESS: Loaded vct_core module!")
    
    # Test decay calculation
    values = [200.0, 250.0, 300.0]
    days_ago = [10, 5, 0]
    decay_result = vct_core.calculate_time_decay_form(values, days_ago, 0.05)
    print(f"Time Decay Result: {decay_result:.4f}")
    
    # Test consistency (Standard Deviation)
    cons_result = vct_core.calculate_consistency(values)
    print(f"Consistency (StdDev): {cons_result:.4f}")
    
    # Test composite rating
    comp_result = vct_core.calculate_composite_rating(1.2, 250.0, 75.0, 140.0)
    print(f"Composite Rating: {comp_result:.4f}")
    
except ImportError as e:
    print("ERROR: Could not import vct_core module.")
    print("Make sure to compile the module first using:")
    print("  python setup.py build_ext --inplace")
    print(f"Error details: {e}")
