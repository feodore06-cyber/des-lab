# BioMat Lab — feature documentation

## Projects

A project holds one research question, its own variable definitions, its experiments, its protocol
notes and its literature. Projects are independent by default; cross-project analysis is only done
when explicitly requested.

## Experiments

Each experiment is one row. The row's fields are the project's variables, in the order the project
declares. Sample IDs are generated per project (EXP-01, EXP-02, ...): switching to another project
does not restart or disturb the numbering of this one.

## Variable management

Variables can be added, hidden, reordered and removed.

- Hiding a column changes the display only; the stored measurements are untouched.
- Removing a variable stops it being asked for in future entries; historical values stay in the
  records and are reported before anything is removed.
- Units and display names can be edited; the stored values are not rewritten silently.

## Comparison: two experiments

The comparison shows:

1. Results, one row per result variable, with absolute and relative differences.
2. Conditions, split into identical, differing and missing.
3. Interpretation: the observed pattern, possible explanations, alternative explanations, and the
   limits of the evidence.

Causation is never asserted from two runs.

## Comparison: experiment against literature

The paper's parameters and results are extracted, mapped onto the project's variables, and shown
next to the laboratory's values. Values with different definitions are flagged as not directly
comparable before any difference is computed. Each extracted value links back to its source.

## Comparison: project-wide

Experiments can be ranked by a chosen result variable, grouped by condition, and checked for
repeats. Ranking refuses to mix incompatible result definitions.

## Export

CSV and JSON. The JSON export carries the variable definitions alongside the records, so an outside
reader can interpret every column.

## Limits

- The AI proposes variable roles and extracts literature values; the researcher confirms them.
- Extraction from figures and graphs is not part of the first release.
- The public site contains synthetic examples only; no research record is reachable from it.
