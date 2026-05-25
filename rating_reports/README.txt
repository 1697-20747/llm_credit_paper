Rating agency reports on specific banks — PDF format.

These are reports written by Moody's, S&P, Fitch, DBRS etc.
on individual banks (e.g. "Fitch Affirms Lloyds Banking Group at A+").

These are processed by 03_extract_rating_agency.py and contribute
to Pipeline B training pairs tagged as document_type=rating_report.

Examples of what to place here:
  - fitch_lloyds_2024_rating_action.pdf
  - sp_jpmorgan_2024_research_update.pdf
  - moodys_barclays_2023_credit_opinion.pdf

Run after adding files:
  ./run.sh --reprocess
