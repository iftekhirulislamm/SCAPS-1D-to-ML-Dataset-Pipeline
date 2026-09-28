import numpy as np
import pandas as pd
import os
from scipy.stats import qmc


SCAPS_ROOT   = "C:/Scaps3309"          # wherever scaps.exe actually lives, no spaces
DEF_FILENAME = "baseline_cell.def"
ACT_FILENAME = "baseline_actions.act"   # SCAPS's own extension is .act, not .sca

# Your own project workspace, just for bookkeeping (CSV + generated .script file)
BASE_DIR = "C:/SCAPS_ML"
os.makedirs(BASE_DIR, exist_ok=True)

# ==============================================================================
# 1. DEFINE PARAMETER SPACE
# ==============================================================================
parameters = {
    "ETL_Thickness_um":     [0.05, 0.15, False],
    "ETL_Doping_cm3":       [1e15, 1e19, True],
    "ETL_BulkDefect_cm3":   [1e12, 1e17, True],

    "Abs_Thickness_um":     [0.4, 0.8, False],
    "Abs_Doping_cm3":       [1e15, 1e18, True],
    "Abs_BulkDefect_cm3":   [1e10, 1e15, True],

    "HTL_Thickness_um":     [0.05, 0.15, False],
    "HTL_Doping_cm3":       [1e16, 1e20, True],
    "HTL_BulkDefect_cm3":   [1e12, 1e17, True],

    "Int_Defect_ETL_Abs":   [1e10, 1e16, True],
    "Int_Defect_Abs_HTL":   [1e10, 1e16, True],

    "R_series_ohm_cm2":     [0.1, 10.0, False],
    "R_shunt_ohm_cm2":      [1e2, 1e5, True],
    "Temperature_K":        [280, 350, False],
}

num_samples = 5000
param_names = list(parameters.keys())

# ==============================================================================
# 2. LATIN HYPERCUBE SAMPLING (LHS) WITH PHYSICAL-PLAUSIBILITY FILTERING
# ==============================================================================
# SCAPS's solver can hang indefinitely (not error out) when a sample is
# physically extreme -- most commonly when a layer's bulk defect density
# approaches or exceeds its doping density, breaking charge neutrality.
# Since a script has no way to time out or skip a stuck run, we filter
# those combinations out BEFORE writing the script, rather than discovering
# them one stalled batch at a time.
#
# Rule of thumb enforced below: for each layer, BulkDefect <= 0.5 * Doping.
# Adjust MAX_DEFECT_TO_DOPING_RATIO if this is too strict/loose for your
# material system.
MAX_DEFECT_TO_DOPING_RATIO = 0.5
DEFECT_DOPING_PAIRS = [
    ("ETL_BulkDefect_cm3", "ETL_Doping_cm3"),
    ("Abs_BulkDefect_cm3", "Abs_Doping_cm3"),
    ("HTL_BulkDefect_cm3", "HTL_Doping_cm3"),
]

print("Generating Latin Hypercube Samples...")
sampler = qmc.LatinHypercube(d=len(parameters))

accepted_rows = []
batch_size = num_samples
attempts = 0
max_attempts = 50  # safety cap on resampling rounds

total_accepted = 0
while total_accepted < num_samples and attempts < max_attempts:
    attempts += 1
    sample_matrix = sampler.random(n=batch_size)

    scaled = np.zeros_like(sample_matrix)
    for i, key in enumerate(param_names):
        min_val, max_val, is_log = parameters[key]
        if is_log:
            log_min, log_max = np.log10(min_val), np.log10(max_val)
            scaled[:, i] = 10 ** (log_min + sample_matrix[:, i] * (log_max - log_min))
        else:
            scaled[:, i] = min_val + sample_matrix[:, i] * (max_val - min_val)

    batch_df = pd.DataFrame(scaled, columns=param_names)

    # Reject rows where any layer's defect density is too close to/above doping
    keep_mask = pd.Series(True, index=batch_df.index)
    for defect_col, doping_col in DEFECT_DOPING_PAIRS:
        keep_mask &= batch_df[defect_col] <= MAX_DEFECT_TO_DOPING_RATIO * batch_df[doping_col]

    accepted_rows.append(batch_df[keep_mask])
    total_accepted += int(keep_mask.sum())
    print(f"  Attempt {attempts}: kept {keep_mask.sum()}/{batch_size} "
          f"(running total {total_accepted}/{num_samples})")

df_inputs = pd.concat(accepted_rows, ignore_index=True)
if len(df_inputs) < num_samples:
    print(f"WARNING: only generated {len(df_inputs)}/{num_samples} plausible "
          f"samples after {max_attempts} attempts. Consider loosening "
          f"MAX_DEFECT_TO_DOPING_RATIO.")
else:
    df_inputs = df_inputs.iloc[:num_samples].reset_index(drop=True)
