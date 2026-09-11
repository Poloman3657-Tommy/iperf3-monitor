"""Executable entry point, including an opt-in offline package diagnostic."""
import sys

if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--check-package':
        from package_check import check_package
        sys.exit(check_package(sys.argv[2]))
    else:
        from gui import main
        main()
