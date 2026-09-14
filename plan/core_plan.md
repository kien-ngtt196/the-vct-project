# Core Development Plan: High-Performance Analytics Engine

## Goal
Build a high-performance C++ core integrated with Python via `pybind11` to calculate complex statistical features (Player Form, Team Strength, Map Elo) from PostgreSQL data. These features will serve as the primary input for the Machine Learning model.

---

## Tech Stack
*   **Language:** C++17 (for math-heavy logic and performance).
*   **Bridge:** `pybind11` (to expose C++ functions as a Python module).
*   **Build System:** `setuptools` + `Pybind11Extension` (to compile `.cpp` into `.pyd` binaries).
*   **Database:** PostgreSQL (source of raw data).
*   **Logic:** Exponential Time-Decay algorithms, Standard Deviation, and Elo-based systems.

---

## Phase 1: Environment & Tooling
**Objective:** Set up the compiler and bridge to ensure C++ and Python can talk.
1.  **Compiler Installation:** 
    *   Install **MSVC (Microsoft Visual C++ Build Tools)** via Visual Studio Installer.
2.  **Library Setup:**
    *   `pip install pybind11`
3.  **Project Structure:**
    *   Create `src/core/` directory.
    *   Create `analytics.cpp` (C++ logic) and `setup.py` (build script).

---

## Phase 2: Algorithm Implementation (C++)
**Objective:** Write the math logic in C++ for maximum speed.
1.  **Time-Decayed Player Form:**
    *   Implement exponential decay: $Weight = e^{-\lambda \cdot DaysAgo}$.
    *   Calculate weighted averages for `ACS`, `K/D`, and `Rating`.
2.  **Team Map-Strength (Elo):**
    *   Calculate map-specific power ratings by iterating through match histories.
3.  **Consistency/Volatility Metrics:**
    *   Calculate Standard Deviation of player performance to measure "reliability."

---

## Phase 3: Python Bridging (pybind11)
**Objective:** Compile the C++ code into a usable Python module.
1.  **Module Definition:**
    *   Use `PYBIND11_MODULE` macro in C++ to map functions.
2.  **Compilation:**
    *   Run `python setup.py build_ext --inplace` to generate `vct_core.pyd`.
3.  **Verification:**
    *   Write a test script to `import vct_core` and verify math results.

---

## Phase 4: Data Pipeline Integration
**Objective:** Connect the database to the C++ core.
1.  **Feature Extractor Script:**
    *   Write `src/core/feature_extractor.py`.
    *   Use `psycopg2` to fetch player/match history from PostgreSQL.
2.  **Data Processing:**
    *   Group raw SQL results by player/team.
    *   Pass large lists of numbers (ACS, dates) from Python to C++.
    *   Receive calculated scores (Form, Strength) back from C++.

---

## Phase 5: Feature Engineering for ML
**Objective:** Create the final dataset for the XGBoost model.
1.  **Feature Table:**
    *   Create a new PostgreSQL table `match_features` or export to `training_data.csv`.
2.  **Row Generation:**
    *   For every historical match, calculate the "Snapshot" of player form and team strength *exactly as it was on that match date*.
3.  **Target Variable:**
    *   Map these features to the actual match result (Win/Loss) for training.
