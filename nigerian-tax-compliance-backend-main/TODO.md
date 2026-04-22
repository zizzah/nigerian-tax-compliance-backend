# Products.py Fixes - Implementation Steps

## TODO (6/6 complete) ✅

- [x] 1. Add logger import and logger instance at module top
- [x] 2. Add InvoiceItem import for usage count query
- [x] 3. Fix create_product: Add general try/except Exception around DB ops
- [x] 4. Fix update_product: Add general try/except Exception around DB ops  
- [x] 5. Fix delete_product: Add full try/except Exception block
- [x] 6. Fix permanently_delete_product: Replace usage_count with live InvoiceItem query + add try/except

## All fixes complete!

**Test:** Restart server (`uvicorn app.main:app --reload`) and test all product endpoints.

## Testing
- Restart server: `uvicorn app.main:app --reload`
- Test all 4 endpoints with valid/invalid data
- Force DB error if needed to test exception handling
- Verify logs show logger usage

**Next:** After all ✓, run `attempt_completion`

