# Security

The application includes several security-oriented building blocks.

## Authentication

Authentication uses JWT access and refresh tokens.

Password hashing uses Argon2.

## Authorization

Route-level authorization and project access checks are implemented in the API security layer.

Relevant modules:

```text
src/ai_testplan_generator/api/security/
```

## API Keys

API key support uses hashed keys rather than storing raw API keys.

## Sensitive Configuration

Secrets must be provided through environment variables and should not be committed.

Examples:

- provider API keys;
- JWT secrets;
- private key paths;
- database credentials;
- blob encryption key.

## Production Security Notes

For production-like use:

- do not use `API_CORS_ORIGINS=["*"]`;
- do not use the local default JWT secret;
- use HTTPS;
- use a real database backup strategy;
- use encrypted blob storage;
- restrict admin routes;
- rotate external API keys.
