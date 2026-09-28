# SCAPS-1D to ML Dataset Pipeline

These scripts generate a machine-learning-ready dataset from SCAPS-1D by running
it across thousands of Latin Hypercube sampled device configurations. There are
two Python scripts, with a SCAPS-1D batch run in between:

```
generate_scaps_batch.py  -->  SCAPS-1D (.script execution)  -->  parse_scaps_results.py
   (creates the .script file)       (creates thousands of .iv files)     (creates the final training CSV)
```

The parameter ranges in the generator are placeholders. Edit them to suit your
own device before running.

---

## 1. Prerequisites

- SCAPS-1D installed in a normal, non-protected folder (e.g. `C:\Scaps3309\`).
  Do not install or run it from `C:\Program Files (x86)\...`. Windows silently
  redirects writes from protected folders to a hidden `VirtualStore` location,
  which makes your output files appear to vanish.
- Python 3.x with `numpy`, `pandas` and `scipy`:
  ```
  pip install numpy pandas scipy
  ```
- Your baseline device files, already built and tested manually in the SCAPS GUI:
  - `baseline_cell.def` (problem definition)
  - `baseline_actions.act` (action list / IV measurement settings)

---

## 2. Directory layout

| Purpose | Path used in this guide | Notes |
|---|---|---|
| SCAPS install root | `C:\Scaps3309\` | Wherever `scaps3309.exe` actually lives |
| SCAPS definition files | `C:\Scaps3309\def\` | `.def` and `.act` files must live here |
| SCAPS results output | `C:\Scaps3309\results\` | SCAPS writes all `.iv` files here automatically |
| Your project workspace | `C:\SCAPS_ML\` | Generated `.script` file, input CSV, final dataset |

Note that SCAPS script commands (`load`, `save`) only take a bare filename,
never a path. SCAPS resolves them against its own fixed subfolders listed above,
so you can't redirect them to `C:\SCAPS_ML\` or anywhere else from the script.

If you can, keep `C:\SCAPS_ML\` and the SCAPS folder out of OneDrive-synced
locations (e.g. Desktop). Active syncing can lock files mid-write.

---

## 3. Step 1: Generate the SCAPS script (`generate_scaps_batch.py`)

What it does:
1. Defines a 14-parameter search space (layer thicknesses, doping, bulk and
   interface defect densities, parasitic resistances, temperature).
2. Draws Latin Hypercube samples, rejecting and resampling any combination
   where a layer's bulk defect density exceeds half its doping density (a
   common cause of SCAPS non-convergence).
3. Saves the accepted parameter combinations to `ML_Inputs_Backup.csv`.
4. Writes `run_5000_sims.script`, a SCAPS script that, for each sample, sets
   all 14 parameters, runs `calculate`, saves the result to `run_<i>.iv`, then
   runs `clear simulations`. That last command resets SCAPS's internal result
   history so each `.iv` file holds only that one run.

Before running, check these variables at the top of the script:
```python
SCAPS_ROOT   = "C:/Scaps3309"
DEF_FILENAME = "baseline_cell.def"
ACT_FILENAME = "baseline_actions.act"
BASE_DIR     = "C:/SCAPS_ML"
num_samples  = 5000
```

For a first run, set `num_samples = 5` and do an end-to-end check before
committing to the full batch.

Run it:
```
python generate_scaps_batch.py
```

Output:
- `C:\SCAPS_ML\ML_Inputs_Backup.csv`: one row per accepted sample, 14 parameter
  columns.
- `C:\SCAPS_ML\run_5000_sims.script`: the SCAPS batch script.

Before moving on, copy `baseline_cell.def` and `baseline_actions.act` into
`C:\Scaps3309\def\` and make sure `C:\Scaps3309\results\` exists.

---

## 4. Step 2: Run the script in SCAPS-1D

1. Open SCAPS-1D.
2. Load and run `C:\SCAPS_ML\run_5000_sims.script` (via the script option in the
   Action Panel or File menu; the exact path depends on your SCAPS version).
3. SCAPS won't respond to mouse or keyboard until the script finishes. Windows
   may show "Not Responding" while it computes. This is expected.
4. When it's done, check:
   - `C:\Scaps3309\results\run_0.iv` ... `run_4999.iv` for the simulated I-V
     results.
   - `C:\Scaps3309\scaps_batch_errors.log` for any errors logged during the run.

If SCAPS seems stuck on one run for a long time, look at Task Manager and check
the CPU usage of `scaps3309.exe`. Near-0% for several minutes on one sample
usually means a non-convergent parameter combination. You may need to kill the
process and tighten the plausibility filter in Step 1.

---

## 5. Step 3: Parse results and build the dataset (`parse_scaps_results.py`)

What it does:
1. Scans `C:\Scaps3309\results\` for every `run_*.iv` file.
2. Extracts `Voc`, `Jsc`, `FF`, `eta`, `V_MPP` and `J_MPP` from each (SCAPS
   writes these at the bottom of every `.iv` file).
3. If a file contains several concatenated result blocks (e.g. left over from an
   earlier test run), it uses only the last block and warns you which files were
   affected.
4. Merges the outputs with `ML_Inputs_Backup.csv` by run index.
5. Flags input rows with no matching `.iv` file (missing or failed runs).
6. Saves the final merged dataset.

Before running, check the paths at the top of the script:
```python
RESULTS_DIR = "C:/Scaps3309/results"
INPUTS_CSV  = "C:/SCAPS_ML/ML_Inputs_Backup.csv"
OUTPUT_CSV  = "C:/SCAPS_ML/ML_Training_Dataset.csv"
```

Run it:
```
python parse_scaps_results.py
```

Output:
- `C:\SCAPS_ML\ML_Training_Dataset.csv`: 14 input columns plus 6 output columns
  (`Voc_V`, `Jsc_mA_cm2`, `FF_pct`, `eta_pct`, `V_MPP_V`, `J_MPP_mA_cm2`), one
  row per sample.

Notes:
- If you run the parser before SCAPS has finished, unfinished rows will show
  `NaN` in the output columns. Drop them before training.
- You can re-run the parser later without any code changes once more samples
  finish. It picks up new files automatically.

---

## 6. Checklist

- [ ] SCAPS installed outside `Program Files` (avoids the VirtualStore redirect)
- [ ] `baseline_cell.def` and `baseline_actions.act` verified manually in the
      SCAPS GUI
- [ ] Step 1 variables (`SCAPS_ROOT`, `DEF_FILENAME`, `ACT_FILENAME`,
      `BASE_DIR`, `num_samples`) updated for your setup
- [ ] Parameter ranges edited to match your device
- [ ] `.def` and `.act` files copied into `C:\Scaps3309\def\`
- [ ] `C:\Scaps3309\results\` exists
- [ ] Tested with `num_samples = 5` first
- [ ] `results` folder cleared of old test files before the real batch
- [ ] Full batch run in SCAPS
- [ ] `scaps_batch_errors.log` checked for failures
- [ ] Parser run, `ML_Training_Dataset.csv` produced
- [ ] Incomplete (`NaN`) rows dropped before training
