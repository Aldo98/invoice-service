# Invoice Service (FastAPI → AWS Lambda Container)

A simple invoice PDF generator built with **FastAPI**, packaged as an **AWS Lambda container image**, and deployed using **AWS SAM**.

## Features
- `POST /generate-invoice` returns a **PDF invoice** (`application/pdf`)
- Supports `booking_id`, `payment_id`, and `locale` (optional) in addition to core invoice fields

---

## API

### Endpoint
- `POST /generate-invoice`
  - **Response:** PDF bytes (`application/pdf`)
  - **Typical usage:** client downloads/saves the PDF

### Example Request Body
```json
{
  "customer_name": "John Doe",
  "guide_name": "Bali Explorer",
  "date": "2026-04-05",
  "price": 150.0,
  "currency": "USD"
}
```

---

## Deployed Service
Postman shared collection: [View Collection][postman]. This collection is designed to be used with a **AWS-Lambda Environment** that included inside.

### Usage
1. Open Postman
2. Select the correct **Environment** (top-right dropdown)
3. Select "AWS-Lambda"
4. Send requests

[postman]: https://www.postman.com/infra-grit/workspace/aldo-public/request/10685688-9e434054-cd96-42ed-9f50-4d57d2a4a3f0?action=share&creator=10685688&active-environment=10685688-6ff48377-89dc-45a6-931e-bc53e7dce604