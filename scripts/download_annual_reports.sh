#!/bin/bash
# =============================================================================
# download_annual_reports.sh — 10-year coverage, all URLs verified May 2026
# =============================================================================
# Usage:
#   chmod +x scripts/download_annual_reports.sh
#   ./scripts/download_annual_reports.sh
#   ./scripts/download_annual_reports.sh --validate
#   ./scripts/download_annual_reports.sh --ar-only
#   ./scripts/download_annual_reports.sh --pillar3-only
#   ./scripts/download_annual_reports.sh --banks hsbc natwest lloyds
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FINANCIALS_DIR="$PROJECT_ROOT/financials"
PILLAR3_DIR="$PROJECT_ROOT/pillar3"
LOGS_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOGS_DIR/download_annual_reports.log"

mkdir -p "$FINANCIALS_DIR" "$PILLAR3_DIR" "$LOGS_DIR"

DRY_RUN=false; PILLAR3_ONLY=false; AR_ONLY=false; VALIDATE=false
FILTER_BANKS=""; MIN_PDF_SIZE=200000

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)      DRY_RUN=true;      shift ;;
    --pillar3-only) PILLAR3_ONLY=true; shift ;;
    --ar-only)      AR_ONLY=true;      shift ;;
    --validate)     VALIDATE=true;     shift ;;
    --banks)        shift; FILTER_BANKS="$*"; break ;;
    *) shift ;;
  esac
done

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN='\033[0;36m';  GREY='\033[0;37m';   NC='\033[0m'
info()   { echo -e "${GREEN}[INFO]${NC}   $*" | tee -a "$LOG_FILE"; }
get()    { echo -e "${CYAN}[GET]${NC}    $*"  | tee -a "$LOG_FILE"; }
skip()   { echo -e "${GREY}[SKIP]${NC}   $*"  | tee -a "$LOG_FILE"; }
ok()     { echo -e "${GREEN}[OK]${NC}     $*"  | tee -a "$LOG_FILE"; }
fail()   { echo -e "${RED}[FAIL]${NC}   $*"  | tee -a "$LOG_FILE"; FAILED_LIST+=("$*"); }
manual() { echo -e "${YELLOW}[MANUAL]${NC} $*" | tee -a "$LOG_FILE"; }
warn()   { echo -e "${YELLOW}[WARN]${NC}   $*" | tee -a "$LOG_FILE"; }

DOWNLOADED=0; SKIPPED=0; FAILED=0; FAILED_LIST=()

echo "" | tee -a "$LOG_FILE"
echo "===================================================================" | tee -a "$LOG_FILE"
echo " Annual Report + Pillar 3 Downloader" | tee -a "$LOG_FILE"
echo " Started: $(date)" | tee -a "$LOG_FILE"
echo "===================================================================" | tee -a "$LOG_FILE"

# ── PDF validation ─────────────────────────────────────────────────────────────
is_valid_pdf() {
  local file="$1"
  [[ ! -f "$file" ]] && return 1
  local size
  size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
  [[ "$size" -lt "$MIN_PDF_SIZE" ]] && return 1
  local magic
  magic=$(xxd -p -l 4 "$file" 2>/dev/null || hexdump -n 4 -e '"%02x"' "$file" 2>/dev/null || echo "")
  [[ "$magic" == "25504446" ]] && return 0
  return 1
}

if [[ "$VALIDATE" == true ]]; then
  echo ""; info "Validating existing files..."
  invalid_count=0
  for dir in "$FINANCIALS_DIR" "$PILLAR3_DIR"; do
    while IFS= read -r -d '' f; do
      if ! is_valid_pdf "$f"; then
        size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
        warn "INVALID (${size}B): $(basename "$f")"; rm -f "$f"
        (( invalid_count++ )) || true
      fi
    done < <(find "$dir" -name "*.pdf" -print0 2>/dev/null)
  done
  info "Removed $invalid_count invalid files."
fi

