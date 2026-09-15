---
name: test-agent
description: This skill should be used when the user asks to "run tests", "test the app", "test the API", or wants automated tests run against the application.
version: 1.0.0
allowed-tools: Read, Bash, Write, Edit, Glob
user-invocable: true
---

# Test Agent — LinDriveSpace

Run automated tests against LinDriveSpace at `/home/user/projects/lindrivespace`.

## Responsibilities

### 1. Unit Tests

Test individual modules and functions by importing directly:

- **Core logic**: Test the main business logic functions with known inputs/outputs
- **Edge cases**: Empty inputs, boundary values, invalid data
- **Error handling**: Verify errors are raised/handled appropriately
- **Data transformations**: Verify input/output mappings are correct

### 2. API / Route Tests

Use the application's test client or HTTP requests:

- **GET endpoints**: Verify 200 responses with expected content
- **POST endpoints**: Verify correct handling of valid and invalid payloads
- **Error responses**: Verify 4xx/5xx responses for bad requests
- **Response format**: Verify JSON structure, HTML content, or other expected formats

### 3. Integration Tests

- **Data round-trip**: Verify end-to-end flows produce correct persistent state
- **File/DB persistence**: Verify data is correctly stored and retrievable
- **External service mocks**: Test integrations with external APIs using mocks where appropriate

### 4. Frontend / Static Asset Tests

- Verify static assets load (CSS, JS, images)
- Verify template rendering produces valid HTML
- Check for broken links or missing references

## Execution

Discover the project's test runner and use it. Common patterns:
- Python: `pytest`, `unittest`, or direct script execution
- Node: `npm test`, `jest`, `vitest`
- Go: `go test ./...`
- If no test runner exists, create a test script and run it

Present results as PASS/FAIL per test with a summary count.

Skip slow tests (live API calls, full E2E) unless the user explicitly requests them.
