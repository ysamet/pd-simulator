# Grid templates — hand-authored starting layouts

Files in this folder paint the starting world for a lattice run, cell by
cell. In the app, set **Initial layout** to `from_file` and type a file's
bare name (e.g. `example_quadrants.txt`) into **Layout file** — a name with
no path separator is looked up here. A full or relative path (anything
containing `/` or `\`) is used as given instead.

## Format

```
kind: lattice_grid
rows: 4
cols: 6

<one token per cell, 24 tokens in total>
```

- The three header lines are required, in any order, before the grid body.
  `kind: lattice_grid` is a format marker — always exactly that, for now.
- `rows:` and `cols:` must match the run's grid dimensions.
- The body has one **token per cell**. Tokens are separated by
  **whitespace**, or by **commas**: if any body line contains a comma, the
  whole file is read comma-separated (each token is trimmed), so the two
  styles cannot be mixed. Line breaks are cosmetic — only token order
  matters — but one line per grid row is the readable convention.
- A token is either a strategy **machine name, spelled exactly as
  registered** (the app lists the current names beside the Layout file
  box), or `.` for an **empty cell**. In comma style, an empty field
  (`,,`) is an error, not an empty cell — write the `.`.
- Blank lines are ignored; lines starting with `#` are comments.
- The number of non-`.` cells is the number of agents, and the run's
  **Population size must equal it** (each example below states its count).
  Which strategy sits where is entirely the file's decision — the
  population-mix widgets are superseded. You do not have to type the
  numbers yourself: when the Population section disagrees with the file,
  the app shows the difference and offers a one-click **Populate the
  Population section from the file**.

A run that uses a template copies it into its run folder, so the recorded
run stays reproducible even if the template here is later edited.

## The examples

- `example_quadrants.txt` — whitespace-separated, 4×6, **18 agents**:
  three strategy blocks and an empty strip.
- `example_island.txt` — comma-separated, 4×6, **24 agents**: a
  tit-for-tat island inside a sea of defectors.
