# Flask REST API - User Management

A simple Flask REST API for managing users with in-memory storage.

## Features

- **GET /users** - Retrieve all users
- **POST /users** - Create a new user
- In-memory storage (no database required)
- Comprehensive error handling
- JSON request/response format

## Installation

1. Install Python 3.7 or higher

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the API

Start the Flask development server:

```bash
python app.py
```

The API will be available at `http://localhost:5000`

## API Endpoints

### GET /users

Retrieves a list of all users.

**Request:**
```bash
curl http://localhost:5000/users
```

**Response (200 OK):**
```json
{
  "users": [
    {
      "id": 1,
      "name": "John Doe",
      "email": "john@example.com"
    }
  ],
  "count": 1
}
```

### POST /users

Creates a new user.

**Request:**
```bash
curl -X POST http://localhost:5000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Jane Doe",
    "email": "jane@example.com"
  }'
```

**Response (201 Created):**
```json
{
  "message": "User created successfully",
  "user": {
    "id": 2,
    "name": "Jane Doe",
    "email": "jane@example.com"
  }
}
```

**Required Fields:**
- `name` (string, required): User's name
- `email` (string, required): User's email address

## Error Handling

The API returns appropriate HTTP status codes and error messages:

### 400 Bad Request
- Missing or invalid JSON body
- Missing required fields
- Invalid field types

**Example:**
```json
{
  "error": "Validation error",
  "message": "Field \"name\" is required"
}
```

### 409 Conflict
- Duplicate email address

**Example:**
```json
{
  "error": "Conflict",
  "message": "User with email \"jane@example.com\" already exists"
}
```

### 404 Not Found
- Endpoint does not exist

### 405 Method Not Allowed
- HTTP method not supported for endpoint

### 500 Internal Server Error
- Unexpected server errors

## Example Usage

### Create a user
```bash
curl -X POST http://localhost:5000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice Smith", "email": "alice@example.com"}'
```

### Get all users
```bash
curl http://localhost:5000/users
```

### Create another user
```bash
curl -X POST http://localhost:5000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Bob Johnson", "email": "bob@example.com"}'
```

## Notes

- Data is stored in-memory and will be lost when the server restarts
- User IDs are auto-incremented starting from 1
- Email addresses must be unique
- All string fields are trimmed of whitespace
