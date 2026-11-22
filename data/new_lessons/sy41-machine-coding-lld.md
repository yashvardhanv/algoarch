# Lesson 41 — Machine Coding: Parking Lot, Splitwise & In-Memory DB

> **Priority:** ★★★★★ (The 60-90 min elimination round at Swiggy, Flipkart, Uber, Razorpay, Cred)  
> **Estimated Study Time:** 70 minutes  
> **Key Skills:** SOLID Principles in code, Factory, Strategy, Observer, State, Singleton patterns, Thread-safety (locks, concurrent collections), Extensible class hierarchy, Clean CLI runner, Unit tests.

---

## 1. The 60-Minute Machine Coding Protocol

Most candidates fail machine coding not because they don't know OOP, but because they spend 40 minutes designing database schemas or overcomplicating with external frameworks. Follow this strict timeline:

- **Minute 00 - 10: Requirements & Entity Identification**
  Clarify inputs/outputs. Identify primary entities (e.g. `User`, `Expense`, `Split`, `Group` in Splitwise).
- **Minute 10 - 20: Core Model Classes & Enums**
  Define clear classes, private fields, getters, and immutable value objects.
- **Minute 20 - 45: Business Logic Services & Strategy Patterns**
  Extract volatile business rules into Strategies (e.g. `ExactSplitStrategy`, `EqualSplitStrategy`, `PercentageSplitStrategy`).
- **Minute 45 - 55: In-Memory Storage & Thread Safety**
  Create repository classes with `threading.Lock` or `ConcurrentHashMap`.
- **Minute 55 - 60: Driver Code / CLI & Test Scenarios**
  Provide a working `main()` that parses input commands and proves all sample cases pass.

---

## 2. Production Python Blueprint: Splitwise Strategy Pattern

```python
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict
import threading

class SplitType(Enum):
    EQUAL = "EQUAL"
    EXACT = "EXACT"
    PERCENT = "PERCENT"

@dataclass
class User:
    user_id: str
    name: str
    email: str

@dataclass
class Split:
    user: User
    amount: float

class SplitStrategy(ABC):
    @abstractmethod
    def validate_and_compute(self, total_amount: float, splits: List[Split], extra_params: List[float] = None) -> List[Split]:
        pass

class EqualSplitStrategy(SplitStrategy):
    def validate_and_compute(self, total_amount: float, splits: List[Split], extra_params: List[float] = None) -> List[Split]:
        n = len(splits)
        split_amount = round(total_amount / n, 2)
        for s in splits:
            s.amount = split_amount
        return splits

class ExactSplitStrategy(SplitStrategy):
    def validate_and_compute(self, total_amount: float, splits: List[Split], extra_params: List[float] = None) -> List[Split]:
        total = sum(s.amount for s in splits)
        if abs(total - total_amount) > 0.01:
            raise ValueError(f"Sum of split amounts ({total}) does not match total amount ({total_amount})")
        return splits

class SplitwiseService:
    def __init__(self):
        self._lock = threading.Lock()
        self.users: Dict[str, User] = {}
        # balance_sheet[u1][u2] = amount u1 owes u2
        self.balance_sheet: Dict[str, Dict[str, float]] = {}

    def add_user(self, user: User):
        with self._lock:
            self.users[user.user_id] = user
            self.balance_sheet[user.user_id] = {}

    def add_expense(self, paid_by: User, total_amount: float, splits: List[Split], strategy: SplitStrategy):
        validated_splits = strategy.validate_and_compute(total_amount, splits)
        with self._lock:
            for split in validated_splits:
                if split.user.user_id == paid_by.user_id:
                    continue
                borrower = split.user.user_id
                payer = paid_by.user_id
                amt = split.amount
                
                self.balance_sheet[borrower][payer] = self.balance_sheet[borrower].get(payer, 0.0) + amt
                self.balance_sheet[payer][borrower] = self.balance_sheet[payer].get(borrower, 0.0) - amt

    def show_balances(self) -> List[str]:
        output = []
        with self._lock:
            for u1, debts in self.balance_sheet.items():
                for u2, amt in debts.items():
                    if amt > 0:
                        output.append(f"{self.users[u1].name} owes {self.users[u2].name}: ₹{amt:.2f}")
        return output
```

---

## 3. What L5 Evaluators Grade in Machine Coding

1. **Extensibility (OCP - Open/Closed Principle):** If the interviewer says "Now add Crypto splits or Currency conversion", can you add a new strategy class without modifying existing service code?
2. **Concurrency / Thread-Safety:** Did you guard state mutations with mutex locks?
3. **Clean Code & Idiomatic Naming:** No massive 200-line monolithic methods; clean single-responsibility methods.
