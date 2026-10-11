# Data library status

Generated: 2026-10-11T07:21:43+00:00

Only the current source version is shown. A completed analysis is preferred over partial runs.
Ready means processing is complete, not that AI conclusions have been independently validated.

## Analysis ready

| Dataset | Version | Reviews | Topics | Status |
| --- | --- | --- | --- | --- |
| F70\_feedback\_hackathon\.xlsx | 1 | 2128 | 460 | Ready |

## Awaiting or incomplete analysis

| Dataset | Version | Reviews | Topics | Status |
| --- | --- | --- | --- | --- |
| G60\_feedback\_hackathon\.xlsx | 1 | 4000 | 0 | Awaiting analysis |
| G70\_feedback\_hackathon\.xlsx | 1 | 4000 | 0 | Awaiting analysis |

## Supporting data imported

| Dataset | Version | Reviews | Topics | Status |
| --- | --- | --- | --- | --- |
| F70\_G60\_G68\_G70\_customer\_studies\.xlsx | 1 | 0 | 0 | Imported: 0 sales, 1833 study observations, 0 PDF pages |
| F70\_OptionList\.PDF | 1 | 0 | 0 | Imported: 0 sales, 0 study observations, 23 PDF pages |
| G60\_OptionList\.PDF | 1 | 0 | 0 | Imported: 0 sales, 0 study observations, 28 PDF pages |
| G70\_OptionList\.PDF | 1 | 0 | 0 | Imported: 0 sales, 0 study observations, 27 PDF pages |
| sales\_volumes\.xlsx | 1 | 0 | 0 | Imported: 36 sales, 0 study observations, 0 PDF pages |

## Refresh after processing another workbook

Run from the feedback_topics_package directory:

```powershell
python data_library.py ingest-all .
python data_library.py status
```

This attaches matching existing analysis files; it does not run AI analysis.
Status files and export bundles are snapshots. Regenerate them after updates.
