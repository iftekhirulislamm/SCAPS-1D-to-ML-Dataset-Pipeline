import re
import glob
import os
import pandas as pd

# ==============================================================================
# CONFIG -- adjust these paths to match your setup
# ==============================================================================
RESULTS_DIR = "C:/Scaps3309/results"
INPUTS_CSV = "C:/SCAPS_ML/ML_Inputs_Backup.csv"
OUTPUT_CSV = "C:/SCAPS_ML/ML_Training_Dataset.csv"

# ==============================================================================
# PARSE EACH .iv FILE FOR ITS DEDUCED SOLAR CELL PARAMETERS
# ==============================================================================
# Each SCAPS .iv file ends with a block like:
#   Voc =        1.269990   Volt
#   Jsc =       26.35857876 mA/cm2
#   FF =        56.1950     %
#   eta =       18.8113     %
#   V_MPP =      0.946309   Volt
#   J_MPP =     19.87862889 mA/cm2
PARAM_PATTERNS = {
    "Voc_V":    r"Voc\s*=\s*([-\d.eE+]+)",
    "Jsc_mA_cm2": r"Jsc\s*=\s*([-\d.eE+]+)",
    "FF_pct":   r"FF\s*=\s*([-\d.eE+]+)",
    "eta_pct":  r"eta\s*=\s*([-\d.eE+]+)",
    "V_MPP_V":  r"V_MPP\s*=\s*([-\d.eE+]+)",
    "J_MPP_mA_cm2": r"J_MPP\s*=\s*([-\d.eE+]+)",
}

iv_files = glob.glob(os.path.join(RESULTS_DIR, "run_*.iv"))
print(f"Found {len(iv_files)} .iv files in {RESULTS_DIR}")

results = {}
failed_parses = []
multi_block_files = []

for filepath in iv_files:
    fname = os.path.basename(filepath)
    match = re.search(r"run_(\d+)\.iv", fname)
    if not match:
        continue
    run_idx = int(match.group(1))

    with open(filepath, "r", errors="ignore") as f:
        content = f.read()

    # SCAPS's 'save results.iv' APPENDS rather than overwrites. If a script
    # was re-run during testing without clearing the results folder first,
    # a file can contain several concatenated simulation blocks. Detect that
    # and always use the LAST block (the most recent result), not the first.
    num_blocks = content.count("SCAPS 3.3.09 ELIS-UGent")
    if num_blocks > 1:
        multi_block_files.append((fname, num_blocks))
        last_block_start = content.rfind("SCAPS 3.3.09 ELIS-UGent")
        content = content[last_block_start:]

    row = {"run_index": run_idx}
    ok = True
    for key, pattern in PARAM_PATTERNS.items():
        m = re.search(pattern, content)
        if m:
            row[key] = float(m.group(1))
        else:
            row[key] = None
            ok = False

    if not ok:
        failed_parses.append(fname)

    results[run_idx] = row

if multi_block_files:
    print(f"\nWARNING: {len(multi_block_files)} files contained multiple "
          f"appended simulation blocks (leftover from repeated script runs).")
    print("Used the LAST block in each -- verify results directory was meant "
          "to accumulate these, or delete stale .iv files and re-run for a "
          "clean batch. Affected files (first 10):")
    for fname, n in multi_block_files[:10]:
        print(f"  {fname}: {n} blocks")

print(f"Successfully parsed: {len(results) - len(failed_parses)}")
if failed_parses:
    print(f"WARNING: {len(failed_parses)} files missing one or more parameters "
          f"(likely non-converged runs). First few: {failed_parses[:10]}")

# ==============================================================================
# BUILD OUTPUT DATAFRAME, SORTED BY RUN INDEX
# ==============================================================================
results_df = pd.DataFrame(results.values()).sort_values("run_index").reset_index(drop=True)

# ==============================================================================
# MERGE WITH THE ORIGINAL INPUT PARAMETERS
# ==============================================================================
inputs_df = pd.read_csv(INPUTS_CSV)
inputs_df["run_index"] = inputs_df.index  # row order must match generation order

merged_df = inputs_df.merge(results_df, on="run_index", how="left")

# Flag rows where SCAPS produced no matching .iv file at all (e.g. it hung,
# was skipped, or the batch was stopped early)
missing_runs = merged_df[merged_df["Voc_V"].isna()]
if len(missing_runs) > 0:
    print(f"\n{len(missing_runs)} input rows have NO corresponding parsed result "
          f"(missing .iv file or failed parse). Their run_index values:")
    print(missing_runs["run_index"].tolist()[:20],
          "..." if len(missing_runs) > 20 else "")

merged_df.to_csv(OUTPUT_CSV, index=False)
print(f"\nSaved merged dataset: {OUTPUT_CSV}")
print(f"Total rows: {len(merged_df)}  |  Complete rows: {len(merged_df) - len(missing_runs)}")