csv_path = f"{BASE_DIR}/ML_Inputs_Backup.csv"
import time
for attempt in range(5):
    try:
        df_inputs.to_csv(csv_path, index=False)
        break
    except PermissionError:
        if attempt == 4:
            raise PermissionError(
                f"\nCould not write {csv_path} after 5 attempts.\n"
                "Likely causes:\n"
                "  1. The CSV is open in Excel/Notepad/another program -- close it.\n"
                "  2. OneDrive is mid-sync and briefly locked the file -- wait a moment and rerun.\n"
                "  3. Consider moving BASE_DIR outside your OneDrive-synced Desktop folder\n"
                "     (e.g. C:/SCAPS_ML instead of a path under OneDrive) to avoid this entirely."
            )
        print(f"  CSV write locked, retrying in 2s... (attempt {attempt + 1}/5)")
        time.sleep(2)

# ==============================================================================
# 3. GENERATE SCAPS BATCH SCRIPT (corrected syntax)
# ==============================================================================
script_filename = f"{BASE_DIR}/run_5000_sims.script"

print("Writing SCAPS script file...")
with open(script_filename, "w") as f:

    # Route script errors to a log file instead of a GUI popup that would
    # otherwise hang the batch (SCAPS ignores mouse/keyboard during a script).
    f.write("set errorhandling.appendtofile scaps_batch_errors.log\n\n")

    # Bare filenames only -- resolved inside <SCAPS_ROOT>\def
    f.write(f"load definitionfile {DEF_FILENAME}\n")
    f.write(f"load action {ACT_FILENAME}\n\n")   # 'action' = actionlistfile shorthand

    for idx in range(num_samples):
        row = df_inputs.iloc[idx]

        # ETL (Layer 1)
        f.write(f'set layer1.thickness {row["ETL_Thickness_um"]}\n')
        f.write(f'set layer1.Nd {row["ETL_Doping_cm3"]}\n')
        f.write(f'set layer1.defect1.Ntotal {row["ETL_BulkDefect_cm3"]}\n')

        # Absorber (Layer 2)
        f.write(f'set layer2.thickness {row["Abs_Thickness_um"]}\n')
        f.write(f'set layer2.Na {row["Abs_Doping_cm3"]}\n')
        f.write(f'set layer2.defect1.Ntotal {row["Abs_BulkDefect_cm3"]}\n')

        # HTL (Layer 3)
        f.write(f'set layer3.thickness {row["HTL_Thickness_um"]}\n')
        f.write(f'set layer3.Na {row["HTL_Doping_cm3"]}\n')
        f.write(f'set layer3.defect1.Ntotal {row["HTL_BulkDefect_cm3"]}\n')

        # Interface defects: interfaceN.IFdefectM, NOT interfaceN.defectM
        # Values are cm^-2 (areal density) -- confirmed from SCAPS Interface Panel
        f.write(f'set interface1.IFdefect1.Ntotal {row["Int_Defect_ETL_Abs"]}\n')
        f.write(f'set interface2.IFdefect1.Ntotal {row["Int_Defect_Abs_HTL"]}\n')

        # Parasitics: external.Rs / external.Rsh, NOT Rseries/Rshunt
        f.write(f'set external.Rs {row["R_series_ohm_cm2"]}\n')
        f.write(f'set external.Rsh {row["R_shunt_ohm_cm2"]}\n')

        # Temperature is an ACTION command, not a set command
        f.write(f'action workingpoint.temperature {row["Temperature_K"]}\n')

        # 'calculate' takes no argument
        f.write("calculate\n")

        # Saved into <SCAPS_ROOT>\results by bare filename
        f.write(f"save results.iv run_{idx}.iv\n")

        # CRITICAL: SCAPS accumulates every calculated result in an internal
        # in-session history, and 'save results.iv' dumps that ENTIRE history
        # every time -- not just the latest run. Without this line, run_5.iv
        # would contain runs 0 through 5 all concatenated, run_500.iv would
        # contain runs 0 through 500, etc. -- both wasting enormous disk space
        # and making every later file harder to parse correctly.
        # 'clear simulations' is the documented script equivalent of clicking
        # 'clear all simulations' on the Action Panel: it resets that internal
        # history so the NEXT save only contains the next run's own result.
        f.write("clear simulations\n\n")

print("Script generation complete.")
print(f"Script:  {script_filename}")
print(f"CSV:     {BASE_DIR}/ML_Inputs_Backup.csv")
print("\nBEFORE RUNNING:")
print(f"  1. Copy {DEF_FILENAME} and {ACT_FILENAME} into {SCAPS_ROOT}/def")
print(f"  2. Make sure {SCAPS_ROOT}/results exists (SCAPS writes .iv files there)")
print("  3. Test with num_samples = 2-3 first before scaling to 5000")