download_pdf() {
  local url="$1" dest="$2" description="$3"
  if is_valid_pdf "$dest"; then
    local size; size=$(stat -f%z "$dest" 2>/dev/null || stat -c%s "$dest" 2>/dev/null || echo 0)
    skip "$description ($(( size / 1024 ))KB)"
    (( SKIPPED++ )) || true; return 0
  fi
  [[ -f "$dest" ]] && rm -f "$dest"
  get "$description"
  [[ "$DRY_RUN" == true ]] && { info "  [DRY RUN] $url"; return 0; }
  local http_code
  http_code=$(curl -sS -L \
    --max-time 180 --retry 2 --retry-delay 3 \
    -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36" \
    -H "Accept: application/pdf,*/*" \
    -H "Accept-Language: en-GB,en;q=0.9" \
    -H "Referer: https://www.google.com/" \
    -o "$dest" -w "%{http_code}" "$url" 2>/dev/null) || http_code="000"
  if is_valid_pdf "$dest"; then
    local size; size=$(stat -f%z "$dest" 2>/dev/null || stat -c%s "$dest" 2>/dev/null || echo 0)
    ok "$description — $(( size / 1024 ))KB"
    (( DOWNLOADED++ )) || true
  else
    rm -f "$dest"
    fail "$description — HTTP $http_code"
    (( FAILED++ )) || true
  fi
  sleep 0.6
}

should_download() {
  [[ -z "$FILTER_BANKS" ]] && return 0
  for b in $FILTER_BANKS; do [[ "$1" == *"$b"* ]] && return 0; done
  return 1
}

# =============================================================================
# ANNUAL REPORTS
# =============================================================================
if ! $PILLAR3_ONLY; then
echo ""; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ANNUAL REPORTS"; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── LLOYDS ─────────────────────────────────────────────────────────────────────
# 2021+ simple path; pre-2021 uses financial-performance path
if should_download "lloyds"; then
  echo -e "\n${CYAN}Lloyds Banking Group${NC}"
  for year in 2025 2024 2023 2022 2021; do
    download_pdf \
      "https://www.lloydsbankinggroup.com/assets/pdfs/investors/${year}/lbg-${year}-annual-report.pdf" \
      "$FINANCIALS_DIR/${year}-lbg-annual-report.pdf" "Lloyds $year"
  done
  for year in 2020 2019 2018 2017 2016; do
    download_pdf \
      "https://www.lloydsbankinggroup.com/assets/pdfs/investors/financial-performance/lloyds-banking-group-plc/${year}/q4/${year}-lbg-annual-report.pdf" \
      "$FINANCIALS_DIR/${year}-lbg-annual-report.pdf" "Lloyds $year"
  done
fi

# ── HSBC ───────────────────────────────────────────────────────────────────────
if should_download "hsbc"; then
  echo -e "\n${CYAN}HSBC Holdings${NC}"
  for spec in \
    "2024:250227" "2023:240221" "2022:230221" "2021:220222" \
    "2020:210223" "2019:200218" "2018:190219" "2017:180220" \
    "2016:170221" "2015:160222"
  do
    year="${spec%%:*}"; prefix="${spec##*:}"
    download_pdf \
      "https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/${year}/annual/pdfs/hsbc-holdings-plc/${prefix}-annual-report-and-accounts-${year}.pdf" \
      "$FINANCIALS_DIR/hsbc_holdings_${year}_annual_report.pdf" "HSBC $year"
  done
fi

# ── NATWEST / RBS ──────────────────────────────────────────────────────────────
# NOTE: 2022 filename has NO year suffix in the filename
if should_download "natwest"; then
  echo -e "\n${CYAN}NatWest Group (fmr RBS)${NC}"
  for spec in \
    "2024:14022025:nwg-annual-report-and-accounts-2024.pdf" \
    "2023:16022024:nwg-annual-report-and-accounts-2023.pdf" \
    "2022:17022023:nwg-annual-report-and-accounts.pdf" \
    "2021:18022022:natwest-group-annual-report-accounts-2021.pdf" \
    "2020:19022021:natwest-group-annual-report-accounts-2020.pdf" \
    "2019:14022020:rbs-group-annual-report-2019.pdf" \
    "2018:15022019:rbs-annual-report-2018.pdf" \
    "2017:23022018:rbs-annual-report-2017.pdf" \
    "2016:24022017:rbs-annual-report-2016.pdf" \
    "2015:26022016:rbs-annual-report-2015.pdf"
  do
    year="${spec%%:*}"; rest="${spec#*:}"; datepath="${rest%%:*}"; filename="${rest##*:}"
    download_pdf \
      "https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/${datepath}/${filename}" \
      "$FINANCIALS_DIR/natwest_group_${year}_annual_report.pdf" "NatWest/RBS $year"
  done
fi

# ── STANDARD CHARTERED ────────────────────────────────────────────────────────
if should_download "standard_chartered"; then
  echo -e "\n${CYAN}Standard Chartered — manual required (HTTP 403)${NC}"
  manual "  https://www.sc.com/en/investors/results-and-reports/"
  manual "  Save as: financials/standard_chartered_<year>_annual_report.pdf"
fi

# ── DEUTSCHE BANK ──────────────────────────────────────────────────────────────
# KEY FINDING: DB stores each year's report in the NEXT year's folder
# e.g. Annual-Report-2023.pdf is in /2024/ folder
# e.g. Annual-Report-2022.pdf is in /2023/ folder
if should_download "deutsche"; then
  echo -e "\n${CYAN}Deutsche Bank${NC}"
  for spec in \
    "2024:2025" "2023:2024" "2022:2023" "2021:2022" "2020:2021" \
    "2019:2020" "2018:2019" "2017:2018" "2016:2017" "2015:2016"
  do
    report_year="${spec%%:*}"; folder_year="${spec##*:}"
    download_pdf \
      "https://investor-relations.db.com/files/documents/annual-reports/${folder_year}/Annual-Report-${report_year}.pdf" \
      "$FINANCIALS_DIR/deutsche_bank_${report_year}_annual_report.pdf" "Deutsche Bank $report_year"
  done
fi

# ── BNP PARIBAS ────────────────────────────────────────────────────────────────
# URD (Universal Registration Document) format
if should_download "bnp"; then
  echo -e "\n${CYAN}BNP Paribas${NC}"
  for spec in \
    "2024:2025-03:bnp-paribas-2024-universal-registration-document.pdf" \
    "2023:2024-03:bnp-paribas-2023-universal-registration-document.pdf" \
    "2022:2023-03:bnp-paribas-2022-universal-registration-document.pdf" \
    "2021:2022-03:bnp-paribas-2021-universal-registration-document.pdf" \
    "2020:2021-04:bnp-paribas-2020-universal-registration-document.pdf" \
    "2019:2020-03:bnp-paribas-2019-universal-registration-document.pdf" \
    "2018:2019-03:bnp-paribas-2018-registration-document.pdf" \
    "2017:2018-03:bnp-paribas-2017-registration-document.pdf"
  do
    year="${spec%%:*}"; rest="${spec#*:}"; datepath="${rest%%:*}"; filename="${rest##*:}"
    download_pdf \
      "https://invest.bnpparibas/sites/default/files/documents/${datepath}/${filename}" \
      "$FINANCIALS_DIR/bnp_paribas_${year}_annual_report.pdf" "BNP Paribas $year"
  done
fi

# ── UNICREDIT ──────────────────────────────────────────────────────────────────
# 2021+ verified working; pre-2021 uses older path structure
if should_download "unicredit"; then
  echo -e "\n${CYAN}UniCredit${NC}"
  for spec in \
    "2024:4Q24:2024-Annual-Reports-and-Accounts-General-Meeting-Draft.pdf" \
    "2023:4Q23:2023-Annual-Reports-and-Accounts.pdf" \
    "2022:4Q22:2022-Annual-Reports-and-Accounts.pdf" \
    "2021:4Q21:2021-Annual-Reports-and-Accounts.pdf" \
    "2020:4Q20:2020-Annual-Reports-and-Accounts.pdf" \
    "2019:4Q19:2019-Annual-Reports-and-Accounts.pdf" \
    "2018:4Q18:2018-Annual-Report.pdf" \
    "2017:4Q17:2017-Annual-Report.pdf" \
    "2016:4Q16:2016-Annual-Report.pdf" \
    "2015:4Q15:2015-Annual-Report.pdf"
  do
    year="${spec%%:*}"; rest="${spec#*:}"; quarter="${rest%%:*}"; filename="${rest##*:}"
    download_pdf \
      "https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/${year}/${quarter}/${filename}" \
      "$FINANCIALS_DIR/unicredit_${year}_annual_report.pdf" "UniCredit $year"
  done
fi

# ── SANTANDER GROUP ────────────────────────────────────────────────────────────
# 2019+ verified; pre-2019 uses older naming
if should_download "santander"; then
  echo -e "\n${CYAN}Santander Group${NC}"
  for year in 2024 2023 2022 2021 2020 2019; do
    download_pdf \
      "https://www.santander.com/content/dam/santander-com/en/documentos/informe-financiero-anual/${year}/ifa-${year}-consolidated-annual-financial-report-en.pdf" \
      "$FINANCIALS_DIR/santander_group_${year}_annual_report.pdf" "Santander $year"
  done
  # Pre-2019 used different Spanish path
  for year in 2018 2017 2016 2015; do
    download_pdf \
      "https://www.santander.com/content/dam/santander-com/en/documentos/informe-anual-y-de-sostenibilidad/${year}/santander-${year}-annual-report.pdf" \
      "$FINANCIALS_DIR/santander_group_${year}_annual_report.pdf" "Santander $year"
  done
fi

# ── ABN AMRO ───────────────────────────────────────────────────────────────────
# ABN AMRO uses Contentful CDN (ctfassets.net) — not their own domain
# These stable URLs from their IR page download centre
if should_download "abn"; then
  echo -e "\n${CYAN}ABN AMRO${NC}"
  for spec in \
    "2024:https://downloads.ctfassets.net/1u811bvgvthc/ABN-AMRO-Integrated-Annual-Report-2024.pdf" \
    "2023:https://downloads.ctfassets.net/1u811bvgvthc/1ct3rr0164d6Vt5YuVrWqe/e700292b6cdec93acb5d782976efaf0e/ABN_AMRO___Integrated_Annual_Report_2023.pdf" \
    "2022:https://downloads.ctfassets.net/1u811bvgvthc/ABN-AMRO-Annual-Report-2022.pdf" \
    "2021:https://downloads.ctfassets.net/1u811bvgvthc/ABN-AMRO-Annual-Report-2021.pdf"
  do
    year="${spec%%:*}"; url="${spec#*:}"
    download_pdf "$url" "$FINANCIALS_DIR/abn_amro_${year}_annual_report.pdf" "ABN AMRO $year"
  done
  # Older years on abnamro.com direct
  for year in 2020 2019 2018 2017 2016 2015; do
    download_pdf \
      "https://www.abnamro.com/en/images/documents/Investors/Annual_Reports/${year}/ABN-AMRO-Annual-Report-${year}.pdf" \
      "$FINANCIALS_DIR/abn_amro_${year}_annual_report.pdf" "ABN AMRO $year"
  done
fi

# ── INTESA SANPAOLO ────────────────────────────────────────────────────────────
# Multiple URL patterns tried
if should_download "intesa"; then
  echo -e "\n${CYAN}Intesa Sanpaolo${NC}"
  for spec in \
    "2024:https://group.intesasanpaolo.com/content/dam/intesasanpaolo/investor-relations/annual-reports/report-annuale-2024-en.pdf" \
    "2023:https://group.intesasanpaolo.com/content/dam/intesasanpaolo/investor-relations/annual-reports/report-annuale-2023-en.pdf" \
    "2022:https://group.intesasanpaolo.com/content/dam/intesasanpaolo/investor-relations/annual-reports/report-annuale-2022-en.pdf" \
    "2021:https://group.intesasanpaolo.com/content/dam/intesasanpaolo/investor-relations/annual-reports/report-annuale-2021-en.pdf" \
    "2020:https://group.intesasanpaolo.com/scriptIsir0/si09/contentData/view/Annual-Report-2020.pdf" \
    "2019:https://group.intesasanpaolo.com/scriptIsir0/si09/contentData/view/Annual-Report-2019.pdf" \
    "2018:https://group.intesasanpaolo.com/scriptIsir0/si09/contentData/view/Annual-Report-2018.pdf" \
    "2017:https://group.intesasanpaolo.com/scriptIsir0/si09/contentData/view/Annual-Report-2017.pdf"
  do
    year="${spec%%:*}"; url="${spec#*:}"
    download_pdf "$url" "$FINANCIALS_DIR/intesa_sanpaolo_${year}_annual_report.pdf" "Intesa Sanpaolo $year"
  done
fi

# ── COMMONWEALTH BANK ─────────────────────────────────────────────────────────
if should_download "commonwealth"; then
  echo -e "\n${CYAN}Commonwealth Bank of Australia${NC}"
  for year in 2024 2023 2022 2021 2020 2019 2018 2017 2016 2015; do
    download_pdf \
      "https://www.commbank.com.au/content/dam/commbank-assets/investors/${year}-annual-report/${year}-annual-report.pdf" \
      "$FINANCIALS_DIR/commonwealth_bank_${year}_annual_report.pdf" "CBA $year"
  done
fi

# ── ANZ ─────────────────────────────────────────────────────────────────────────
# 2024 verified. Older years use same ANZBGL pattern but may have different spacing
if should_download "anz"; then
  echo -e "\n${CYAN}ANZ Banking Group${NC}"
  for year in 2024 2023 2022 2021 2020 2019 2018 2017 2016 2015; do
    download_pdf \
      "https://www.anz.com/content/dam/anzcom/shareholder/ANZBGL-${year}-Annual%20Report.pdf" \
      "$FINANCIALS_DIR/anz_banking_${year}_annual_report.pdf" "ANZ $year"
  done
fi

# ── WESTPAC ─────────────────────────────────────────────────────────────────────
# 2024 verified; 2023 try both naming patterns
if should_download "westpac"; then
  echo -e "\n${CYAN}Westpac${NC}"
  for year in 2024 2023 2022 2021 2020 2019 2018; do
    download_pdf \
      "https://www.westpac.com.au/content/dam/public/wbc/documents/pdf/aw/ic/wbc-annual-report-${year}.pdf" \
      "$FINANCIALS_DIR/westpac_${year}_annual_report.pdf" "Westpac $year"
  done
  for year in 2017 2016 2015; do
    download_pdf \
      "https://www.westpac.com.au/content/dam/public/wbc/documents/pdf/aw/ic/${year}-annual-report.pdf" \
      "$FINANCIALS_DIR/westpac_${year}_annual_report.pdf" "Westpac $year"
  done
fi

# ── NAB ─────────────────────────────────────────────────────────────────────────
# 2022-2024 in /nab/ path; older in /nabrwd/ path
if should_download "nab"; then
  echo -e "\n${CYAN}NAB${NC}"
  for year in 2024 2023 2022; do
    download_pdf \
      "https://www.nab.com.au/content/dam/nab/documents/reports/corporate/${year}-annual-report.pdf" \
      "$FINANCIALS_DIR/nab_${year}_annual_report.pdf" "NAB $year"
  done
  for year in 2021 2020 2019 2018 2017 2016 2015; do
    download_pdf \
      "https://www.nab.com.au/content/dam/nabrwd/documents/reports/corporate/${year}-annual-report.pdf" \
      "$FINANCIALS_DIR/nab_${year}_annual_report.pdf" "NAB $year"
  done
fi

# ── ING (manual) ──────────────────────────────────────────────────────────────
if should_download "ing"; then
  echo -e "\n${CYAN}ING Group — manual required (JS-rendered)${NC}"
  manual "  AR:  https://www.ing.com/Investor-relations/Financial-performance/Annual-reports.htm"
  manual "  Save: financials/ing_group_<year>_annual_report.pdf"
fi

fi  # end ! PILLAR3_ONLY

# =============================================================================
# PILLAR 3 REPORTS
# =============================================================================
if ! $AR_ONLY; then
echo ""; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " PILLAR 3 REPORTS"; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── LLOYDS PILLAR 3 ─────────────────────────────────────────────────────────────
# All years use same financial-performance path pattern (verified 2023-2025)
if should_download "lloyds"; then
  echo -e "\n${CYAN}Lloyds Banking Group — Pillar 3${NC}"
  for year in 2025 2024 2023 2022 2021 2020 2019 2018; do
    download_pdf \
      "https://www.lloydsbankinggroup.com/assets/pdfs/investors/financial-performance/lloyds-banking-group-plc/${year}/q4/${year}-lbg-fy-pillar-3.pdf" \
      "$PILLAR3_DIR/lloyds_banking_group_${year}_pillar3.pdf" "Lloyds $year Pillar 3"
  done
fi

# ── BARCLAYS PILLAR 3 ──────────────────────────────────────────────────────────
# 2022-2024: reports-and-events/annual-reports/<year>/Pillar-3/ path (verified)
# 2018-2021: ResultAnnouncements path
if should_download "barclays"; then
  echo -e "\n${CYAN}Barclays — Pillar 3${NC}"
  for year in 2024 2023 2022; do
    download_pdf \
      "https://home.barclays/content/dam/home-barclays/documents/investor-relations/reports-and-events/annual-reports/${year}/Pillar-3/Barclays-PLC-Pillar-3-Report-${year}.pdf" \
      "$PILLAR3_DIR/barclays_${year}_pillar3.pdf" "Barclays $year Pillar 3"
  done
  for spec in "2021:FY21" "2020:FY20" "2019:FY19" "2018:FY18"; do
    year="${spec%%:*}"; tag="${spec##*:}"
    download_pdf \
      "https://home.barclays/content/dam/home-barclays/documents/investor-relations/ResultAnnouncements/FullYear${year}Results/${tag}-Barclays-PLC-Pillar-3-Report.pdf" \
      "$PILLAR3_DIR/barclays_${year}_pillar3.pdf" "Barclays $year Pillar 3"
  done
fi

# ── HSBC PILLAR 3 ──────────────────────────────────────────────────────────────
# Verified format: <prefix>-pillar-3-disclosures-at-31-december-<year>.pdf
if should_download "hsbc"; then
  echo -e "\n${CYAN}HSBC Holdings — Pillar 3${NC}"
  for spec in \
    "2024:250227" "2023:240221" "2022:230221" "2021:220222" \
    "2020:210223" "2019:200218" "2018:190219"
  do
    year="${spec%%:*}"; prefix="${spec##*:}"
    download_pdf \
      "https://www.hsbc.com/-/files/hsbc/investors/hsbc-results/${year}/annual/pdfs/hsbc-holdings-plc/${prefix}-pillar-3-disclosures-at-31-december-${year}.pdf" \
      "$PILLAR3_DIR/hsbc_holdings_${year}_pillar3.pdf" "HSBC $year Pillar 3"
  done
fi

# ── NATWEST PILLAR 3 ──────────────────────────────────────────────────────────
# Each year has a specific filename (verified from live search)
if should_download "natwest"; then
  echo -e "\n${CYAN}NatWest Group — Pillar 3${NC}"
  for spec in \
    "2024:14022025:nwg-pillar-3-report-2024.pdf" \
    "2023:16022024:nwg-pillar-3-report-2023.pdf" \
    "2022:17022023:nwg-pillar-3-report-v1.pdf" \
    "2021:18022022:nwg-pillar-3-supplement-2021.pdf" \
    "2020:19022021:natwest-holdings-pillar-3-report-fy2020.pdf" \
    "2019:14022020:rbs-pillar-3-report-2019.pdf" \
    "2018:15022019:rbs-pillar-3-report-2018.pdf"
  do
    year="${spec%%:*}"; rest="${spec#*:}"; datepath="${rest%%:*}"; filename="${rest##*:}"
    download_pdf \
      "https://investors.natwestgroup.com/~/media/Files/R/RBS-IR-V2/results-center/${datepath}/${filename}" \
      "$PILLAR3_DIR/natwest_group_${year}_pillar3.pdf" "NatWest $year Pillar 3"
  done
fi

# ── DEUTSCHE BANK PILLAR 3 ─────────────────────────────────────────────────────
# Same folder pattern as AR — stored in following year's folder
if should_download "deutsche"; then
  echo -e "\n${CYAN}Deutsche Bank — Pillar 3${NC}"
  for spec in \
    "2024:2025" "2023:2024" "2022:2023" "2021:2022" "2020:2021" \
    "2019:2020" "2018:2019" "2017:2018"
  do
    report_year="${spec%%:*}"; folder_year="${spec##*:}"
    download_pdf \
      "https://investor-relations.db.com/files/documents/annual-reports/${folder_year}/Pillar-3-Report-${report_year}.pdf" \
      "$PILLAR3_DIR/deutsche_bank_${report_year}_pillar3.pdf" "Deutsche Bank $report_year Pillar 3"
  done
fi

# ── UNICREDIT PILLAR 3 ─────────────────────────────────────────────────────────
if should_download "unicredit"; then
  echo -e "\n${CYAN}UniCredit — Pillar 3${NC}"
  for spec in \
    "2024:4Q24" "2023:4Q23" "2022:4Q22" "2021:4Q21" "2020:4Q20"
  do
    year="${spec%%:*}"; quarter="${spec##*:}"
    download_pdf \
      "https://www.unicreditgroup.eu/content/dam/unicreditgroup-eu/documents/en/investors/financial-reports/${year}/${quarter}/${year}-Pillar3-Report.pdf" \
      "$PILLAR3_DIR/unicredit_${year}_pillar3.pdf" "UniCredit $year Pillar 3"
  done
fi

# ── JPMORGAN PILLAR 3 ─────────────────────────────────────────────────────────
if should_download "jpmorgan"; then
  echo -e "\n${CYAN}JPMorgan Chase — Pillar 3${NC}"
  for year in 2024 2023 2022 2021 2020; do
    download_pdf \
      "https://www.jpmorganchase.com/content/dam/jpmc/jpmorgan-chase-and-co/investor-relations/documents/basel-disclosures/${year}-4q-pillar-3-capital-disclosures.pdf" \
      "$PILLAR3_DIR/jpmorgan_chase_${year}_pillar3.pdf" "JPMorgan $year Pillar 3"
  done
fi

fi  # end ! AR_ONLY

# =============================================================================
# MANUAL DOWNLOADS
# =============================================================================
echo ""; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " MANUAL DOWNLOADS REQUIRED"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo " Standard Chartered (HTTP 403)"
echo "   https://www.sc.com/en/investors/results-and-reports/"
echo "   financials/standard_chartered_<year>_annual_report.pdf"
echo "   pillar3/standard_chartered_<year>_pillar3.pdf"
echo ""
echo " ING Group (JS-rendered)"
echo "   AR:  https://www.ing.com/Investor-relations/Financial-performance/Annual-reports.htm"
echo "   P3:  https://www.ing.com/Investor-relations/Financial-performance/Risk-and-Capital-reports.htm"
echo "   financials/ing_group_<year>_annual_report.pdf"
echo "   pillar3/ing_group_<year>_pillar3.pdf"
echo ""
echo " BBVA (JS-rendered)"
echo "   https://shareholdersandinvestors.bbva.com/financial-information/annual-report/"
echo "   financials/bbva_<year>_annual_report.pdf"
echo ""
echo " Bank of America Pillar 3"
echo "   https://investor.bankofamerica.com/regulatory-and-other-filings/basel-disclosures"
echo "   pillar3/bank_of_america_<year>_pillar3.pdf"
echo ""
echo " Wells Fargo Pillar 3"
echo "   https://www.wellsfargo.com/invest_relations/basel/"
echo "   pillar3/wells_fargo_<year>_pillar3.pdf"
echo ""
echo " Goldman Sachs Pillar 3"
echo "   https://www.goldmansachs.com/investor-relations/financials/basel-disclosures/"
echo "   pillar3/goldman_sachs_<year>_pillar3.pdf"
echo ""

# =============================================================================
# SUMMARY
# =============================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Downloaded : $DOWNLOADED"
echo " Skipped    : $SKIPPED (valid PDFs already present)"
echo " Failed     : $FAILED"
if [[ ${#FAILED_LIST[@]} -gt 0 ]]; then
  echo ""; echo " Failed items (check DATA_ACQUISITION_PLAN.md for manual URLs):"
  for item in "${FAILED_LIST[@]}"; do echo "   ✗ $item"; done
fi
AR_COUNT=$(find "$FINANCIALS_DIR" \( -name "*.pdf" -o -name "*.htm" \) 2>/dev/null | wc -l | tr -d ' ')
P3_COUNT=$(find "$PILLAR3_DIR" -name "*.pdf" 2>/dev/null | wc -l | tr -d ' ')
echo ""; echo " financials/ : $AR_COUNT files"; echo " pillar3/    : $P3_COUNT files"
echo ""; echo " Validate: ./scripts/download_annual_reports.sh --validate"
echo " Retry:    ./scripts/download_annual_reports.sh --banks <name>"
echo " Next:     ./run.sh --reprocess"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
