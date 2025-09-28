import sys
import importlib

REQUIRED_PYTHON = (3, 11)
REQUIRED_PACKAGES = [
    "flask",
    "pandas",
    "numpy",
    "plotly",
    "matplotlib",
    "requests",
    "aiohttp",
    "websockets",
    "python-dotenv",
]

def check_python():
    if sys.version_info[:2] != REQUIRED_PYTHON:
        print(f"⚠️ Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]} required, "
              f"but found {sys.version.split()[0]}")
    else:
        print(f"✅ Python version {sys.version.split()[0]} OK")

def check_packages():
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
            print(f"✅ {pkg} installed")
        except ImportError:
            print(f"❌ {pkg} NOT installed")
            missing.append(pkg)
    return missing

if __name__ == "__main__":
    check_python()
    missing = check_packages()
    if missing:
        print("\n⚠️ Missing packages, run:")
        print(f"pip install {' '.join(missing)}")
    else:
        print("\n🎉 Environment looks good!")