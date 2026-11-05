# Billing API notes

- Base URL comes from `BILLING_API`.
- Every response carries an `X-Request-Id` header.
- JSON responses also repeat it as `requestId` in the body.
- `DELETE` and `POST .../archive` answer `204 No Content` when there is nothing to return.
