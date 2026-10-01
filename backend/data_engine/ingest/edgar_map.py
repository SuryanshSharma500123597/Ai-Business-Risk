"""Versioned SEC us-gaap to canonical financial-field mapping."""

EDGAR_MAP_VERSION = "us-gaap-map-1"

# Ordered alternatives are intentional: company facts uses taxonomy-specific
# tags and filers do not all report the same synonym.
US_GAAP_FIELD_TAGS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "cogs": ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsAndSold"),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "receivables": ("AccountsReceivableNetCurrent", "AccountsReceivableNet"),
    "inventory": ("InventoryNet", "InventoryGross"),
    "payables": ("AccountsPayableCurrent", "AccountsPayableAndAccruedLiabilitiesCurrent"),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
    "equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "total_debt": ("LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtNoncurrent"),
    "st_debt": ("LongTermDebtCurrent", "ShortTermBorrowings"),
    "lt_debt": ("LongTermDebtNoncurrent",),
    "opex": ("OperatingExpenses",),
    "ebit": ("OperatingIncomeLoss",),
    "interest_expense": ("InterestExpenseNonOperating", "InterestExpenseDebt"),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "ocf": ("NetCashProvidedByUsedInOperatingActivities",),
    "da": (
        "DepreciationDepletionAndAmortization",
        "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
    ),
}
