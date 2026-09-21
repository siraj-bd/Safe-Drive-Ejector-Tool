from setuptools import setup, find_packages

setup(
    name="safe-drive-ejector",
    version="1.0.0",
    description="Cross-platform External Disk Safe Ejector & Auto-Remounter (macOS & Windows)",
    author="Siraj",
    url="https://github.com/siraj-bd/Safe-Drive-Ejector-Tool",
    license="MIT",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "safe-eject=main:main",
        ],
    },
    python_requires=">=3.8",
    install_requires=[],
    extras_require={
        "tray": ["pystray>=0.19.5", "pillow>=10.0.0"],
    },
)
