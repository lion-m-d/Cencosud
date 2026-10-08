"""03-validation-engine. En AWS lo ejecuta CodeBuild, sin un job propio de Glue."""

from reconciliation.validate_cli import main


if __name__ == "__main__":
    main()
