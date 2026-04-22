# Expenses.py Fixes - Implementation Steps

## TODO (4/5 complete)

- [x] 1. Fix update_expense: Add `from datetime import timezone` import + ensure `datetime.now(timezone.utc)`
- [x] 2. Fix get_summary: Move InvoiceStatus to top import, remove local import
- [x] 3. Add try/except error handling to create_expense, update_expense, delete_expense
- [x] 5. Fix cogs_ytd scalar handling in get_summary: `cogs_ytd = float(cogs_rows or 0)`
- [ ] 4. Fix _get_business HTTPException handling pattern in routes

## Notes
- Logger already present
- Add `except HTTPException: raise` before broad Exception in routes

**Next:** Test endpoints after all ✓

