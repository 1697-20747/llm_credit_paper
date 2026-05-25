Existing credit papers in Microsoft Word format (DOCX).

These become GOLD STANDARD training examples — the highest quality
training data in the pipeline because they are real analyst-written
credit analyses.

The extractor (06_extract_credit_reports.py) will:
  1. Extract full text from each DOCX
  2. Identify CAMELS sections automatically
  3. Create training pairs where the assistant response IS the
     real analyst content — no templates, no AI generation

Gold pairs are weighted 2x in training to amplify their influence.

Naming convention (optional but helpful for year detection):
  lloyds_banking_group_2024_credit_paper.docx
  jpmorgan_chase_2023_camels_analysis.docx
  barclays_2024_credit_review.docx

Run after adding files:
  ./run.sh --reprocess
