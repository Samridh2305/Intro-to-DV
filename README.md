# Fewer Fires, Bigger Burns - COMP 6934 Team 9

Final project for COMP 6934 (Fall 2026). We look at the Canadian National Fire
Database (NFDB) to see where Canada's burned area comes from.

Team 9 (all three contributed equally):

| Name               | Student ID |
|--------------------|------------|
| Amar Preet Singh   | 202680417  |
| Samridh Barthaval  | 202582280  |
| Prakash Periyasamy | 202681309  |

The finished report is [`report/report.pdf`](report/report.pdf).

## Folder layout

```
make_figures.py      cleans the data and makes every figure in the report
requirements.txt     python packages (versions we used)
data/                NFDB_point_txt.zip (our copy of the fire data)
                     + boundaries/ (province outlines)
figures/             output: fig1 ... fig6 as PDF and PNG,
                     numbers_used_in_report.txt
report/report.tex    the LaTeX report
report/report.pdf    the compiled report
```

## How to run

Python 3.12 was used.

```
python -m venv .venv
.venv\Scripts\activate          (Windows)   or   source .venv/bin/activate
pip install -r requirements.txt
python make_figures.py
```

The script unzips `data/NFDB_point_txt.zip` (version 20260811, the one used
in the report), then writes the six figures to `figures/` and prints the
numbers we quote in the report. If the zip or the province outlines are
missing it downloads them. It takes less than a minute.

## Data

- NFDB fire point data, version **20260811** (11 Aug 2026), Natural Resources
  Canada, Open Government Licence - Canada.
  https://cwfis.cfs.nrcan.gc.ca/downloads/nfdb/fire_pnt/current_version/NFDB_point_txt.zip
- Province/territory outlines: Natural Earth 1:50m Admin 1, v5.1.1.

The NRCan link always points to the newest version, which is why we keep our
own copy in the repo. If you use a newer download instead, change `DATA_FILE`
at the top of the script (the numbers will then be slightly different from the
report).

## Building the report

The report figures are read from `../figures/`. On Overleaf, upload
`report.tex` and the `figures/` folder (the `.pdf` files are enough) next to
it; `\graphicspath` looks in both places.
