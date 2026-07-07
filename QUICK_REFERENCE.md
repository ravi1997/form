# 🚀 Quick Reference - Test Suite Commands

## Installation
```bash
# Install test dependencies
pip install -r requirements-test.txt
```

## Run Tests
```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_models_user.py -v

# Specific test class
pytest tests/test_models_user.py::TestUserBasicCreation -v

# Specific test
pytest tests/test_models_user.py::TestUserBasicCreation::test_create_user_with_minimal_fields -v
```

## Filter Tests
```bash
# Unit tests only
pytest tests/ -m unit -v

# Integration tests only
pytest tests/ -m integration -v

# Security tests only
pytest tests/ -m security -v

# Exclude slow tests
pytest tests/ -m "not slow" -v
```

## Coverage
```bash
# Generate HTML coverage report
pytest tests/ --cov=app --cov-report=html

# Show coverage in terminal
pytest tests/ --cov=app --cov-report=term-missing
```

## Debugging
```bash
# Show print output
pytest tests/ -s -v

# Stop at first failure
pytest tests/ -x

# Full traceback
pytest tests/ --tb=long

# Run with debugger on failure
pytest tests/ --pdb
```

## Performance
```bash
# Show slowest tests
pytest tests/ --durations=10

# Run in parallel (install pytest-xdist first)
pytest tests/ -n auto

# Run only last failed tests
pytest tests/ --lf
```

## Test Organization

```
tests/
├── conftest.py              → Fixtures & Configuration
├── test_models_user.py      → User Model (42 tests)
├── test_models_organization.py → Organization Model (29 tests)
├── test_services_auth.py    → Auth Service (34 tests)
├── test_api_auth.py        → Auth API (30 tests)
├── test_security_validation.py → Security (31 tests)
└── test_integration.py      → Integration (20 tests)
```

## Test Markers

```python
@pytest.mark.unit           # Unit tests
@pytest.mark.integration    # Integration tests
@pytest.mark.security       # Security tests
@pytest.mark.slow          # Slow tests
```

## Fixtures

```python
def test_something(self, app_context, client, test_user):
    # app_context - Flask app context
    # client - Test client for API calls
    # test_user - Pre-created test user
    pass
```

## Common Assertions

```python
# Status codes
assert response.status_code == 200
assert response.status_code in [200, 201]

# JSON responses
data = json.loads(response.data)
assert "access_token" in data

# Exceptions
with pytest.raises(ValidationError):
    user.clean()

# Database queries
retrieved = User.objects.get(uuid=user.uuid)
assert retrieved.name == "John"

# Timestamps
assert user.created_at is not None
assert user.updated_at >= user.created_at
```

## Test Statistics

- **Total Tests**: 186+
- **User Model**: 42 tests
- **Organization Model**: 29 tests
- **Auth Service**: 34 tests
- **Auth API**: 30 tests
- **Security**: 31 tests
- **Integration**: 20 tests

## Files

| File | Lines | Tests | Purpose |
|------|-------|-------|---------|
| conftest.py | 100 | - | Fixtures & Config |
| test_models_user.py | 720 | 42 | User Model |
| test_models_organization.py | 410 | 29 | Organization |
| test_services_auth.py | 590 | 34 | Auth Service |
| test_api_auth.py | 600 | 30 | Auth API |
| test_security_validation.py | 500 | 31 | Security |
| test_integration.py | 460 | 20 | Integration |

## Documentation

- **TESTING_GUIDE.md** - How to run tests
- **TEST_SUITE_README.md** - Detailed docs
- **TEST_SUITE_SUMMARY.md** - Overview
- **pytest.ini** - Configuration
- **requirements-test.txt** - Dependencies

## Key Testing Areas

✅ **Models** - All fields, validation, relationships
✅ **Services** - Auth, tokens, sessions
✅ **API** - Login, register, refresh, logout
✅ **Security** - Passwords, JWT, injection prevention
✅ **Validation** - Input sanitization, constraints
✅ **Integration** - Component interactions
✅ **Performance** - Bulk ops, large datasets
✅ **Error Handling** - Invalid data, recovery

---

**Pro Tip**: Run `pytest tests/ --cov=app` before committing to catch bugs early!
