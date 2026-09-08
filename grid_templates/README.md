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

## Painting a layout in the app

You do not have to type a layout file. The app's **Layout painter** tab
(the second tab, after "Run lab") paints one with the mouse: start a blank
grid, load one of the files here, or copy the Run lab's founding preview;
pick a gesture under **Tool** (Draw paints every cell the pointer passes
over while the button is held; Rectangle paints a dragged box; Lasso
paints an enclosed area) and a strategy (or the eraser) under **Brush**,
then press and drag over the canvas; then **Save layout** writes an
ordinary file of exactly the
format above into this folder under the bare name you type (`.txt` is added
when you give no extension), opening with the comment line
`# written by the pdsim layout painter`. **Use this layout in the Run lab**
then sets the Run lab to an evolution run on a lattice of the painting's
size with `from_file` naming the saved file, and fills the Population
section in from it. The shipped examples below are protected — the painter
refuses to overwrite them — and any other existing name needs the
**Replace the existing file** box ticked.

The painter's **Existing layout file** list shows the **`.txt` files** in
this folder only: this README, and anything saved under another extension,
is not offered for loading. A painting you want to keep is yours to commit;
a recorded run stays self-contained regardless, because the run folder
holds its own copy.

## The examples

- `example_quadrants.txt` — whitespace-separated, 4×6, **18 agents**:
  three strategy blocks and an empty strip.
- `example_island.txt` — comma-separated, 4×6, **24 agents**: a
  tit-for-tat island inside a sea of defectors.
- `example_template_20x20.txt` — whitespace-separated, 20×20, **400
  agents** (a full grid): a chequer of 5×5 blocks alternating Always Defect
  and Tit for Tat — the owner's hand-written sample, formerly
  `Grid_Layout_Template.md`, loadable in the painter as a large editable
  starting point.
