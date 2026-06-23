class _BudgetExceededType:
    _instance: "_BudgetExceededType | None" = None

    def __new__(cls) -> "_BudgetExceededType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "BUDGET_EXCEEDED"


BUDGET_EXCEEDED = _BudgetExceededType()
