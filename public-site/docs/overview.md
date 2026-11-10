# BioMat Lab — product overview

BioMat Lab is a scientific intelligence platform for chemistry, materials science and formulation
research. It does three things that are usually done by hand:

1. It records experiments in a structured, project-specific form.
2. It understands what each variable is — a condition, a result, a derived value, a label.
3. It compares results, after checking that the numbers actually mean the same thing.

Everything on this site is synthetic example data. The working platform requires sign-in and is not
reachable from this public site.

## The problem it addresses

Laboratory records usually live in spreadsheets that mix conditions and outcomes in the same table,
with units in the header and no definition of what a column means. Two consequences follow:

- A result cannot be compared across projects, because nobody wrote down the denominator.
- Literature values cannot be compared with the laboratory's own, because a paper's "lignin yield"
  may be a percentage of biomass while the lab's is a percentage of lignin.

BioMat Lab makes the definition part of the data model.

## Variable definitions

Every variable carries a name, a unit, a scientific role, and — for computed values — a formula.
Roles are:

- parameter: a condition the experimenter sets;
- result: a measured outcome;
- derived: computed from measurements (for example yield from recovered mass and biomass);
- identifier: a label such as a sample ID;
- covariate: recorded, but neither a condition nor an outcome.

Results additionally carry a priority (primary or secondary). Role and priority are different
concepts and are stored separately. There is deliberately no star rating of variables.

## Comparability

Before two results are compared, the platform compares their definitions: numerator, denominator,
unit, material identity, measurement method, and the experimental conditions. The outcome is one of
four statuses:

- directly comparable;
- comparable with caveats (for example a single run, no replicates);
- not directly comparable (different definitions);
- insufficient information.

Worked example: with 3 g of dry biomass and 388 mg of recovered lignin, the yield is 12.93 % of
biomass, while the recovery is 58.8 % of the 660 mg of lignin present (assuming 22 % Klason lignin).
The same 388 mg gives two different numbers; they are never compared as if they were one metric.

## Literature extraction

Given a paper, the platform extracts parameters and results and keeps, for each value:

- the original wording, for example "3 h";
- the normalised value and unit, for example 180 min;
- the source location: page, table or section;
- a status: extracted and awaiting review, verified, corrected by the user, not reported, or
  extraction failed.

Values the paper does not report are marked "not reported" and are never filled in by inference.
The researcher checks each value; corrections are kept distinct from the AI's output.

## Data and exports

Records export to CSV and JSON. Derived values store their formula, so they can be recomputed from
the underlying measurements rather than trusted as numbers.

## Public demo links

- Variable definitions: data/variables.json
- Experiment records: data/demo_dataset.json
- Comparison result: data/demo_comparison.json
- Literature extraction: data/demo_literature.json
