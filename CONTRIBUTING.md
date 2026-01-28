# Contributing to DataAtelier

Thank you for your interest in contributing to DataAtelier!

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/jwgwalton/DataAtelier.git
cd DataAtelier
```

2. Install in development mode:
```bash
pip install -e ".[dev]"
```

3. Install pre-commit hooks (optional):
```bash
pre-commit install
```

## Code Style

We use:
- **Black** for code formatting (line length: 100)
- **Ruff** for linting
- Type hints where appropriate

Format your code before committing:
```bash
black .
ruff check . --fix
```

## Testing

Currently, the project uses manual testing. We welcome contributions to add automated tests!

To manually test:
1. Set up a test Azure Storage account with sample data
2. Configure environment variables (see .env.example)
3. Run the application: `python azure_blob_cleanup_tui.py run --container testcontainer`

## Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Format and lint your code
5. Test your changes
6. Commit with clear messages
7. Push to your fork
8. Open a Pull Request

## Areas for Contribution

- **Tests**: Add unit and integration tests
- **Documentation**: Improve docs, add examples, tutorials
- **Features**: 
  - Additional file preview types (PDF, DOCX)
  - Search and filtering improvements
  - Batch operations enhancements
  - Export to different formats
- **Bug fixes**: Check the issue tracker
- **Performance**: Optimize LLM calls, caching, file I/O

## Questions?

Open an issue for discussion or questions.
